"""ADR-3 span detector tests.

Losslessness is checked against real pdfplumber-extracted lines from the
reference PDFs (guarded so the suite still runs without them); behavioural
tests use the exact PDF-extracted strings the feature exists for.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.mathengine.spans import Span, classify_token, split_math_spans  # noqa: E402

PDF_DIR = os.path.expanduser("~/Downloads/Tests for maths converter")
_PDFS = [
    "MathSample.pdf",
    "Mathematics - II.pdf",
    "Maths-SQP.pdf",
    "ICSE sample .pdf",
    "2025112060.pdf",
]


def _pdf_lines(max_lines: int = 120) -> list[str]:
    """Substantial text lines from the first pages of every available PDF."""
    import pdfplumber

    lines: list[str] = []
    for name in _PDFS:
        path = os.path.join(PDF_DIR, name)
        if not os.path.exists(path):
            continue
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages[:4]:
                for raw in (page.extract_text() or "").split("\n"):
                    line = raw.strip()
                    if len(line) >= 8:
                        lines.append(line)
                        if len(lines) >= max_lines:
                            return lines
    return lines


def _pdfs_available() -> bool:
    try:
        import pdfplumber  # noqa: F401
    except ImportError:
        return False
    return os.path.isdir(PDF_DIR) and any(
        os.path.exists(os.path.join(PDF_DIR, name)) for name in _PDFS
    )


class TestLosslessness(unittest.TestCase):
    """ADR-3's one guarantee: the partition never adds or loses a character."""

    @unittest.skipUnless(_pdfs_available(), "reference PDFs / pdfplumber not available")
    def test_lossless_over_pdf_extracted_lines(self):
        lines = _pdf_lines()
        self.assertGreaterEqual(
            len(lines), 30, "need at least 30 extracted lines for the check"
        )
        for line in lines:
            with self.subTest(line=line[:60]):
                joined = "".join(s.text for s in split_math_spans(line))
                self.assertEqual(joined, line)

    def test_lossless_on_math_bearing_pdf_strings(self):
        # Exact pdfplumber lines carrying integrals / equations.
        lines = [
            "10. \u222b xsec 2 xdx is equal to",
            "26. Find \u222b(sin\u20131x)2dx",
            "27. Evaluate \u222b 1-x2 dx",
            "c) Find the particular integral of y\" + y = cos x.",
            "(A) 4 units (B) \u221a34 units (C) 5 units (D) 5\u221a2 units",
            "5 / 2 5",
            "0 / 2",
            "1. At which point does the graph of y=sinx intersect the origin in the given image?",
        ]
        for line in lines:
            with self.subTest(line=line[:60]):
                joined = "".join(s.text for s in split_math_spans(line))
                self.assertEqual(joined, line)


class TestClassification(unittest.TestCase):
    def test_math_tokens(self):
        for tok in ("\u222b", "\u221a34", "5\u221a2", "sin(", "dx", "x^2", "3x+2"):
            self.assertEqual(classify_token(tok), "MATH", tok)

    def test_glued_function_word_is_prose_not_math(self):
        # "y=sinx" (glued, no digits/operators beyond '=') is uncertain —
        # the detector keeps it as text rather than guess an equation.
        self.assertEqual(classify_token("y=sinx"), "PROSE")

    def test_prose_tokens(self):
        for tok in ("General", "Instructions", "units", "the"):
            self.assertEqual(classify_token(tok), "PROSE", tok)

    def test_glue_tokens(self):
        for tok in ("x", "=", ","):
            self.assertEqual(classify_token(tok), "GLUE", tok)

    def test_option_label_breaks_run(self):
        # ADR-3: an option label is a region boundary. Classifying it as
        # GLUE let one run swallow "(B)", so four MCQ options were parsed
        # as a single expression and the labels survived as stray
        # parenthesized letters inside the OMML.
        for tok in ("(A)", "(C)", "(d)"):
            self.assertEqual(classify_token(tok), "PROSE", tok)


class TestSpanBehaviour(unittest.TestCase):
    def test_prose_only_line_yields_no_math_spans(self):
        # Exact PDF line (2025112060.pdf cover page).
        line = "Marking Scheme link is given at every page."
        spans = split_math_spans(line)
        self.assertEqual([s.kind for s in spans], ["text"])
        self.assertEqual(spans[0].text, line)

    def test_prose_only_line_two_yields_no_math_spans(self):
        # Exact PDF line (MathSample.pdf header).
        line = "General Instructions"
        spans = split_math_spans(line)
        self.assertTrue(all(s.kind == "text" for s in spans))

    def test_adjacent_mcq_options_split_into_separate_math_spans(self):
        # SQP option row: no prose between the options, so only a label
        # break can separate them. Before the fix this was ONE math span
        # and became one welded OMML holding four options.
        line = "(A) cos\u22121x (B) cos\u22121(2x) (C) sin\u22121(x/2) (D) 2sin\u22121x"
        spans = split_math_spans(line)
        math = [s.text for s in spans if s.kind == "math"]
        self.assertEqual(len(math), 4, [s.text for s in spans])
        for m in math:
            for label in ("(A)", "(B)", "(C)", "(D)"):
                self.assertNotIn(label, m)
        self.assertEqual("".join(s.text for s in spans), line)

    def test_option_label_stays_text_at_run_edge(self):
        # A single leading label is trimmed to text; the value is math.
        spans = split_math_spans("(C) 1/4")
        math = [s.text for s in spans if s.kind == "math"]
        self.assertEqual(len(math), 1)
        self.assertEqual(math[0], "1/4")
        self.assertTrue(any("(C)" in s.text for s in spans if s.kind == "text"))

    def test_spec_example_yields_one_math_span(self):
        # The ADR-3 spec example: prose host with an embedded integral.
        spans = split_math_spans("Evaluate \u222b x 2 y dx dy")
        math = [s for s in spans if s.kind == "math"]
        self.assertEqual(len(math), 1)
        self.assertEqual(math[0].text, "\u222b x 2 y dx dy")

    def test_integral_pdf_line_keeps_prose_out(self):
        # Exact MathSample.pdf line: item label and prose stay text.
        spans = split_math_spans("26. Find \u222b(sin\u20131x)2dx")
        kinds = [s.kind for s in spans]
        self.assertIn("math", kinds)
        math = [s.text for s in spans if s.kind == "math"]
        self.assertTrue(math[0].startswith("\u222b"), math)
        for s in spans:
            if s.kind == "text":
                self.assertNotIn("\u222b", s.text)

    def test_mcq_options_become_separate_math_spans(self):
        # Exact Maths-SQP.pdf MCQ option line: each option value is its own
        # span, the "units"/label prose between them stays text.
        line = "(A) 4 units (B) \u221a34 units (C) 5 units (D) 5\u221a2 units"
        spans = split_math_spans(line)
        math = [s.text for s in spans if s.kind == "math"]
        self.assertIn("\u221a34", math)
        self.assertIn("5\u221a2", math)
        # Prose words never end up inside a math span.
        for s in spans:
            if s.kind == "math":
                self.assertNotIn("units", s.text)

    def test_empty_string(self):
        self.assertEqual(split_math_spans(""), [])

    def test_spans_are_ordered_and_contiguous(self):
        line = "26. Find \u222b(sin\u20131x)2dx"
        spans = split_math_spans(line)
        self.assertEqual("".join(s.text for s in spans), line)
        for s in spans:
            self.assertIsInstance(s, Span)


if __name__ == "__main__":
    unittest.main()
