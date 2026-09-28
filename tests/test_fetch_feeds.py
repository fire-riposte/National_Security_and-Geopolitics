import contextlib
import datetime as dt
import io
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch_feeds as ff  # noqa: E402

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Test</title>
<item>
  <title>Ex-Army analyst charged with spying for China - Reuters</title>
  <link>https://news.google.com/rss/articles/abc</link>
  <pubDate>Mon, 28 Sep 2026 10:00:00 GMT</pubDate>
  <description>&lt;a href="x"&gt;Ex-Army analyst charged with spying for China&lt;/a&gt;</description>
  <source url="https://www.reuters.com">Reuters</source>
</item>
<item>
  <title>Local bakery wins award</title>
  <link>https://example.com/bakery?utm_source=rss</link>
  <pubDate>Mon, 28 Sep 2026 09:00:00 GMT</pubDate>
  <description>&lt;p&gt;Bread &amp;amp; butter.&lt;/p&gt;</description>
</item>
<item><title>No date here</title><link>https://example.com/undated</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Test</title>
<entry>
  <title>PLA drills near Taiwan</title>
  <link rel="self" href="https://example.org/self"/>
  <link href="https://example.org/pla-drills"/>
  <updated>2026-09-28T08:30:00Z</updated>
  <summary>Chinese forces staged exercises.</summary>
</entry>
</feed>"""


REDDIT = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>espionage</title>
<entry>
  <content type="html">submitted by &lt;a href=&quot;https://www.reddit.com/user/someone&quot;&gt; /u/someone &lt;/a&gt; &lt;br/&gt; &lt;span&gt;&lt;a href=&quot;https://www.nytimes.com/2026/09/27/us/spy.html?a=1&amp;amp;b=2&quot;&gt;[link]&lt;/a&gt;&lt;/span&gt; &lt;span&gt;&lt;a href=&quot;https://www.reddit.com/r/espionage/comments/abc/x/&quot;&gt;[comments]&lt;/a&gt;&lt;/span&gt;</content>
  <link href="https://www.reddit.com/r/espionage/comments/abc/x/"/>
  <published>2026-09-27T15:00:00+00:00</published>
  <title>How a CIA officer was turned</title>
</entry>
<entry>
  <content type="html">&lt;div&gt;Any good spy novels?&lt;/div&gt; &lt;span&gt;&lt;a href=&quot;https://www.reddit.com/r/espionage/comments/def/y/&quot;&gt;[link]&lt;/a&gt;&lt;/span&gt;</content>
  <link href="https://www.reddit.com/r/espionage/comments/def/y/"/>
  <published>2026-09-27T16:00:00+00:00</published>
  <title>Any good spy novels?</title>
</entry>
</feed>"""


def groups():
    return ff.compile_groups([
        {"name": "espionage", "weight": 5, "terms": ["spying", "MSS", "APT*"]},
        {"name": "adversaries", "weight": 3, "terms": ["China", "Iran*", "PLA"]},
    ])


class ParseTests(unittest.TestCase):
    def test_rss(self):
        items, undated = ff.parse_feed(RSS, "Feed")
        self.assertEqual(undated, 1)
        self.assertEqual(len(items), 2)
        gn = items[0]
        self.assertEqual(gn.title, "Ex-Army analyst charged with spying for China")
        self.assertEqual(gn.outlet, "Reuters")
        self.assertEqual(gn.summary, "")  # headline echo is dropped
        self.assertEqual(gn.published, dt.datetime(2026, 9, 28, 10, tzinfo=dt.timezone.utc))
        self.assertEqual(items[1].summary, "Bread & butter.")

    def test_atom_prefers_alternate_link(self):
        items, _ = ff.parse_feed(ATOM, "Feed")
        self.assertEqual(items[0].link, "https://example.org/pla-drills")
        self.assertEqual(items[0].published.hour, 8)

    def test_reddit_uses_article_link_and_skips_text_posts(self):
        items, _ = ff.parse_feed(REDDIT, "Reddit r/espionage")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].link, "https://www.nytimes.com/2026/09/27/us/spy.html?a=1&b=2")
        self.assertEqual(items[0].outlet, "nytimes.com")
        self.assertEqual(items[0].source, "nytimes.com via Reddit r/espionage")


    def test_html_entities_and_headline_led_summaries(self):
        feed = (b'<rss><channel><item><title>Navy&nbsp;update</title>'
                b'<link>https://example.com/n</link><pubDate>Mon, 28 Sep 2026 10:00:00 GMT</pubDate>'
                b'<description>Navy update: the fleet sails&hellip; &bogus; today.</description>'
                b'</item></channel></rss>')
        items, _ = ff.parse_feed(feed, "Feed")
        self.assertEqual(items[0].title, "Navy update")  # &nbsp; becomes a plain space
        self.assertEqual(items[0].summary, "Navy update: the fleet sails\u2026 &bogus; today.")


