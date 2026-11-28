#!/usr/bin/env python3
"""Collect the real titles and publish dates of CASI publications.

CASI published each PDF through an article page on its site that carries the
proper title, the publish date and a short description. This reads the Wayback
Machine's captures of those pages and writes docs/_data/casi_articles.json,
keyed by the PDF's path, so fetch_casi.py can label each file correctly.

Pages are cached under build/casi_pages/, so a re-run only fetches new ones.
Standard library only.
"""

from __future__ import annotations

import datetime as dt
import gzip
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "build" / "casi_pages"
OUT = ROOT / "docs" / "_data" / "casi_articles.json"

CDX = (
    "https://web.archive.org/cdx/search/cdx"
    "?url=airuniversity.af.edu/CASI/*"
    "&output=json&fl=original,timestamp"
    "&filter=statuscode:200&filter=mimetype:text/html&limit=100000"
)
USER_AGENT = "Mozilla/5.0 (compatible; natsec-brief-casi-mirror/1.0)"
TIMEOUT = 120
PAUSE = 2.5
TRIES_PER_ARTICLE = 3  # newest captures to try before giving up on a page


def get(url: str, tries: int = 4) -> bytes:
    delay = 15
    for attempt in range(1, tries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = resp.read()
            return gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data
        except urllib.error.HTTPError as err:
            if err.code == 404 or attempt == tries:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            if attempt == tries:
                raise
        time.sleep(delay)
        delay *= 2
    raise RuntimeError("unreachable")


def pdf_key(href: str) -> str | None:
    """Lowercase decoded path below /Portals/10/CASI/, matching fetch_casi.py."""
    path = urllib.parse.unquote(urllib.parse.urlsplit(html.unescape(href)).path)
    parts = re.split(r"/portals/10/casi/", path, flags=re.I)
    if len(parts) < 2 or not parts[-1].lower().endswith(".pdf"):
        return None
    return parts[-1].lower()


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse(page: str) -> dict | None:
    m = re.search(r"<meta\s+property=['\"]og:title['\"]\s+content=['\"](.*?)['\"]\s*/?>", page, re.S)
    title = clean(m[1]) if m else ""
    if not title:
        m = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
        title = clean(re.sub(r"<[^>]+>", "", m[1])) if m else ""
    date = ""
    m = re.search(r"<time[^>]*datetime=['\"]([^'\"]+)['\"]", page)
    if m:
        raw = clean(m[1])
        for fmt in ("%B %d, %Y", "%b. %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
            try:
                date = dt.datetime.strptime(raw.replace("Sept.", "Sep."), fmt).date().isoformat()
                break
            except ValueError:
                continue
    m = re.search(r"<meta\s+property=['\"]og:description['\"]\s+content=['\"](.*?)['\"]\s*/?>", page, re.S)
    summary = clean(m[1]) if m else ""
    pdfs = []
    for href in re.findall(r"href=['\"]([^'\"]+)['\"]", page):
        key = pdf_key(href)
        if key and key not in pdfs:
            pdfs.append(key)
    if not title:
        return None
    return {"title": title, "date": date, "summary": summary, "pdfs": pdfs}


def main() -> int:
    rows = json.loads(get(CDX))[1:]
    captures: dict[str, list[tuple[str, str]]] = {}
    for original, ts in rows:
        m = re.search(r"/Article/(\d+)", original)
        if m:
            captures.setdefault(m[1], []).append((ts, original))
    print(f"index: {len(captures)} article pages", flush=True)

    CACHE.mkdir(parents=True, exist_ok=True)
    articles, failed = {}, []
    for n, (aid, caps) in enumerate(sorted(captures.items()), 1):
        cached = CACHE / f"{aid}.json"
        if cached.exists():
            articles[aid] = json.loads(cached.read_text(encoding="utf-8"))
            continue
        info = None
        for ts, original in sorted(caps, reverse=True)[:TRIES_PER_ARTICLE]:
            try:
                page = get(f"https://web.archive.org/web/{ts}id_/{original}").decode("utf-8", "replace")
            except Exception as err:  # noqa: BLE001
                last = str(err)
                time.sleep(PAUSE)
                continue
            time.sleep(PAUSE)
            info = parse(page)
            if info:
                info["article_url"] = original.split("?")[0].replace("http://", "https://")
                info["article_wayback"] = f"https://web.archive.org/web/{ts}/{original}"
                break
            last = "no title found"
        if not info:
            failed.append((aid, last))
            print(f"[{n}/{len(captures)}] FAIL {aid}: {last}", flush=True)
            continue
        cached.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
        articles[aid] = info
        print(f"[{n}/{len(captures)}] {info['date'] or '----------'} {info['title'][:80]} ({len(info['pdfs'])} pdf)", flush=True)

    # One entry per PDF. A PDF linked from several pages takes the page that
    # links to the fewest files (its own article, not a roundup).
    by_pdf: dict[str, dict] = {}
    for aid, info in articles.items():
        for key in info["pdfs"]:
            entry = {k: info[k] for k in ("title", "date", "summary", "article_url", "article_wayback")}
            entry["article_id"] = aid
            entry["_n"] = len(info["pdfs"])
            if key not in by_pdf or entry["_n"] < by_pdf[key]["_n"]:
                by_pdf[key] = entry
    for entry in by_pdf.values():
        entry["pdf_count"] = entry.pop("_n")  # how many PDFs that page links

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dict(sorted(by_pdf.items())), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    with_pdf = sum(1 for a in articles.values() if a["pdfs"])
    print(f"\n{len(articles)} pages read, {with_pdf} link to a PDF, {len(by_pdf)} PDFs labelled, {len(failed)} failed")
    for aid, why in failed:
        print(f"  failed: article {aid} ({why})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
