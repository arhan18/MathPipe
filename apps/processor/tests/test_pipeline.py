"""Pipeline regression tests — run with: .venv/bin/python -m unittest discover -s tests -v"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.ingestion.validate import validate_pdf  # noqa: E402
from src.ingestion.classify import classify_pdf  # noqa: E402
from src.pipeline.runner import run_pipeline  # noqa: E402
from src.understanding.blocks import segment_blocks  # noqa: E402
from src.understanding.reading_order import order_blocks  # noqa: E402
from src.understanding.text import extract_page_text  # noqa: E402

GOLDEN = os.path.join(os.path.dirname(__file__), "golden")
TWO_COL = os.path.join(GOLDEN, "algebra-two-column.pdf")
SINGLE = os.path.join(GOLDEN, "algebra-worksheet.pdf")


class TestValidation(unittest.TestCase):
    def test_missing_file_is_typed(self):
        r = validate_pdf("/nope/missing.pdf", max_bytes=10**6, max_pages=10)
        self.assertFalse(r.ok)
        self.assertEqual(r.error_code, "FILE_INVALID")

    def test_page_limit_is_typed(self):
        r = validate_pdf(SINGLE, max_bytes=10**6, max_pages=0)
        self.assertFalse(r.ok)
        self.assertEqual(r.error_code, "PAGE_LIMIT_EXCEEDED")

    def test_valid_pdf(self):
        r = validate_pdf(SINGLE, max_bytes=10**6, max_pages=10)
        self.assertTrue(r.ok)
        self.assertEqual(r.page_count, 1)


class TestClassification(unittest.TestCase):
    def test_born_digital(self):
        self.assertEqual(classify_pdf(SINGLE).label, "BORN_DIGITAL")

    def test_unknown_on_garbage(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"not a pdf at all")
            name = f.name
        try:
            self.assertEqual(classify_pdf(name).label, "UNKNOWN")
        finally:
            os.unlink(name)


class TestReadingOrder(unittest.TestCase):
    def test_two_column_left_before_right(self):
        pages = extract_page_text(TWO_COL)
        blocks = segment_blocks(pages[0])
        ordered = order_blocks(blocks, pages[0].width)
        texts = [b.text for b in ordered]
        left_idx = next(i for i, t in enumerate(texts) if "Left column first" in t)
        right_idx = next(i for i, t in enumerate(texts) if "Right gutter" in t or "Right column" in t)
        self.assertLess(left_idx, right_idx)

    def test_single_column_stays_geometric(self):
        pages = extract_page_text(SINGLE)
        blocks = segment_blocks(pages[0])
        ordered = order_blocks(blocks, pages[0].width)
        tops = [b.bbox[1] for b in ordered]
        self.assertEqual(tops, sorted(tops))


class TestPipeline(unittest.TestCase):
    def test_end_to_end_model(self):
        result = run_pipeline(TWO_COL, source_name="algebra-two-column.pdf", max_bytes=10**6, max_pages=10)
        self.assertTrue(result.ok, result.message)
        assert result.model is not None
        self.assertEqual(result.model["schemaVersion"], "document-model/v0.1-partial")
        pages = result.model["document"]["pages"]
        self.assertEqual(len(pages), 1)
        self.assertTrue(all(b["readingOrder"] >= 1 for b in pages[0]["blocks"]))

    def test_failure_is_typed(self):
        result = run_pipeline("/nope/missing.pdf", source_name="x.pdf", max_bytes=10**6, max_pages=10)
        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error_code)


if __name__ == "__main__":
    unittest.main()
