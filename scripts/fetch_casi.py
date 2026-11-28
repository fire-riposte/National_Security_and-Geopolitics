#!/usr/bin/env python3
"""Mirror the China Aerospace Studies Institute (CASI) publications.

CASI's site blocks scripted requests, so this pulls the PDFs from the Internet
Archive's Wayback Machine instead. It asks the Wayback index for every PDF
captured under airuniversity.af.edu/Portals/10/CASI/, keeps the newest good
capture of each file, drops byte-identical duplicates, and saves the files
into a checkout of the separate casi-archive repo (--dest, by default
../casi-archive/files). The PDFs stay out of this repo so the daily routine
doesn't clone them. The catalog page reads docs/_data/casi.json, which this
script writes.

Safe to re-run: files already on disk are skipped. Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEST = ROOT.parent / "casi-archive" / "files"
MANIFEST = ROOT / "docs" / "_data" / "casi.json"
MISSING = ROOT / "docs" / "_data" / "casi_missing.json"
ARTICLES = ROOT / "docs" / "_data" / "casi_articles.json"  # from fetch_casi_meta.py

CDX = (
    "https://web.archive.org/cdx/search/cdx"
    "?url=airuniversity.af.edu/Portals/10/CASI/*"
    "&output=json&fl=original,timestamp,digest,length"
    "&filter=statuscode:200&filter=mimetype:application/pdf&limit=50000"
)
USER_AGENT = "Mozilla/5.0 (compatible; natsec-brief-casi-mirror/1.0)"
TIMEOUT = 120
PAUSE = 3.0  # seconds between downloads, to stay polite to archive.org
MAX_FILE = 95_000_000  # GitHub rejects files over 100 MB

# Source folder (lowercase) -> (slug, display name). First match wins.
CATEGORIES = [
    ("documents/translations", ("translations", "In Their Own Words (translations)")),
    ("documents/ translations", ("translations", "In Their Own Words (translations)")),
    ("documents/research/casi articles", ("articles", "CASI Articles")),
    ("documents/research/plaaf", ("plaaf", "PLA Air Force")),
    ("documents/research/plan_aviation", ("plan", "PLA Navy")),
    ("documents/research/plan", ("plan", "PLA Navy")),
    ("documents/research/plarf", ("plarf", "PLA Rocket Force")),
    ("documents/research/plassf", ("plassf", "PLA Strategic Support Force")),
    ("documents/research/space", ("space", "Space")),
    ("documents/research/cyber", ("cyber", "Cyber")),
    ("documents/research/infrastructure", ("infrastructure", "Infrastructure")),
    ("documents/research/pacaf state of the game", ("pacaf", "PACAF State of the Game")),
    ("documents/research/other", ("other-topics", "Other Topics")),
    ("documents/research", ("research", "Research")),
    ("documents/toolkit", ("toolkit", "Toolkit Presentations")),
    ("documents/thoughts from the chairman", ("chairman", "Thoughts from the Chairman")),
    ("documents/admin", ("admin", "Admin and Quarterly Updates")),
    ("conference", ("conference", "Conference Papers")),
    ("books", ("books", "Books")),
    ("documents", ("reports", "Reports")),
]


def get(url: str, tries: int = 5) -> bytes:
    """Fetch a URL, backing off when archive.org throttles or stumbles."""
    delay = 15
    for attempt in range(1, tries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read()
        except urllib.error.HTTPError as err:
            if err.code == 404 or attempt == tries:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            if attempt == tries:
                raise
        time.sleep(delay)
        delay *= 2
    raise RuntimeError("unreachable")


def rel_path(original: str) -> str:
    """Decoded path below /Portals/10/CASI/, without the query string."""
    path = urllib.parse.urlsplit(original).path
    path = urllib.parse.unquote(path)
    return re.split(r"/portals/10/casi/", path, flags=re.I)[-1]


def categorize(rel: str) -> tuple[str, str]:
    folder = rel.rsplit("/", 1)[0].lower() if "/" in rel else ""
    for prefix, cat in CATEGORIES:
        if folder.startswith(prefix):
            return cat
    return ("reports", "Reports")


def slugify(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:110].strip("-") or "untitled"


def title_and_date(filename: str) -> tuple[str, str]:
    stem = re.sub(r"\.pdf$", "", filename, flags=re.I)
    date = ""
    m = re.match(r"^\s*(\d{4})[-_.]?(\d{2})[-_.]?(\d{2})(?!\d)[\s_\-.]*", stem)
    if m and 1990 <= int(m[1]) <= 2030 and 1 <= int(m[2]) <= 12 and 1 <= int(m[3]) <= 31:
        date = f"{m[1]}-{m[2]}-{m[3]}"
        stem = stem[m.end():]
    title = re.sub(r"[_\s]+", " ", stem).strip(" -")
    if not date:
        # "2020-10 PACAF State of the Game", "1998 White Paper": sortable, title unchanged
        m = re.match(r"^((?:19|20)\d{2})(?:[-_ ]?(0[1-9]|1[0-2])(?!\d))?(?!\d)", title)
        if m:
            date = m[1] + (f"-{m[2]}" if m[2] else "")
    return title or filename, date


def alternates(caps: list[list[str]], chosen_digest: str) -> list[tuple[str, str]]:
    best: dict[str, list[str]] = {}
    for cap in caps:
        if cap[2] != chosen_digest and (cap[2] not in best or cap[1] > best[cap[2]][1]):
            best[cap[2]] = cap
    ordered = sorted(best.values(), key=lambda c: int(c[3]) if c[3].isdigit() else 0, reverse=True)
    return [(c[1], c[0]) for c in ordered]


def complete_pdf(data: bytes) -> bool:
    """A whole PDF starts with %PDF and ends with an %%EOF marker. Some Wayback
    captures were cut off at 1 MB and lack the ending."""
    return b"%PDF" in data[:1024] and b"%%EOF" in data[-4096:]


def pdf_created(data: bytes) -> str:
    """The creation date stored inside the PDF, as YYYY-MM-DD, or ''."""
    m = re.search(rb"/CreationDate\s*\(D:(\d{4})(\d{2})(\d{2})", data)
    if not m:
        m = re.search(rb"<xmp:CreateDate>(\d{4})-(\d{2})-(\d{2})", data)
    if not m:
        return ""
    y, mo, d = (int(g) for g in m.groups())
    if not (1990 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31):
        return ""
    return f"{y:04d}-{mo:02d}-{d:02d}"


def best_date(item: dict, data: bytes) -> tuple[str, str]:
    """Pick the most trustworthy date and say where it came from.

    Order: the article page's publish date, a full date in the file name, the
    PDF's own creation date, then a year or year-month from the file name. A
    file-name year wins over a PDF creation date from a different year, since
    old documents were often scanned or re-saved long after they came out.
    """
    name_date = item["name_date"]
    if item["article_date"] and not (item["article_pdfs"] > 1 and name_date):
        return item["article_date"], "article page"
    if len(name_date) == 10:
        return name_date, "file name"
    created = pdf_created(data)
    if created and (not name_date or created.startswith(name_date[:4])):
        return created, "PDF creation date"
    if name_date:
        return name_date, "file name"
    return "", ""


def fetch_best(item: dict) -> tuple[bytes, str, str]:
    """Try the newest capture, then the alternates, until one is a complete PDF."""
    tries = [(item["captured_ts"], item["original"])] + item["alternates"]
    last = "no captures"
    for ts, original in tries:
        try:
            data = get(f"https://web.archive.org/web/{ts}id_/{original}")
        except Exception as err:  # noqa: BLE001
            last = str(err)
            continue
        finally:
            time.sleep(PAUSE)
        if complete_pdf(data):
            return data, ts, original
        last = "incomplete PDF (capture cut off)" if b"%PDF" in data[:1024] else "not a PDF"
    raise RuntimeError(last)


def loose(key: str) -> str:
    """Path key that ignores the space/underscore/dash spellings CASI mixed."""
    return re.sub(r"[\s_\-]+", " ", key).strip()


def index() -> list[dict]:
    rows = json.loads(get(CDX))[1:]
    newest: dict[str, list[str]] = {}
    captures: dict[str, list[list[str]]] = {}
    for original, ts, digest, length in rows:
        key = rel_path(original).lower()
        captures.setdefault(key, []).append([original, ts, digest, length])
        if key not in newest or ts > newest[key][1]:
            newest[key] = [original, ts, digest, length]
    # Real titles and dates from CASI's article pages, where a page links the PDF.
    meta = json.loads(ARTICLES.read_text(encoding="utf-8")) if ARTICLES.exists() else {}
    meta_loose = {loose(k): v for k, v in meta.items()}

    def lookup(k: str) -> dict:
        return meta.get(k) or meta_loose.get(loose(k)) or {}

    # CASI posted some files at more than one address. Every address with the
    # same content shares whatever article page links to any of them.
    by_digest: dict[str, list[str]] = {}
    for key in sorted(newest):
        for cap in captures[key]:
            if key not in by_digest.setdefault(cap[2], []):
                by_digest[cap[2]].append(key)

    seen: set[str] = set()
    items = []
    for key in sorted(newest):
        original, ts, digest, length = newest[key]
        if digest in seen:
            continue
        seen.add(digest)
        # Label and file the document by the address its article page links to.
        best_key = next((k for k in [key] + by_digest[digest] if lookup(k)), key)
        article = lookup(best_key)
        rel = rel_path(original)
        filename = rel.rsplit("/", 1)[-1]
        slug, _ = categorize(rel)  # folder on disk: stays put once downloaded
        _, cat_name = categorize(best_key)
        title, date = title_and_date(filename)
        title_source = "article page" if article.get("title") else "file name"
        if article.get("title"):
            if article.get("pdf_count", 1) > 1:
                # A page that links several files: keep each file's own name too.
                title = f"{title} ({article['title']})"
            else:
                title = article["title"]
        items.append({
            "title": title,
            "article_date": article.get("date", ""),
            "article_pdfs": article.get("pdf_count", 1),
            "name_date": date,
            "title_source": title_source,
            "summary": article.get("summary", ""),
            "article_url": article.get("article_url", ""),
            "article_wayback": article.get("article_wayback", ""),
            "category": slug,
            "category_name": cat_name,
            "source_url": original.split("?")[0].replace("http://", "https://"),
            "wayback_url": f"https://web.archive.org/web/{ts}/{original}",
            "captured_ts": ts,
            "original": original,
            "stem": slugify(re.sub(r"\.pdf$", "", filename, flags=re.I)),
            # Other captures of the same file, biggest first, one per distinct content.
            "alternates": alternates(captures[key], digest),
        })
    # Publications an article page links to that the Wayback Machine never saved.
    have = {loose(k) for keys in by_digest.values() for k in keys}
    missing = [
        {"title": v["title"], "date": v["date"], "file": k.rsplit("/", 1)[-1],
         "article_wayback": v["article_wayback"]}
        for k, v in sorted(meta.items(), key=lambda kv: kv[1]["date"], reverse=True)
        if loose(k) not in have
    ]
    MISSING.parent.mkdir(parents=True, exist_ok=True)
    MISSING.write_text(json.dumps(missing, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST,
                        help="folder for the PDFs: files/ in a checkout of the casi-archive repo")
    parser.add_argument("--limit", type=int, default=0, help="stop after N new downloads")
    args = parser.parse_args()

    items = index()
    print(f"index: {len(items)} unique PDFs", flush=True)

    used: set[str] = set()
    done, failed, fetched = [], [], 0
    for n, item in enumerate(items, 1):
        path = f"{item['category']}/{item['stem']}.pdf"
        bump = 2
        while path in used:
            path = f"{item['category']}/{item['stem']}-{bump}.pdf"
            bump += 1
        used.add(path)
        dest = args.dest / path

        if dest.exists() and not complete_pdf(dest.read_bytes()):
            dest.unlink()  # cut-off copy from an earlier run
        sidecar = dest.with_suffix(".capture")
        if not dest.exists():
            if args.limit and fetched >= args.limit:
                continue
            try:
                data, ts, original = fetch_best(item)
            except Exception as err:  # noqa: BLE001 - report and move on
                failed.append((item["source_url"], str(err)))
                print(f"[{n}/{len(items)}] FAIL {path}: {err}", flush=True)
                continue
            if len(data) > MAX_FILE:
                failed.append((item["source_url"], f"too large ({len(data)} bytes)"))
                print(f"[{n}/{len(items)}] SKIP {path}: too large", flush=True)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            if ts != item["captured_ts"]:
                sidecar.write_text(f"{ts} {original}\n", encoding="utf-8")
            fetched += 1
            print(f"[{n}/{len(items)}] ok {path} ({len(data) // 1024} KB)", flush=True)

        # If an older capture had to be used, cite that one.
        ts, original = item["captured_ts"], item["original"]
        if sidecar.exists():
            ts, original = sidecar.read_text(encoding="utf-8").split(maxsplit=1)
            original = original.strip()
        item["wayback_url"] = f"https://web.archive.org/web/{ts}/{original}"
        item["captured"] = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"

        data = dest.read_bytes()
        item["date"], item["date_source"] = best_date(item, data)
        done.append({
            "title": item["title"],
            "date": item["date"],
            "date_source": item["date_source"],
            "title_source": item["title_source"],
            "summary": item["summary"],
            "article_url": item["article_url"],
            "article_wayback": item["article_wayback"],
            "category": item["category"],
            "category_name": item["category_name"],
            "path": path,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "source_url": item["source_url"],
            "wayback_url": item["wayback_url"],
            "captured": item["captured"],
        })

    done.sort(key=lambda d: (d["category_name"], d["date"] or "0000", d["title"].lower()))
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(done, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    total = sum(d["bytes"] for d in done)
    print(f"\non disk: {len(done)} files, {total / 1e6:.0f} MB; new this run: {fetched}; failed: {len(failed)}")
    for url, why in failed:
        print(f"  failed: {url} ({why})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
