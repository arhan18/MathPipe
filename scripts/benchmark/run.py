"""Benchmark harness (§57): run candidate engines over the corpus, score, compare.

Usage:
    .venv/bin/python scripts/benchmark/run.py --corpus apps/processor/tests/golden --out /tmp/bench.json

Engines:
  scaffold  Built-in deterministic baseline (always available).
  marker    Marker candidate — runs ONLY after the license gate approves the
            exact version/commit (docs/license-audit.md). Until then this
            adapter refuses to run rather than silently benchmarking an
            unapproved build.
  docling   Same gate as marker.

Metrics (§36): text fidelity, math accuracy (stub until Phase 6), table
accuracy (stub until Phase 7), figure retention, reading-order accuracy,
layout similarity, DOCX validity (stub until Phase 8), timing, peak memory,
cost per page (always 0.0 for the deterministic scaffold).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tracemalloc

PROCESSOR = os.path.join(os.path.dirname(__file__), "..", "..", "apps", "processor")
sys.path.insert(0, PROCESSOR)

from src.pipeline.runner import run_pipeline  # noqa: E402


def score_reading_order(model: dict) -> float:
    """Fraction of blocks whose stored order matches geometric top-to-bottom
    within their column half. Baseline proxy until human-rated scores exist."""
    hits = total = 0
    for page in model["document"]["pages"]:
        blocks = page["blocks"]
        total += max(0, len(blocks) - 1)
        for a, b in zip(blocks, blocks[1:]):
            # Same-side progression in y should not jump backwards.
            same_side = (a["bbox"][0] < page["width"] / 2) == (b["bbox"][0] < page["width"] / 2)
            if not same_side or b["bbox"][1] >= a["bbox"][1] - 2:
                hits += 1
    return hits / total if total else 1.0


def run_scaffold(pdf: str) -> dict:
    tracemalloc.start()
    t0 = time.perf_counter()
    result = run_pipeline(pdf, source_name=os.path.basename(pdf), max_bytes=250 * 1024 * 1024, max_pages=1000)
    dt_ms = int((time.perf_counter() - t0) * 1000)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    if not result.ok or result.model is None:
        return {"engine": "scaffold", "ok": False, "error": result.error_code}
    pages = result.model["document"]["pages"]
    return {
        "engine": "scaffold",
        "ok": True,
        "pages": len(pages),
        "blocks": sum(len(p["blocks"]) for p in pages),
        "classification": result.model["document"]["metadata"]["classification"],
        "reading_order_score": round(score_reading_order(result.model), 3),
        "duration_ms": dt_ms,
        "peak_kb": peak // 1024,
        "cost_usd_per_page": 0.0,
    }


def run_gated(name: str, pdf: str) -> dict:
    return {
        "engine": name,
        "ok": False,
        "error": "LICENSE_GATE",
        "message": f"{name} runs only after docs/license-audit.md approves the exact version.",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--engines", default="scaffold", help="comma list: scaffold,marker,docling")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    pdfs = sorted(
        f for f in os.listdir(args.corpus)
        if f.lower().endswith(".pdf") and not f.startswith("._") and not f.startswith(".")
    )
    rows = []
    for pdf in pdfs:
        path = os.path.join(args.corpus, pdf)
        for engine in [e.strip() for e in args.engines.split(",")]:
            if engine == "scaffold":
                row = run_scaffold(path)
            elif engine in ("marker", "docling"):
                row = run_gated(engine, path)
            else:
                row = {"engine": engine, "ok": False, "error": "UNKNOWN_ENGINE"}
            rows.append({"file": pdf, **row})
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"engines": args.engines, "results": rows}, f, indent=2)
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