class ScoringTests(unittest.TestCase):
    def item(self, title, summary=""):
        return ff.Item(title, "https://x", dt.datetime.now(dt.timezone.utc), summary, "Feed")

    def test_headline_counts_full_snippet_half(self):
        it = self.item("Spying case", "Linked to China")
        ff.score(it, groups(), boost=0)
        self.assertEqual(it.score, 5 + 1)
        self.assertEqual(it.matched, ["espionage", "adversaries"])

    def test_acronyms_are_case_sensitive(self):
        it = self.item("Pla and mss are not acronyms here")
        ff.score(it, groups(), boost=0)
        self.assertEqual(it.score, 0)

    def test_prefix_terms(self):
        it = self.item("Iranian hackers tied to APT34")
        ff.score(it, groups(), boost=1)
        self.assertEqual(it.score, 1 + 5 + 3)

    def test_negative_groups_subtract_even_from_the_snippet(self):
        g = ff.compile_groups([
            {"name": "espionage", "weight": 5, "terms": ["spy"]},
            {"name": "noise", "weight": -8, "terms": ["thriller*"]},
        ])
        headline = self.item("Spy thriller tops the charts")
        ff.score(headline, g, boost=0)
        self.assertEqual(headline.score, 5 - 8)
        snippet = self.item("Spy drama", "A thriller")
        ff.score(snippet, g, boost=0)
        self.assertEqual(snippet.score, 5 - 4)

    def test_normalize_url_drops_tracking(self):
        self.assertEqual(
            ff.normalize_url("https://www.Example.com/a/?utm_source=x&id=2#frag"),
            ff.normalize_url("http://example.com/a?id=2"),
        )


class FeedUrlTests(unittest.TestCase):
    def test_google_news_defaults_to_us_english(self):
        url = ff.feed_url({"google_news": "spy"})
        self.assertIn("hl=en-US&gl=US&ceid=US%3Aen", url)

    def test_google_news_locale(self):
        url = ff.feed_url({"google_news": "Spionage", "locale": "de-DE"})
        self.assertIn("hl=de-DE&gl=DE&ceid=DE%3Ade", url)


# Checks against the real feeds.toml, for terms with more than one meaning.
class ConfigTermTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = tomllib.loads(ff.CONFIG.read_text(encoding="utf-8"))
        cls.groups = ff.compile_groups(cfg["scoring"]["groups"])
        cls.min_score = int(cfg["scoring"]["min_score"])

    def scored(self, title):
        it = ff.Item(title, "https://x", dt.datetime.now(dt.timezone.utc), "", "Feed")
        ff.score(it, self.groups, boost=0)
        return it

    def test_bnd_bond_fund_is_noise(self):
        it = self.scored("Vanguard Total Bond Market (BND) yield climbs")
        self.assertIn("noise", it.matched)
        self.assertLess(it.score, self.min_score)

    def test_uk_vanguard_submarines_are_not_noise(self):
        it = self.scored("HMS Vanguard returns from record Trident patrol")
        self.assertNotIn("noise", it.matched)

    def test_gba_is_not_the_federal_prosecutor(self):
        it = self.scored("Nintendo brings GBA classics to Switch Online")
        self.assertNotIn("germany-israel", it.matched)

    def test_federal_prosecutor(self):
        it = self.scored("Bundesanwaltschaft erhebt Anklage gegen mutmaßlichen Spion")
        self.assertIn("germany-israel", it.matched)


