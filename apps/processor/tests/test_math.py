"""Math engine tests — deterministic, license-clean, no model weights."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.mathengine.confidence import route_confidence  # noqa: E402
from src.mathengine.detect import is_equation_line, score_text  # noqa: E402
from src.mathengine.mathir import content_hash, validate_mathir, wrap, fraction, text  # noqa: E402
from src.mathengine.normalize import normalize_latex  # noqa: E402
from src.mathengine.numbers import split_equation_number  # noqa: E402
from src.mathengine.recognize import DeterministicAsciiRecognizer, GatedRecognizer, LicenseNotCleared  # noqa: E402


class TestDetection(unittest.TestCase):
    def test_equation_lines(self):
        self.assertTrue(is_equation_line("x^2 + 3x + 2 = 0"))
        self.assertTrue(is_equation_line("x = (-b +- sqrt(b^2 - 4ac)) / 2a"))

    def test_prose_rejected(self):
        self.assertFalse(is_equation_line("Solve each equation. Show all steps."))
        self.assertFalse(is_equation_line("a"))

    def test_scores_increase_with_symbols(self):
        plain = score_text("Solve the equation").score
        mathy = score_text("x^2 + 3x + 2 = 0").score
        self.assertGreater(mathy, plain)


class TestNormalize(unittest.TestCase):
    def test_aliases_and_unicode(self):
        self.assertEqual(normalize_latex(r"\dfrac{a}{b}"), r"\frac{a}{b}")
        self.assertIn(r"\times", normalize_latex("a × b"))
        self.assertIn(r"\sqrt", normalize_latex("√x"))

    def test_whitespace(self):
        self.assertEqual(normalize_latex("x  +   y"), "x + y")


class TestConfidence(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(route_confidence(0.97).action, "accept")
        self.assertEqual(route_confidence(0.85).action, "secondary_check")
        self.assertEqual(route_confidence(0.70).action, "fallback_recognizer")
        self.assertEqual(route_confidence(0.40).action, "escalate")


class TestNumbers(unittest.TestCase):
    def test_trailing_number_splits(self):
        n = split_equation_number("x^2 + 1 (4)")
        self.assertEqual(n.number, "4")
        self.assertEqual(n.body, "x^2 + 1")

    def test_no_number(self):
        n = split_equation_number("x + y = z")
        self.assertIsNone(n.number)


class TestRecognizer(unittest.TestCase):
    def setUp(self):
        self.rec = DeterministicAsciiRecognizer()

    def test_fraction_and_superscript(self):
        r = self.rec.recognize("x^2 + 3x + 2")
        self.assertGreaterEqual(r.confidence, 0.9)
        self.assertEqual(validate_mathir(r.mathir), [])
        # Must contain a superscript node somewhere.
        blob = str(r.mathir)
        self.assertIn("superscript", blob)

    def test_slash_fraction(self):
        r = self.rec.recognize("(x^2 + 1) / (x - 1)")
        self.assertEqual(validate_mathir(r.mathir), [])
        self.assertIn("fraction", str(r.mathir))

    def test_sqrt_and_function(self):
        r = self.rec.recognize("sqrt(x) + sin(x)")
        self.assertEqual(validate_mathir(r.mathir), [])
        self.assertIn("root", str(r.mathir))

    def test_garbage_escalates_honestly(self):
        r = self.rec.recognize("@@@ ###")
        self.assertLess(r.confidence, 0.6)

    def test_gated_refuses(self):
        with self.assertRaises(LicenseNotCleared):
            GatedRecognizer("pix2tex").recognize("x^2")


class TestMathIR(unittest.TestCase):
    def test_schema_round_trip(self):
        doc = wrap(fraction(text("a"), text("b")))
        self.assertEqual(validate_mathir(doc), [])
        h1 = content_hash(doc)
        h2 = content_hash(wrap(fraction(text("a"), text("b"))))
        self.assertEqual(h1, h2)

    def test_ragged_matrix_flagged(self):
        from src.mathengine.mathir import matrix

        doc = wrap(matrix([[text("a")], [text("b"), text("c")]]))
        # Schema allows it; structural check must flag it.
        self.assertTrue(any("ragged" in issue for issue in validate_mathir(doc)))


if __name__ == "__main__":
    unittest.main()
