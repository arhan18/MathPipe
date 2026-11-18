"""Furniture regression tests — running headers/footers/folios must never
reach body blocks, in full-document AND single-page/chunked extraction.

Run with: .venv/bin/python -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.understanding.blocks import segment_blocks  # noqa: E402
from src.understanding.text import (  # noqa: E402
    PageText,
    Word,
    _strip_furniture,
    is_furniture_line,
)

H = 792.0  # ICSE-like page height; bottom band starts at 0.80*H = 633.6
W = 612.0


def _w(text: str, x0: float, top: float, size: float = 11.0) -> Word:
    return Word(text, x0, top, x0 + len(text) * size * 0.55, top + size,
                "TimesNewRomanPS-BoldMT", size)


def _line(texts: list[str], top: float, x0: float = 60.0, size: float = 11.0) -> list[Word]:
    out: list[Word] = []
    x = x0
    for t in texts:
        w = _w(t, x, top, size)
        out.append(w)
        x = w.x1 + size * 0.35
    return out


def _page(*lines: list[Word], n: int = 1, h: float = H) -> PageText:
    return PageText(n, W, h, [w for ln in lines for w in ln])


def _kept(page: PageText) -> str:
    dried = _strip_furniture([page])
    return " ".join(w.text for w in dried[0].words)


class TestPerPageFurniture(unittest.TestCase):
    def test_press_folio_code_stripped(self):
        page = _page(_line(["Question", "1", "stem"], 100.0),
                     _line(["T26", "511", "I", "3"], 697.0))
        self.assertNotIn("T26", _kept(page))
        self.assertIn("stem", _kept(page))

    def test_press_folio_with_turn_over_suffix_stripped(self):
        page = _page(_line(["Question", "1", "stem"], 100.0),
                     _line(["T26", "511", "I", "3", "Turn", "Over"], 697.0))
        kept = _kept(page)
        self.assertNotIn("T26", kept)
        self.assertNotIn("Turn", kept)

    def test_turn_over_alone_stripped(self):
        line = _line(["Turn", "Over"], 700.0)
        self.assertTrue(is_furniture_line(line, H))

    def test_continuation_variants_stripped(self):
        for texts in (["P.T.O."], ["Continued"], ["Please", "turn", "over"]):
            with self.subTest(texts=texts):
                self.assertTrue(is_furniture_line(_line(texts, 700.0), H))

    def test_continuation_prose_kept(self):
        # Prose merely containing the words is body content, not furniture.
        line = _line(["Turn", "over", "the", "page", "to", "continue"], 700.0)
        self.assertFalse(is_furniture_line(line, H))

    def test_url_footer_stripped(self):
        line = _line(["CLICK", "HERE", "https://link.amazon/x"], 774.0)
        self.assertTrue(is_furniture_line(line, H))

    def test_facing_page_folio_stripped(self):
        line = _line(["473", "425"], 685.0, x0=154.0)
        line[-1] = Word(line[-1].text, 300.0, line[-1].top, 350.0,
                         line[-1].bottom, line[-1].fontname, line[-1].size)
        self.assertTrue(is_furniture_line(line, H))

    def test_lone_folio_extreme_margin_stripped(self):
        self.assertTrue(is_furniture_line(_line(["9"], 745.0), H))
        self.assertTrue(is_furniture_line(_line(["9/13"], 744.0), H))

    def test_body_outside_band_kept(self):
        # Same shapes above the margin band are never furniture.
        self.assertFalse(is_furniture_line(_line(["Turn", "Over"], 500.0), H))
        self.assertFalse(is_furniture_line(_line(["9"], 500.0), H))


class TestPageFolioFurniture(unittest.TestCase):
    """Exam papers print "Page N of M" in the bottom margin.

    SQP p1: the wrapped tail of the footer note shares the line with the
    folio ("2025-26. Page 1 of 10"), so a full-line rule can never match
    it and the folio used to leak into body text and corrupt the last
    question's paragraph.
    """

    H842 = 842.0

    def test_page_of_footer_line_stripped(self):
        line = _line(["Page", "1", "of", "10"], 795.0)
        self.assertTrue(is_furniture_line(line, self.H842))

    def test_numeric_of_footer_line_stripped(self):
        line = _line(["1", "of", "10"], 795.0)
        self.assertTrue(is_furniture_line(line, self.H842))

    def test_folio_with_wrapped_note_tail_stripped(self):
        line = _line(["2025-26.", "Page", "1", "of", "10"], 795.0)
        self.assertTrue(is_furniture_line(line, self.H842))

    def test_folio_dropped_from_body_keeping_content(self):
        page = _page(_line(["Question", "1", "stem"], 100.0),
                     _line(["2025-26.", "Page", "1", "of", "10"], 795.0),
                     h=self.H842)
        kept = _kept(page)
        self.assertNotIn("Page", kept)
        self.assertNotIn("of", kept.split("stem")[-1])
        self.assertIn("stem", kept)

    def test_body_page_reference_kept(self):
        # Prose that mentions a page number is body content, not furniture.
        line = _line(["see", "page", "3", "of", "10", "for", "details"], 795.0)
        self.assertFalse(is_furniture_line(line, self.H842))

    def test_page_folio_above_band_kept(self):
        # Same shape outside the bottom margin is body content.
        line = _line(["Page", "1", "of", "10"], 500.0)
        self.assertFalse(is_furniture_line(line, self.H842))

    def test_page_folio_repetition_across_pages(self):
        # The page number sits at token #2, so the verbatim 3-token prefix
        # rule can never match ("Page 1 of" vs "Page 2 of"). The digit
        # masked fingerprint restores the repetition signal.
        pages = [
            _page(_line(["Question", "1", "stem"], 100.0),
                  _line(["Page", str(n), "of", "10"], 795.0), n=n, h=self.H842)
            for n in (1, 2, 3)
        ]
        dried = _strip_furniture(pages)
        for p in dried:
            kept = " ".join(w.text for w in p.words)
            self.assertNotIn("Page", kept)
            self.assertIn("stem", kept)

    def test_bottom_most_line_folio_stripped_above_band(self):
        # A folio printed high (wide bottom margin) is still furniture
        # when nothing follows it on the page.
        page = _page(_line(["Question", "1", "stem"], 100.0),
                     _line(["Page", "7", "of", "10"], 700.0), h=self.H842)
        kept = _kept(page)
        self.assertNotIn("Page", kept)
        self.assertIn("stem", kept)

    def test_body_page_reference_not_stripped_as_last_line(self):
        # Body prose that mentions a page number stays body content.
        page = _page(_line(["Question", "1", "stem"], 100.0),
                     _line(["see", "page", "3", "of", "10", "notes"], 700.0),
                     h=self.H842)
        kept = _kept(page)
        self.assertIn("see", kept)
        self.assertIn("stem", kept)


class TestMathContentKept(unittest.TestCase):
    """Shapes that look folio-like but are mathematics must survive."""

    def test_matrix_row_kept(self):
        self.assertFalse(is_furniture_line(_line(["0", "0", "1"], 673.0), H))

    def test_binomial_pair_kept(self):
        # Real geometry: QueBank p70 "9 9" sits at y=769 on H=842
        # (frac 0.91, below the 0.95 pair gate).
        line = _line(["9", "9"], 769.0)
        page = _page(line, h=842.0)
        self.assertFalse(is_furniture_line(line, page.height))

    def test_integral_limit_kept(self):
        self.assertFalse(is_furniture_line(_line(["0"], 730.0), H))

    def test_option_line_kept(self):
        line = _line(["(A)", "1", "(B)", "2"], 700.0)
        self.assertFalse(is_furniture_line(line, H))

    def test_question_label_kept(self):
        line = _line(["17.", "Solve", "for", "x"], 700.0)
        self.assertFalse(is_furniture_line(line, H))

    def test_midpage_lone_number_kept(self):
        # Worksheet number columns (QueBank p91) live mid-page, not in
        # the margin, and are never stripped whatever the band gates do.
        self.assertFalse(is_furniture_line(_line(["11"], 277.0), H))

    def test_shallow_pair_kept(self):
        # Matrix debris below the extreme-margin pair gate.
        self.assertFalse(is_furniture_line(_line(["4", "4"], 737.0), H))


class TestCrossPageStillWorks(unittest.TestCase):
    def test_repeated_prefix_stripped_across_pages(self):
        pages = [
            _page(_line(["Body", f"page{n}"], 100.0),
                  _line(["CLICK", "HERE", "TO", "BUY", f"p{n}"], 774.0), n=n)
            for n in (1, 2, 3)
        ]
        dried = _strip_furniture(pages)
        for p in dried:
            self.assertNotIn("CLICK", " ".join(w.text for w in p.words))
            self.assertIn("Body", " ".join(w.text for w in p.words))

    def test_blocks_drop_single_page_furniture(self):
        page = _page(_line(["16.", "If", "vectors", "are"], 100.0),
                     _line(["T26", "511", "I", "3", "Turn", "Over"], 697.0))
        texts = [b.text for b in segment_blocks(page)]
        self.assertTrue(any("16." in t for t in texts))
        self.assertFalse(any("T26" in t or "Turn Over" in t for t in texts))


if __name__ == "__main__":
    unittest.main()
