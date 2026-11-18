"""ADR-5 promotion-gate tests.

Every case uses the exact string the PDF extractor produced for it; the
rendered-length guard is checked against the MathIR the recognizer builds
from that string (the same MathIR the renderer turns into <m:t> content).
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.mathengine.enrich import enrich_blocks  # noqa: E402
from src.mathengine.gate import is_promotable, _rendered_meaningful_len  # noqa: E402
from src.mathengine.recognize import DeterministicAsciiRecognizer  # noqa: E402
from src.understanding.blocks import Block  # noqa: E402

REC = DeterministicAsciiRecognizer()


def _promotable(text: str):
    result = REC.recognize(text)
    mathir = getattr(result, "mathir", None)
    if mathir is None:
        return False, "no-mathir"
    return is_promotable(text, mathir)


class TestRenderedLengthGuard(unittest.TestCase):
    """G6 measured on the rendered equation: spans that type set to nothing
    meaningful must be rejected even when the span text itself is long
    enough to pass the textual rules."""

    def test_mathii_folio_fraction_5_over_2_rejected(self):
        # Exact span from "Mathematics - II.pdf" p.2 folio column ("5 / 2 5"
        # after block splitting): renders as m:t "52".
        self.assertEqual(_promotable("5 / 2"), (False, "rendered-too-short"))

    def test_mathii_folio_fraction_0_over_2_rejected(self):
        # Exact span from "Mathematics - II.pdf" p.1 folio column ("0 / 2").
        self.assertEqual(_promotable("0 / 2"), (False, "rendered-too-short"))

    def test_sqp_mcq_option_value_sqrt34_rejected(self):
        # Exact option value from "Maths-SQP.pdf" p.3 position-vector MCQ:
        # "(B) √34 units" — renders as m:t "34".
        self.assertEqual(_promotable("\u221a34"), (False, "rendered-too-short"))

    def test_sqp_mcq_option_value_5sqrt2_rejected(self):
        # Exact option value from "Maths-SQP.pdf" p.3: "(D) 5\u221a2 units".
        self.assertEqual(_promotable("5\u221a2"), (False, "rendered-too-short"))

    def test_rendered_meaningful_len_matches_expectation(self):
        # "5 / 2" renders "52" (2 meaningful chars), the gate threshold side.
        result = REC.recognize("5 / 2")
        self.assertEqual(_rendered_meaningful_len(result.mathir), 2)

    def test_longer_render_passes(self):
        # "√(3x + 1) = 5" renders well past the threshold.
        result = REC.recognize("\u221a(3x + 1) = 5")
        self.assertGreaterEqual(_rendered_meaningful_len(result.mathir), 3)
        self.assertEqual(_promotable("\u221a(3x + 1) = 5"), (True, "ok"))


class TestRealMathStillPromotes(unittest.TestCase):
    """The guard must not kill genuine equations from the reference PDFs."""

    def test_mathsample_definite_integral(self):
        # Exact MathSample.pdf p.5 line "26. Find ∫(sin–1x)2dx" — the span.
        self.assertEqual(_promotable("\u222b(sin\u20131x)2dx"), (True, "ok"))

    def test_mathsample_integral_line_27(self):
        # Exact MathSample.pdf p.5 line "27. Evaluate ∫ 1-x2 dx" — the span.
        self.assertEqual(_promotable("\u222b 1-x2 dx"), (True, "ok"))

    def test_standard_quadratic(self):
        self.assertEqual(_promotable("x^2 + 3x + 2 = 0"), (True, "ok"))

    def test_trig_equation(self):
        # A clean trig relation promotes.
        self.assertEqual(_promotable("sin(x) = 0"), (True, "ok"))

    def test_glued_trig_stays_text(self):
        # "y=sinx" (exact 2025112060.pdf wording, glued) is uncertain —
        # the gate keeps it as text (precision-first).
        self.assertEqual(_promotable("y=sinx"), (False, "prose-word"))


class TestTextualRulesUnchanged(unittest.TestCase):
    def test_too_short(self):
        result = REC.recognize("x +")
        self.assertEqual(is_promotable("x +", result.mathir)[0], False)
        self.assertEqual(is_promotable("x +", result.mathir)[1], "too-short")

    def test_bare_number(self):
        # 4 digits so the span clears the 3-char floor and reaches the
        # bare-number rule.
        result = REC.recognize("2024")
        self.assertEqual(is_promotable("2024", result.mathir)[1], "bare-number")

    def test_option_label_only(self):
        # "A12": long enough to clear the floor, then label-pattern matched.
        result = REC.recognize("A12")
        self.assertEqual(is_promotable("A12", result.mathir)[1], "option-label-only")

    def test_prose_word(self):
        result = REC.recognize("Evaluate")
        self.assertEqual(is_promotable("Evaluate", result.mathir)[1], "prose-word")

    def test_no_mathir(self):
        self.assertEqual(is_promotable("x^2 + 3x + 2 = 0", None)[1], "no-mathir")

    def test_zero_denominator(self):
        # π/0-style hallucination: fraction over an exact zero.
        mathir = {
            "schemaVersion": "1.0",
            "root": {
                "type": "fraction",
                "numerator": {"type": "text", "value": "\u03c0"},
                "denominator": {"type": "text", "value": "0"},
            },
        }
        self.assertEqual(
            is_promotable("\u03c0/0 = 0", mathir)[1], "zero-denominator"
        )

    def test_rendered_label_only(self):
        # A span that passes every textual rule but renders as a lone
        # option-label pattern ("a12") — G6 would count it fake.
        mathir = {
            "schemaVersion": "1.0",
            "root": {
                "type": "fraction",
                "numerator": {"type": "text", "value": "a1"},
                "denominator": {"type": "text", "value": "2"},
            },
        }
        self.assertEqual(
            is_promotable("a1/2", mathir), (False, "rendered-label-only")
        )


class TestWholeLinePromotionGate(unittest.TestCase):
    """W8: whole-line promotion in ``enrich_blocks`` must pass the same
    single promotion gate as spans. The short answer/option fragments below
    reached standalone OMML on the large corpus (rendered under 3 meaningful
    chars — G6 fakes); the gate keeps them as text instead."""

    @staticmethod
    def _enrich(text: str):
        block = Block(
            id="p1",
            kind="paragraph",
            page_number=1,
            bbox=[0, 0, 1, 1],
            text=text,
            size=10.0,
            bold=False,
            confidence=0.99,
        )
        enrich_blocks([block])
        return block

    def test_answer_fragment_minus_one_stays_text(self):
        block = self._enrich("9) -1")
        self.assertEqual(block.kind, "paragraph")
        self.assertIsNone(block.extra.get("latex"))
        self.assertFalse(block.extra.get("segments"))
        hint = block.extra.get("mathHint", {})
        self.assertEqual(hint.get("fallback"), "text")
        self.assertIn("too-short", hint.get("note", ""))

    def test_answer_fragment_minus_eight_stays_text(self):
        block = self._enrich("9. a) -8")
        self.assertEqual(block.kind, "paragraph")
        self.assertIsNone(block.extra.get("latex"))
        hint = block.extra.get("mathHint", {})
        self.assertEqual(hint.get("fallback"), "text")
        self.assertIn("too-short", hint.get("note", ""))

    def test_option_radical_fragment_stays_text(self):
        # The radical renders as m:t "13" (2 meaningful chars) — rejected.
        block = self._enrich("8) C) \u221a13")
        self.assertEqual(block.kind, "paragraph")
        self.assertIsNone(block.extra.get("latex"))
        self.assertFalse(block.extra.get("segments"))
        hint = block.extra.get("mathHint", {})
        self.assertEqual(hint.get("fallback"), "text")
        self.assertIn("rendered-too-short", hint.get("note", ""))
        self.assertEqual(block.extra.get("inlineFallbacks"), 1)

    def test_option_bare_number_stays_text(self):
        block = self._enrich("8) C) 13")
        self.assertEqual(block.kind, "paragraph")
        self.assertIsNone(block.extra.get("latex"))

    def test_quadratic_still_promotes(self):
        block = self._enrich("x^2 + y^2 = 1")
        self.assertEqual(block.kind, "equation")
        self.assertTrue(block.extra.get("latex"))

    def test_integral_line_still_promotes(self):
        block = self._enrich("\u222b_0^1 f(x)dx")
        self.assertEqual(block.kind, "equation")
        self.assertIn("\\int", block.extra.get("latex", ""))


if __name__ == "__main__":
    unittest.main()
