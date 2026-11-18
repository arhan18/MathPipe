"""Verification tests: seeded errors must be caught, bounded repair must
fix what it can and escalate the rest. No live AI providers involved."""
from __future__ import annotations

import copy
import io
import os
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.pipeline.runner import run_pipeline  # noqa: E402
from src.verification.compare import (  # noqa: E402
    check_docx_consistency,
    check_equation_structure,
    check_text_presence,
)
from src.verification.repair import MAX_REPAIR_ATTEMPTS, repair_equation_block  # noqa: E402
from src.verification.stage import run_verification  # noqa: E402
from src.word.builder import build_docx  # noqa: E402

GOLDEN = os.path.join(os.path.dirname(__file__), "golden")
WORKSHEET = os.path.join(GOLDEN, "algebra-worksheet.pdf")


def fresh_model():
    result = run_pipeline(WORKSHEET, source_name="w.pdf", max_bytes=10**6, max_pages=10, mode="verified")
    assert result.ok and result.model is not None
    return copy.deepcopy(result.model)


class TestDetection(unittest.TestCase):
    def test_missing_mathir_is_critical(self):
        model = fresh_model()
        eq = next(b for p in model["document"]["pages"] for b in p["blocks"] if b["type"] == "equation")
        del eq["mathir"]
        report = check_equation_structure(model)
        self.assertTrue(any(i.severity == "critical" and i.block_id == eq["id"] for i in report.issues))

    def test_missing_text_is_flagged(self):
        model = fresh_model()
        para = next(b for p in model["document"]["pages"] for b in p["blocks"] if b["type"] == "paragraph")
        para["content"] = "Xyzzqy plugh totally absent string 12345"
        report = check_text_presence(WORKSHEET, model)
        self.assertTrue(any(i.block_id == para["id"] for i in report.issues))

    def test_docx_equation_shortfall_is_critical(self):
        model = fresh_model()
        data, _ = build_docx(model)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        # Seed: strip one oMath element from the package.
        stripped = xml.replace("<m:oMath", "<m:oMathRemoved", 1)
        with zipfile.ZipFile(io.BytesIO(data)) as zin:
            names = zin.namelist()
            blobs = {n: (stripped.encode() if n == "word/document.xml" else zin.read(n)) for n in names}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for n, blob in blobs.items():
                zout.writestr(n, blob)
        report = check_docx_consistency(model, buf.getvalue())
        self.assertTrue(any(i.severity == "critical" for i in report.issues))


class TestRepair(unittest.TestCase):
    def test_budget_is_bounded(self):
        self.assertEqual(MAX_REPAIR_ATTEMPTS, 2)

    def test_unfixable_escalates(self):
        block = {"id": "e1", "type": "equation", "content": "@@@ ###", "confidence": 0.3}
        outcome = repair_equation_block(block)
        self.assertFalse(outcome.fixed)
        self.assertTrue(outcome.escalated)
        self.assertLessEqual(outcome.attempts, MAX_REPAIR_ATTEMPTS)

    def test_verified_mode_reports_status(self):
        model = fresh_model()
        report = run_verification(model, WORKSHEET, mode="verified")
        self.assertIn(report.status, ("passed", "warnings"))
        summary = report.summarize()
        self.assertIn("critical", summary)


if __name__ == "__main__":
    unittest.main()
