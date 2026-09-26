#!/usr/bin/env python3
"""Pull the feeds listed in feeds.toml and write a ranked list of candidate stories.

The daily routine runs this first, then writes the brief from build/candidates.md.
It uses only the standard library, so a cloud session can run it without a setup
script.

The published briefs double as state: the coverage window starts at the most
recent brief, and any link already cited in the last ten days of briefs is
skipped so a story isn't reported twice.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import email.utils
import html
import html.entities
import re
import sys
import tomllib
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "feeds.toml"
POSTS_DIR = ROOT / "docs" / "_posts"
DEFAULT_OUT = ROOT / "build" / "candidates.md"

EASTERN = ZoneInfo("America/New_York")
USER_AGENT = "Mozilla/5.0 (compatible; natsec-brief/1.0)"
TIMEOUT = 20
MAX_BYTES = 5_000_000
FIRST_RUN_LOOKBACK = dt.timedelta(hours=24)
MAX_LOOKBACK = dt.timedelta(days=4)
WINDOW_OVERLAP = dt.timedelta(hours=1)
SEEN_LOOKBACK_DAYS = 10
SNIPPET_CHARS = 300

TRACKING_PARAM = re.compile(r"^(utm_\w+|fbclid|gclid|mc_cid|mc_eid|cmpid|ref)$")
POST_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-.*\.md$")
MD_LINK = re.compile(r"\]\((https?://[^)\s]+)\)")
REDDIT_TARGET = re.compile(r'<a href="([^"]+)">\s*\[link\]\s*</a>')


@dataclass
class Item:
    title: str
    link: str
    published: dt.datetime
    summary: str
    feed: str
    outlet: str = ""
    score: int = 0
    matched: list[str] = field(default_factory=list)
    also: list[str] = field(default_factory=list)

    @property
    def source(self) -> str:
        return f"{self.outlet} via {self.feed}" if self.outlet else self.feed


# --- parsing -----------------------------------------------------------------


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child(el: ET.Element, *names: str) -> ET.Element | None:
    for c in el:
        if local(c.tag) in names:
            return c
    return None


def text_of(el: ET.Element | None) -> str:
    return "".join(el.itertext()).strip() if el is not None else ""


def clean(s: str, limit: int | None = None) -> str:
    """Strip markup from feed text, which often carries escaped HTML."""
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"<[^>]+>", " ", html.unescape(s))
    s = re.sub(r"\s+", " ", s).strip()
    if limit and len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0] + "..."
    return s


def parse_date(s: str) -> dt.datetime | None:
    s = s.strip()
    if not s:
        return None
    try:
        d = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def entry_link(el: ET.Element) -> str:
    for c in el:
        if local(c.tag) != "link":
            continue
        href = c.get("href")
        if href is None:  # RSS puts the URL in the element text
            if c.text and c.text.strip():
                return c.text.strip()
        elif c.get("rel", "alternate") == "alternate":
            return href.strip()
    guid = text_of(child(el, "guid", "id"))
    return guid if guid.startswith("http") else ""


def _entity_ref(m: re.Match) -> bytes:
    name = m.group(1).decode()
    if name in ("amp", "lt", "gt", "quot", "apos"):
        return m.group(0)
    cp = html.entities.name2codepoint.get(name)
    return f"&#{cp};".encode() if cp else b"&amp;" + m.group(1) + b";"


def xml_root(data: bytes) -> ET.Element:
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        # Some feeds use HTML entities such as &nbsp; that XML doesn't define.
        return ET.fromstring(re.sub(rb"&([A-Za-z][A-Za-z0-9]*);", _entity_ref, data))


def parse_feed(data: bytes, feed_name: str) -> tuple[list[Item], int]:
    """Return (dated items, count of items skipped for having no usable date)."""
    root = xml_root(data)
    items, undated = [], 0
    for el in root.iter():
        if local(el.tag) not in ("item", "entry"):
            continue
        title = clean(text_of(child(el, "title")))
        link = entry_link(el)
        if not title or not link:
            continue
        published = None
        for name in ("pubDate", "published", "updated", "date", "issued", "modified"):
            published = parse_date(text_of(child(el, name)))
            if published:
                break
        if published is None:
            undated += 1
            continue
        summary_el = child(el, "description", "summary")
        if summary_el is None:
            summary_el = child(el, "encoded", "content")
        # Google News puts the publisher in <source> and appends it to the title.
        outlet = ""
        source_el = child(el, "source")
        if local(el.tag) == "item" and source_el is not None:
            outlet = text_of(source_el)
            if outlet and title.endswith(f" - {outlet}"):
                title = title[: -len(outlet) - 3].rstrip()
        summary = clean(text_of(summary_el), SNIPPET_CHARS)
        # Google News snippets are just the headline plus the outlet name.
        if summary.startswith(title) and len(summary) - len(title) <= len(outlet) + 3:
            summary = ""
        if "reddit.com/" in link:
            # A Reddit entry links to its comment thread; the article is the
            # "[link]" anchor in the body. Text, image and video posts are skipped.
            m = REDDIT_TARGET.search(text_of(child(el, "content")))
            target = html.unescape(m.group(1)) if m else ""
            host = urllib.parse.urlsplit(target).netloc.lower().removeprefix("www.")
            if not target or host.endswith(("reddit.com", "redd.it")):
                continue
            link, outlet, summary = target, host, ""
        items.append(Item(title, link, published, summary, feed_name, outlet))
    return items, undated


# --- fetching ----------------------------------------------------------------


def feed_url(feed: dict) -> str:
    if "google_news" in feed:
        query = urllib.parse.urlencode(
            {"q": feed["google_news"], "hl": "en-US", "gl": "US", "ceid": "US:en"}
        )
        return f"https://news.google.com/rss/search?{query}"
    return feed["url"]


def fetch(feed: dict) -> tuple[dict, list[Item], int, str | None]:
    req = urllib.request.Request(
        feed_url(feed),
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = resp.read(MAX_BYTES)
        items, undated = parse_feed(data, feed["name"])
        return feed, items, undated, None
    except Exception as exc:  # one bad feed must never sink the whole run
        return feed, [], 0, f"{type(exc).__name__}: {exc}"[:160]


# --- filtering and scoring ---------------------------------------------------


def normalize_url(url: str) -> str:
    p = urllib.parse.urlsplit(url.strip())
    query = urllib.parse.urlencode(
        [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
         if not TRACKING_PARAM.match(k)]
    )
    host = p.netloc.lower().removeprefix("www.")
    return urllib.parse.urlunsplit(("", host, p.path.rstrip("/") or "/", query, ""))


def title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def compile_groups(groups: list[dict]) -> list[tuple[str, int, list[re.Pattern]]]:
    compiled = []
    for g in groups:
        patterns = []
        for term in g["terms"]:
            word = term.rstrip("*")
            body = re.escape(word) + (r"\w*" if term.endswith("*") else "")
            flags = 0 if word.isupper() else re.IGNORECASE
            patterns.append(re.compile(rf"\b{body}\b", flags))
        compiled.append((g["name"], int(g["weight"]), patterns))
    return compiled


def score(item: Item, groups, boost: int) -> None:
    total = boost
    for name, weight, patterns in groups:
        if any(p.search(item.title) for p in patterns):
            total += weight
        elif any(p.search(item.summary) for p in patterns):
            total += max(1, weight // 2)
        else:
            continue
        item.matched.append(name)
    item.score = total


# --- state from published briefs ---------------------------------------------


def post_files(today: dt.date) -> list[tuple[dt.date, Path]]:
    """Earlier briefs, oldest first. Today's brief is ignored so a re-run regenerates it."""
    posts = []
    for path in POSTS_DIR.glob("*.md"):
        m = POST_NAME.match(path.name)
        if m:
            day = dt.date.fromisoformat(m.group(1))
            if day < today:
                posts.append((day, path))
    return sorted(posts)


