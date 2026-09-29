#!/usr/bin/env python3
"""Taiwan Dashboard Clock: scoring, validation and logging.

Source of truth: docs/_data/taiwan_clock.json. Standard library only.

    python3 scripts/taiwan_clock.py check
        Validate the data file and print the current reading.
    python3 scripts/taiwan_clock.py log --date 2026-10-05 --note "What moved."
        Recompute the reading, store it in "current", and append (or replace)
        that date's entry in "history".

Model (after Moore's 13 dials, plus an indications-and-warning layer):
    S = (mean dial reading + 2) / 4            motive, 0..1
    T = mean I&W level / 3                     preparation, 0..1
    minutes = round(60 - 30*S - 28*T), clamped to 2..60
    if any I&W level is 3: minutes = min(minutes, 10)

The page (docs/taiwan-clock.html) restates this model under "How the clock is
set" and renders the stored "current" block. Keep both in step with this file.
"""
import argparse
import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "docs" / "_data" / "taiwan_clock.json"
MAX_HISTORY = 60
TRENDS = {"rising", "easing", "steady"}
STATUSES = {"active", "strengthened", "weakened"}


def compute(dials, iw):
    """Return the clock reading for a list of dials and I&W indicators."""
    if len(dials) != 13:
        raise ValueError(f"expected 13 dials, got {len(dials)}")
    readings = [int(d["reading"]) for d in dials]
    levels = [int(i["level"]) for i in iw]
    s = (sum(readings) / len(readings) + 2) / 4
    t = (sum(levels) / len(levels) / 3) if levels else 0.0
    # Round half up; Python's round() would round half to even.
    minutes = int(60 - 30 * s - 28 * t + 0.5)
    minutes = max(2, min(60, minutes))
    if any(lv >= 3 for lv in levels):
        minutes = min(minutes, 10)
    sooner = sum(r > 0 for r in readings)
    later = sum(r < 0 for r in readings)
    return {
        "minutes": minutes,
        "motive": round(s, 3),
        "preparation": round(t, 3),
        "sooner": sooner,
        "later": later,
        "neutral": len(readings) - sooner - later,
    }


def validate(data):
    """Return a list of problems; empty means the file is sound."""
    errs = []
    for key in ("as_of", "as_of_label", "summary", "dials", "iw", "factors", "dates", "history"):
        if key not in data:
            errs.append(f"missing top-level key: {key}")
    if errs:
        return errs
    ns = sorted(d.get("n") for d in data["dials"])
    if ns != list(range(1, 14)):
        errs.append(f"dials must be numbered 1..13, got {ns}")
    for d in data["dials"]:
        tag = f"dial {d.get('n')}"
        if d.get("reading") not in (-2, -1, 0, 1, 2):
            errs.append(f"{tag}: reading must be an integer -2..2")
        if d.get("window") not in ("opening", "closing"):
            errs.append(f"{tag}: window must be opening or closing")
        if d.get("moore") not in ("+", "-"):
            errs.append(f"{tag}: moore must be '+' or '-'")
        if d.get("trend") not in TRENDS:
            errs.append(f"{tag}: trend must be one of {sorted(TRENDS)}")
        errs += _check_card(tag, d)
    for i in data["iw"]:
        tag = f"iw {i.get('id')}"
        if i.get("level") not in (0, 1, 2, 3):
            errs.append(f"{tag}: level must be an integer 0..3")
        errs += _check_card(tag, i)
    for f in data["factors"]:
        if f.get("status") not in STATUSES:
            errs.append(f"factor {f.get('id')}: status must be one of {sorted(STATUSES)}")
    for text_field in _all_text(data):
        if "\u2014" in text_field:
            errs.append(f"em dash found (house style forbids them): {text_field[:60]}...")
    if data.get("current") is not None:
        expected = compute(data["dials"], data["iw"])
        if data["current"] != expected:
            errs.append(f"'current' is stale: stored {data['current']}, computed {expected}. Run the log command.")
    return errs


def _check_card(tag, card):
    errs = []
    if not card.get("assessment"):
        errs.append(f"{tag}: empty assessment")
    for s in card.get("sources", []):
        if not str(s.get("url", "")).startswith("https://"):
            errs.append(f"{tag}: source url must be https: {s}")
    return errs


def _all_text(data):
    """Yield every string in the file: the page renders names, dates and source titles too."""
    if isinstance(data, str):
        yield data
    elif isinstance(data, dict):
        for value in data.values():
            yield from _all_text(value)
    elif isinstance(data, list):
        for value in data:
            yield from _all_text(value)


def log(data, date, note):
    """Store the current reading and upsert today's history entry."""
    cur = compute(data["dials"], data["iw"])
    data["current"] = cur
    entry = {"date": date, "minutes": cur["minutes"], "sooner": cur["sooner"], "note": note}
    hist = [h for h in data["history"] if h["date"] != date]
    hist.append(entry)
    hist.sort(key=lambda h: h["date"])
    # Keep the Moore reference (minutes is null) plus the newest readings.
    ref = [h for h in hist if h["minutes"] is None]
    rest = [h for h in hist if h["minutes"] is not None][-(MAX_HISTORY - len(ref)):]
    data["history"] = sorted(ref + rest, key=lambda h: h["date"])
    return entry


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    lg = sub.add_parser("log")
    lg.add_argument("--date", required=True)
    lg.add_argument("--note", required=True)
    ap.add_argument("--file", default=str(DATA))
    args = ap.parse_args(argv)

    path = Path(args.file)
    data = json.loads(path.read_text(encoding="utf-8"))
    if args.cmd == "log":
        entry = log(data, args.date, args.note)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"logged {entry}")
    errs = validate(data)
    cur = compute(data["dials"], data["iw"])
    print(f"{cur['minutes']} minutes to midnight | {cur['sooner']} of 13 dials say sooner | "
          f"motive {cur['motive']} | preparation {cur['preparation']}")
    if errs:
        print("\n".join("ERROR: " + e for e in errs), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
