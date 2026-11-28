import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch_casi as fc  # noqa: E402
import fetch_casi_meta as fm  # noqa: E402


class TitleAndDate(unittest.TestCase):
    def test_full_date_prefix_is_removed_from_title(self):
        self.assertEqual(fc.title_and_date("2021-02-08 Chinese Military Thoughts.pdf"),
                         ("Chinese Military Thoughts", "2021-02-08"))
        self.assertEqual(fc.title_and_date("20171026_PLA-Naval-Aviation.pdf"),
                         ("PLA-Naval-Aviation", "2017-10-26"))

    def test_partial_dates_stay_in_title(self):
        self.assertEqual(fc.title_and_date("2020-10 PACAF State of the Game.pdf"),
                         ("2020-10 PACAF State of the Game", "2020-10"))
        self.assertEqual(fc.title_and_date("1998 White Paper - Chinese.pdf"),
                         ("1998 White Paper - Chinese", "1998"))

    def test_no_date(self):
        self.assertEqual(fc.title_and_date("CASI_Primer 2017.pdf"), ("CASI Primer 2017", ""))


class PdfTitle(unittest.TestCase):
    TITLES = {"books/little-eagles.pdf": "China's \"Little Eagles\""}

    def test_pdf_title_replaces_file_name(self):
        item = {"title": "Little Eagles", "title_source": "file name"}
        self.assertEqual(fc.pdf_title(item, "books/little-eagles.pdf", self.TITLES),
                         ("China's \"Little Eagles\"", "PDF"))

    def test_article_page_title_wins(self):
        item = {"title": "From the page", "title_source": "article page"}
        self.assertEqual(fc.pdf_title(item, "books/little-eagles.pdf", self.TITLES),
                         ("From the page", "article page"))

    def test_no_entry_keeps_file_name(self):
        item = {"title": "Other", "title_source": "file name"}
        self.assertEqual(fc.pdf_title(item, "books/other.pdf", self.TITLES), ("Other", "file name"))


class BestDate(unittest.TestCase):
    PDF = b"%PDF-1.7 /CreationDate (D:20150302120000) %%EOF"

    def item(self, article="", name="", pdfs=1):
        return {"article_date": article, "name_date": name, "article_pdfs": pdfs}

    def test_article_page_wins(self):
        self.assertEqual(fc.best_date(self.item("2020-11-20", "2020-11-18"), self.PDF),
                         ("2020-11-20", "article page"))

    def test_roundup_page_defers_to_file_name(self):
        self.assertEqual(fc.best_date(self.item("2020-11-20", "1998", pdfs=13), self.PDF),
                         ("1998", "file name"))

    def test_pdf_date_fills_in_when_nothing_else(self):
        self.assertEqual(fc.best_date(self.item(), self.PDF), ("2015-03-02", "PDF creation date"))

    def test_pdf_date_refines_matching_year_only(self):
        self.assertEqual(fc.best_date(self.item(name="2015"), self.PDF), ("2015-03-02", "PDF creation date"))
        self.assertEqual(fc.best_date(self.item(name="1998"), self.PDF), ("1998", "file name"))


class CompletePdf(unittest.TestCase):
    def test_cut_off_capture_is_rejected(self):
        self.assertTrue(fc.complete_pdf(b"%PDF-1.4 body %%EOF\n"))
        self.assertFalse(fc.complete_pdf(b"%PDF-1.4 body" + b"x" * 5000))
        self.assertFalse(fc.complete_pdf(b"<html>Not found</html>"))


class ArticlePage(unittest.TestCase):
    PAGE = """<meta property='og:title' content='ITOW:&#32;Legal&#32;Warfare' />
    <meta property='og:description' content='A&#32;translation.' />
    <time pubdate datetime="April 27, 2026">April 27, 2026</time>
    <a href="/Portals/10/CASI/documents/Translations/2026-04-27 ITOW Legal Warfare.pdf?ver=abc">PDF</a>"""

    def test_parse(self):
        info = fm.parse(self.PAGE)
        self.assertEqual(info["title"], "ITOW: Legal Warfare")
        self.assertEqual(info["date"], "2026-04-27")
        self.assertEqual(info["summary"], "A translation.")
        self.assertEqual(info["pdfs"], ["documents/translations/2026-04-27 itow legal warfare.pdf"])

    def test_loose_key_ignores_spelling_of_separators(self):
        self.assertEqual(fc.loose("books/primer_2nd-edition web.pdf"), fc.loose("books/primer 2nd edition_web.pdf"))


if __name__ == "__main__":
    unittest.main()