def post_time(day: dt.date, path: Path) -> dt.datetime:
    for line in path.read_text(encoding="utf-8").splitlines()[:20]:
        if line.startswith("date:"):
            try:
                return dt.datetime.strptime(line[5:].strip(), "%Y-%m-%d %H:%M:%S %z")
            except ValueError:
                break
    return dt.datetime.combine(day, dt.time(7), EASTERN)


def window_start(now: dt.datetime, posts: list[tuple[dt.date, Path]]) -> dt.datetime:
    start = post_time(*posts[-1]) - WINDOW_OVERLAP if posts else now - FIRST_RUN_LOOKBACK
    return max(start, now - MAX_LOOKBACK)


def seen_links(today: dt.date, posts: list[tuple[dt.date, Path]]) -> set[str]:
    cutoff = today - dt.timedelta(days=SEEN_LOOKBACK_DAYS)
    seen = set()
    for day, path in posts:
        if day >= cutoff:
            seen.update(normalize_url(u) for u in MD_LINK.findall(path.read_text(encoding="utf-8")))
    return seen


# --- output ------------------------------------------------------------------


def fmt_et(d: dt.datetime) -> str:
    return d.astimezone(EASTERN).strftime("%a %b %d %H:%M ET")


def render(now, start, candidates, health, stats) -> str:
    now_et = now.astimezone(EASTERN)
    ok = [h for h in health if h[2] is None]
    failed = [h for h in health if h[2] is not None]
    lines = [
        "# Candidates for the NatSec Brief",
        "",
        f"- Brief file: docs/_posts/{now_et:%Y-%m-%d}-brief.md",
        f"- Front matter date: {now_et:%Y-%m-%d %H:%M:%S %z}",
        f"- Title date: {now_et:%A, %B} {now_et.day}, {now_et.year}",
        f"- Window: {fmt_et(start)} to {fmt_et(now)}",
        f"- Feeds: {len(ok)} of {len(health)} fetched",
        f"- Items: {stats['fetched']} fetched, {stats['in_window']} in window, "
        f"{stats['seen']} already covered, {stats['low_score']} off-topic, "
        f"{stats['dupes']} duplicates merged, {len(candidates)} candidates below",
        "",
    ]
    if failed:
        lines += ["## Failed feeds", ""]
        lines += [f"- {name}: {err}" for name, _, err in failed]
        lines.append("")
    lines += ["## Candidates (highest score first)", ""]
    for n, it in enumerate(candidates, 1):
        tags = ", ".join(it.matched) or "none"
        also = f" | also: {', '.join(it.also)}" if it.also else ""
        lines.append(f"{n}. [{it.score}] {it.title}")
        lines.append(f"   {it.source} | {fmt_et(it.published)} | {tags}{also}")
        lines.append(f"   {it.link}")
        if it.summary:
            lines.append(f"   {it.summary}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--now", help="pretend the run happens at this ISO 8601 time (for testing)")
    args = ap.parse_args(argv)

    now = dt.datetime.fromisoformat(args.now) if args.now else dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=EASTERN)
    today = now.astimezone(EASTERN).date()

    cfg = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    groups = compile_groups(cfg["scoring"]["groups"])
    min_score = int(cfg["scoring"]["min_score"])
    posts = post_files(today)
    start = window_start(now, posts)
    seen = seen_links(today, posts)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(fetch, cfg["feeds"]))

    stats = dict.fromkeys(("fetched", "in_window", "seen", "low_score", "dupes"), 0)
    health = []
    by_title: dict[str, Item] = {}
    by_link: dict[str, Item] = {}
    for feed, items, undated, error in results:
        health.append((feed["name"], len(items), error))
        stats["fetched"] += len(items) + undated
        for it in items:
            if not start <= it.published <= now + dt.timedelta(hours=1):
                continue
            stats["in_window"] += 1
            link_key = normalize_url(it.link)
            if link_key in seen:
                stats["seen"] += 1
                continue
            score(it, groups, int(feed.get("boost", 0)))
            if it.score < min_score:
                stats["low_score"] += 1
                continue
            key = title_key(it.title)
            first = by_title.get(key) or by_link.get(link_key)
            if first:
                stats["dupes"] += 1
                # Prefer a direct publisher link over a Google News redirect.
                if "news.google.com" in first.link and "news.google.com" not in it.link:
                    first.link, first.feed, first.outlet = it.link, it.feed, it.outlet
                # Pickup by another outlet is a signal the story matters.
                other = it.outlet or it.feed
                if other != (first.outlet or first.feed) and other not in first.also:
                    first.also.append(other)
                    first.score += 1
                continue
            by_title[key] = by_link[link_key] = it

    candidates = sorted(by_title.values(), key=lambda i: (-i.score, -i.published.timestamp()))
    candidates = candidates[: int(cfg["scoring"]["max_candidates"])]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(now, start, candidates, health, stats), encoding="utf-8")

    failed = sum(1 for h in health if h[2])
    print(f"{len(candidates)} candidates written to {args.out}")
    print(f"feeds: {len(health) - failed} ok, {failed} failed")
    for name, _, err in health:
        if err:
            print(f"  FAILED {name}: {err}")
    return 0 if failed < len(health) else 1


if __name__ == "__main__":
    sys.exit(main())
