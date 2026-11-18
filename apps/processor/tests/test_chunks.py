"""Long-document tests: chunking, checkpoints, resume, failure isolation."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.pipeline import chunks  # noqa: E402
from src.pipeline.runner import PAGE_FAILURE_THRESHOLD, run_pipeline  # noqa: E402

GOLDEN = os.path.join(os.path.dirname(__file__), "golden")
LONG = os.path.join(GOLDEN, "algebra-long-60.pdf")
TWO_COL = os.path.join(GOLDEN, "algebra-two-column.pdf")


class TestPlanner(unittest.TestCase):
    def test_even_split(self):
        plans = chunks.plan_chunks([1, 2, 3, 4, 5], 2)
        self.assertEqual([[1, 2], [3, 4], [5]], [p.pages for p in plans])

    def test_single_page_docs(self):
        plans = chunks.plan_chunks([1], 10)
        self.assertEqual(len(plans), 1)

    def test_chunk_floor(self):
        plans = chunks.plan_chunks([1, 2], 0)
        self.assertEqual([len(p.pages) for p in plans], [1, 1])


class TestResume(unittest.TestCase):
    def test_resume_reuses_checkpoints(self):
        with tempfile.TemporaryDirectory() as work:
            first = run_pipeline(TWO_COL, source_name="t.pdf", max_bytes=10**6, max_pages=10,
                                 work_dir=work, job_id="j1", chunk_pages=10)
            self.assertTrue(first.ok)
            manifest_file = chunks.manifest_path(work, "j1")
            with open(manifest_file, encoding="utf-8") as f:
                before = json.load(f)
            second = run_pipeline(TWO_COL, source_name="t.pdf", max_bytes=10**6, max_pages=10,
                                  work_dir=work, job_id="j1", chunk_pages=10, resume=True)
            self.assertTrue(second.ok)
            self.assertTrue(any("resumed" in s.detail for s in second.stages))
            with open(manifest_file, encoding="utf-8") as f:
                after = json.load(f)
            self.assertEqual(before["chunks"], after["chunks"])
            self.assertEqual(
                [b["content"] for p in first.model["document"]["pages"] for b in p["blocks"]],
                [b["content"] for p in second.model["document"]["pages"] for b in p["blocks"]],
            )

    def test_long_doc_chunks_and_orders(self):
        result = run_pipeline(LONG, source_name="long.pdf", max_bytes=10**7, max_pages=100, chunk_pages=10)
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.chunks_total, 6)
        self.assertEqual(result.chunks_complete, 6)
        heads = [b["content"] for p in result.model["document"]["pages"] for b in p["blocks"] if "Chapter" in b["content"]]
        nums = [int(h.split()[1].rstrip(".")) for h in heads]
        self.assertEqual(nums, sorted(nums))
        self.assertEqual(len(nums), 60)


class TestIsolation(unittest.TestCase):
    def test_threshold_constant_sane(self):
        self.assertGreater(PAGE_FAILURE_THRESHOLD, 0)
        self.assertLessEqual(PAGE_FAILURE_THRESHOLD, 1.0)


if __name__ == "__main__":
    unittest.main()