class EndToEndTests(unittest.TestCase):
    def test_window_seen_links_and_dedupe(self):
        with tempfile.TemporaryDirectory() as tmp:
            posts = Path(tmp) / "_posts"
            posts.mkdir()
            (posts / "2026-09-25-brief.md").write_text(
                "---\ndate: 2026-09-25 06:45:00 -0400\n---\n"
                "Old story ([Example](https://example.org/pla-drills))\n"
            )
            out = Path(tmp) / "candidates.md"

            def fake_fetch(feed):
                if feed["name"] == "SpyTalk":
                    items, undated = ff.parse_feed(RSS, feed["name"])
                    return feed, items, undated, None
                if feed["name"] == "The Cipher Brief":
                    items, undated = ff.parse_feed(ATOM, feed["name"])
                    return feed, items, undated, None
                if feed["name"] == "Google News: espionage":
                    # The same story, picked up by a second outlet
                    items, undated = ff.parse_feed(RSS.replace(b"Reuters", b"AP"), feed["name"])
                    return feed, items, undated, None
                return feed, [], 0, "URLError: blocked"

            with mock.patch.object(ff, "POSTS_DIR", posts), mock.patch.object(ff, "fetch", fake_fetch), \
                    contextlib.redirect_stdout(io.StringIO()):
                ff.main(["--now", "2026-09-28T06:45:00-04:00", "--out", str(out)])

            text = out.read_text()
            self.assertIn("Brief file: docs/_posts/2026-09-28-brief.md", text)
            self.assertIn("Title date: Monday, September 28, 2026", text)
            self.assertIn("Window: Fri Sep 25 05:45 ET to Mon Sep 28 06:45 ET", text)
            self.assertIn("Ex-Army analyst charged with spying for China", text)
            self.assertIn("also: AP", text)
            self.assertIn("Local bakery wins award", text)  # SpyTalk's boost keeps it
            self.assertNotIn("PLA drills near Taiwan", text)  # already cited in last brief
            self.assertIn("## Failed feeds", text)
            self.assertIn("- SpyTalk: 3 fetched, newest Mon Sep 28 06:00 ET, 2 in window, 2 in candidates", text)
            self.assertIn("- CyberScoop: FAILED URLError: blocked", text)


class WindowTests(unittest.TestCase):
    def test_first_run_on_monday_covers_the_weekend(self):
        monday = dt.datetime(2026, 9, 28, 6, 45, tzinfo=ff.EASTERN)
        self.assertEqual(ff.window_start(monday, []), monday - dt.timedelta(hours=72))
        tuesday = monday + dt.timedelta(days=1)
        self.assertEqual(ff.window_start(tuesday, []), tuesday - dt.timedelta(hours=24))


class FeedCapTests(unittest.TestCase):
    def test_max_items_keeps_the_best_scoring_items(self):
        rss = [b'<rss><channel>']
        for n in range(5):
            spy = b" spy" if n % 2 == 0 else b""
            rss.append(b"<item><title>Story %d%s about China</title><link>https://example.com/%d</link>"
                       b"<pubDate>Mon, 28 Sep 2026 0%d:00:00 GMT</pubDate></item>" % (n, spy, n, n))
        rss.append(b"</channel></rss>")
        data = b"".join(rss)

        def fake_fetch(feed):
            if feed["name"] == "Google News: espionage":
                items, undated = ff.parse_feed(data, feed["name"])
                return feed, items, undated, None
            return feed, [], 0, "URLError: blocked"

        cfg = {"scoring": {"min_score": 1, "max_candidates": 50, "groups": [
                   {"name": "espionage", "weight": 5, "terms": ["spy"]},
                   {"name": "adversaries", "weight": 3, "terms": ["China"]}]},
               "feeds": [{"name": "Google News: espionage", "url": "x", "boost": 0, "max_items": 2}]}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "c.md"
            with mock.patch.object(ff, "POSTS_DIR", Path(tmp)), mock.patch.object(ff, "fetch", fake_fetch), \
                    mock.patch.object(ff.tomllib, "loads", return_value=cfg), \
                    contextlib.redirect_stdout(io.StringIO()):
                ff.main(["--now", "2026-09-28T06:45:00-04:00", "--out", str(out)])
            text = out.read_text()
        # Stories 0, 2 and 4 mention spy (score 8); the cap keeps the two newest of them.
        self.assertIn("Story 4 spy", text)
        self.assertIn("Story 2 spy", text)
        self.assertNotIn("Story 0 spy", text)
        self.assertNotIn("Story 1 about", text)
        self.assertIn("3 over a feed's cap", text)


if __name__ == "__main__":
    unittest.main()
