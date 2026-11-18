# Model Benchmark Log (§57)

Benchmark-driven selection: no parser/model enters production without beating
the baseline on OUR corpus (not vendor scores), passing the license gate, and
clearing cost/latency budgets.

## Baseline run — 2026-10-06 (scaffold-0.1, deterministic)

Corpus: `apps/processor/tests/golden/` (2 generated fixtures).

| File | Engine | Pages | Blocks | Classification | Read-order | Time | Peak | Cost/page |
|---|---|---|---|---|---|---|---|---|
| algebra-two-column.pdf | scaffold | 1 | 2 | BORN_DIGITAL | 1.000 | ~270ms | ~3MB | $0.00 |
| algebra-worksheet.pdf | scaffold | 1 | 1 | BORN_DIGITAL | 1.000 | ~80ms | ~1.5MB | $0.00 |

Reproduce: `.venv/bin/python scripts/benchmark/run.py --corpus apps/processor/tests/golden --out /tmp/bench.json`

## Large-document run — 2026-10-06 (scaffold-0.1, chunked)

`algebra-long-60.pdf`: 60 pages → 6 chunks of 10 → 120 blocks, chapter order
preserved across chunk boundaries, resume reuses all checkpoints, 79 MB peak.
Chunked CLI: `--chunk-pages 10 --work-dir <dir> --job-id <id> [--resume]`.

## Candidates (all gated — none approved)

| Component | Code license | Model license | Status |
|---|---|---|---|
| Marker | Apache-2.0 | Modified OpenRAIL-M (review needed) | Benchmark pending, NOT production |
| Docling | MIT | Per-model review needed | Benchmark pending, NOT production |
| pix2tex weights | MIT (code) | CC BY-NC-SA (weights) | Research only, NOT production |
| Nougat weights | MIT (code) | CC BY-NC | Research only, NOT production |

## Next benchmark (Phase 6)

Add 50–100 real representative PDFs (textbooks, papers, worksheets) plus the
red-team adversarial set (§61), then run Marker vs Docling vs scaffold on
quality + latency + cost before selecting the Phase 6 parser path.
