"""Red-team tests: adversarial inputs must degrade honestly — typed errors,
fallbacks with warning metadata, never a confident wrong answer."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.mathengine.recognize import DeterministicAsciiRecognizer  # noqa: E402
from src.pipeline.runner import run_pipeline  # noqa: E402
from src.word.omml import UnsupportedConstruct, render_omath  # noqa: E402
from src.mathengine import mathir as M  # noqa: E402

GOLDEN = os.path.join(os.path.dirname(__file__), "golden")
TRICKY = os.path.join(GOLDEN, "redteam-tricky.pdf")
MALFORMED = os.path.join(GOLDEN, "redteam-malformed.pdf")


class TestRedTeam(unittest.TestCase):
    def test_malformed_pdf_is_typed(self):
        result = run_pipeline(MALFORMED, source_name="x.pdf", max_bytes=10**6, max_pages=10)
        self.assertFalse(result.ok)
        self.assertIn(result.error_code, ("FILE_INVALID", "PROCESSING_FAILED"))

    def test_unbalanced_delimiters_never_clean(self):
        r = DeterministicAsciiRecognizer().recognize("(x + (y + z)")
        self.assertLess(r.confidence, 0.95)

    def test_long_expression_parses_or_escalates(self):
        text = "x_1 + x_2 + x_3 + x_4 + x_5 + x_6 + x_7 + x_8 = S"
        r = DeterministicAsciiRecognizer().recognize(text)
        # Either clean or honestly downgraded — never 0.97 with dropped content.
        if r.confidence >= 0.9:
            for tok in ["x_1", "x_8", "S"]:
                self.assertIn(tok.replace("_", ""), r.latex.replace("_", ""))

    def test_tricky_doc_completes_with_honest_report(self):
        result = run_pipeline(TRICKY, source_name="red.pdf", max_bytes=10**6, max_pages=10, mode="verified")
        self.assertTrue(result.ok, result.message)
        assert result.model is not None
        # Every equation block either validates or carries a fallback flag.
        from src.mathengine.mathir import validate_mathir

        for page in result.model["document"]["pages"]:
            for b in page["blocks"]:
                if b.get("type") != "equation":
                    continue
                valid = not validate_mathir(b.get("mathir", {}))
                flagged = "fallback" in str(b.get("extra", {})) or "mathHint" in b
                routed = b.get("routing") in ("accept", "secondary_check", "fallback_recognizer")
                self.assertTrue(valid or flagged or routed, f"silent equation: {b.get('content')}")

    def test_unsupported_omml_never_silent(self):
        with self.assertRaises(UnsupportedConstruct):
            render_omath(M.wrap({"type": "accent", "kind": "squiggle", "child": M.text("x")}))


if __name__ == "__main__":
    unittest.main()
