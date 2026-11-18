# OpenCode Work Orders — Math Engine v2

Paste ONE work order at a time into OpenCode (free worker, e.g.
`opencode/nemotron-3-ultra-free` or `opencode/mimo-v2.6-flash-free`).
Always paste the PREAMBLE first. Run orders in order: W1 → W2 → W3 → W4.
Spec: `docs/MATH_ENGINE_V2_SPEC.md` (read the ADR you are implementing).

---

## PREAMBLE (paste at the top of every order)

```
You are an implementation worker on MathPipe (PDF → editable Word with native
equations). Repo root: /Volumes/Arhan/MathPipe/math-pdf-to-word
Python: apps/processor/.venv/bin/python   (never use system python)
Code you may edit: apps/processor/src/** and apps/processor/tests/** ONLY.
Do not touch: apps/web, packages/*, supabase, anything outside the above.
Do not add dependencies. Do not delete files you did not create. This folder is
NOT a git repo: before editing any file, copy it to /tmp/worker_backup/<task>/.

Before coding: read docs/MATH_ENGINE_V2_SPEC.md and the files named in your
order. Search for existing helpers first (reuse > extend > create).

Hard rules:
1. Make the smallest change that satisfies the order. No unrelated refactors.
2. No document-specific literals (question numbers, "each", file names). Fix
   classes of input, never one sample.
3. Every new behaviour gets a unit test in apps/processor/tests/ using the exact
   PDF-extracted string that motivated it.
4. When unsure whether text is math, KEEP IT AS TEXT. A wrong editable equation
   is worse than plain text.
5. Never claim a test or gate passed unless you ran it and pasted the tail of the output.

Verification you MUST run before reporting (paste outputs):
  apps/processor/.venv/bin/python -m unittest discover -s apps/processor/tests 2>&1 | tail -5
  apps/processor/.venv/bin/python apps/processor/tools/scorecard.py \
    --pdf-dir "$HOME/Downloads/Tests for maths converter" --out-dir /tmp/scorecard --skip-big 2>&1 | head -20

Report format (exactly):
  CHANGED: <files>
  TESTS: <N passed / failed>
  SCORECARD BEFORE → AFTER: <the table rows that changed>
  NOT DONE / UNCERTAIN: <honest list>
If tests fail or any gate that passed before now fails: restore the files from
/tmp/worker_backup/<task>/ (delete files you created) and report why. Do not stack fixes.
```

---

## W1 — Segments contract + builder (ADR-2) — pure refactor

**[x] COMPLETE & VERIFIED** (accepted 2026-10-15). Evidence: `tests/test_segments.py` green in the 116-test suite; scorecard rows recorded in `LOOP_LOG.md`.

```
TASK: Add ordered "segments" support. No behaviour change when absent.

1. apps/processor/src/word/builder.py
   In the final `else:` paragraph branch (the one handling inlineMath), add:
   if block.get("segments") is a non-empty list, create ONE paragraph and emit
   each segment in order:
     kind "text"  -> p.add_run(sanitize_xml_text(seg["text"]))
     kind "math"  -> _append_omath(p, seg["mathir"]); report["equations"] += 1
                     on UnsupportedConstruct: add a plain run with seg["text"],
                     report["equation_fallbacks"] += 1
   The covered text must NOT also be emitted via content/inlineMath for that block.
   Segments take precedence over inlineMath. Keep the legacy path untouched.
   Verify how extra fields reach the builder dict: read
   apps/processor/src/contract/document_model.py (build_partial_model) and
   confirm "segments" is passed through like "inlineMath" is. Add it if not.

2. apps/processor/tests/test_docx.py (or new test_segments.py)
   - segments [text, math, text] -> exactly one <w:p>, children order
     w:r, m:oMath, w:r; plain-text of paragraph == prose with no duplicated math.
   - math segment with an unsupported node -> plain-text fallback + counter.
   - block without segments -> output byte-for-byte equal to before (compare to
     building the same model on the previous code path via an existing fixture).

DONE WHEN: all unit tests pass; scorecard rows identical to before.
```

---

## W2 — Span detector + promotion gate + enrich integration (ADR-3, ADR-5)

**[x] COMPLETE & VERIFIED** (accepted 2026-10-15). Evidence: `mathengine/spans.py` + `mathengine/gate.py` in place; `tests/test_spans.py` / `tests/test_gate.py` green in the 116-test suite; G6 = 0 fake OMML on all 4 scorecard rows (`LOOP_LOG.md`).

```
TASK: Create inline math span detection. Read ADR-3 and ADR-5 first.

1. NEW apps/processor/src/mathengine/gate.py
   def is_promotable(span_text: str, mathir: dict) -> tuple[bool, str]
   Move (do not copy) _mathir_has_garbage, _mathir_has_zero_denominator and
   has_math_kernel usage here; enrich.py imports them from gate.py. Add rejects:
   fewer than 3 meaningful chars (ignore spaces/brackets), option-label-only
   (^\(?[A-Da-d]\)?\d*$), marks tags like "(8 x 2)", bare integers, URLs, tokens
   longer than 24 chars without structure. Return (False, "<reason-code>").

2. NEW apps/processor/src/mathengine/spans.py
   @dataclass(frozen=True) class Span: kind: str ("text"|"math"); text: str
   def split_math_spans(text: str) -> list[Span]
   Implement the token classification + run growth in ADR-3. Pure function.
   Lossless invariant: "".join(s.text for s in spans) == text (keep the original
   whitespace inside spans; assign inter-span whitespace to the preceding text span).

3. apps/processor/src/mathengine/enrich.py
   In enrich_blocks, for paragraph blocks that are NOT promoted whole-line:
   run split_math_spans; for each math span call the recognizer; keep it as math
   only if route_confidence != "escalate" and is_promotable(...) is (True, _)
   and mathir validates (mathir.validate_mathir == []). Build block.extra["segments"]
   per the ADR-2 schema. If no span survives, set no segments.
   Do NOT remove the existing fraction/integral/matrix inline passes yet (W4 does).
   But: if a block has segments, skip those legacy passes for that block so math
   is never emitted twice.

4. Tests (apps/processor/tests/test_spans.py, test_gate.py):
   - losslessness over >= 30 strings drawn from the real PDFs
     (run pdfplumber on the 4 test PDFs, take their paragraph strings).
   - prose-only strings -> zero math spans ("Find the particular integral of the equation").
   - "Evaluate ∫ x 2 y dx dy" style strings -> one math span.
   - fake cases rejected: "(A) 1", "(8 x 2)", "[1]", "a14", URL footer.

DONE WHEN: unit tests pass; scorecard shows G6 passing on all 4 PDFs, G8 passing,
OMML total not lower than baseline on MathSample/SQP/Mathematics-II.
```

---

## W3 — Recognizer gap closure

**[x] COMPLETE & VERIFIED** (accepted 2026-10-15). Loop per `LOOP_PROMPT.md` run and
escalated; architect ruling resolved the G5/rule-7d conflict: the
Mathematics - II heading fix was reinstated (the recall drop is a
permanently waived scorecard `m:t`-join artifact) and G5 was amended to
per-PDF thresholds (MathII ≥ 0.95, MathSample ≥ 0.75, Maths-SQP ≥ 0.80,
ICSE at baseline). Final: MathII G5 = 1.00, 116 tests green. Evidence:
`LOOP_LOG.md`.

Do not hand this over as a one-shot. Use `docs/opencode/LOOP_PROMPT.md`; it
feeds W3 failing samples one class at a time.

---

## W4 — Delete overfitting (ADR-6)

**[x] COMPLETE & VERIFIED** (accepted 2026-10-15). `_extract_sqp_bracket_matrices` and
`_extract_definite_integral` deleted (grep: no src/ matches); integral
bounds absorb into `m:sub`/`m:sup` and differentials into the same
`m:oMath` (verified on all 4 builds — never trailing unformatted text);
literal grep on enrich.py clean; `_table_is_matrix` kept; fake OMML = 0 on
4/4 rows. Evidence: `LOOP_LOG.md`.

```
TASK: Remove document-specific code now that spans exist.

1. Delete _extract_sqp_bracket_matrices and its call site in enrich.py.
2. Fold _extract_definite_integral behaviour into spans (bounds "∫ ^{b} _{a}" or
   "∫ _{a} ^{b}" belong to the integral span) then delete the old function and call.
3. grep -rnE "32\.|each\\\\s|𝐴𝐵|and hence" apps/processor/src/ must find no
   enrich.py hits (show the command output).
4. Keep the matrix TABLE path (_table_is_matrix) — it is geometry-based and general.

DONE WHEN: tests green; scorecard not worse on any row; grep output clean.
```

---

## W6 — Unified End-to-End CLI (`convert`) & Figure Binding

**[x] COMPLETE & VERIFIED** (accepted 2026-10-15). One-step `convert` subcommand
in `apps/processor/src/cli.py`: pipeline → DOCX in a single command; failure =
exit 2 + JSON error, nothing written. Figures are re-bound from `imageBase64`
via `_figure_assets_from_model()` — approved as the canonical way to preserve
figures across JSON serialization — and passed to `build_docx(figures=…)` in
both `convert` and `build-docx`. 120 tests green; scorecard rows identical to
the accepted baseline; smoke on `Maths-SQP.pdf`: 1,706,247 bytes / 69 equations
/ 7 figures / 1 table. Evidence: `LOOP_LOG.md`.

Usage:

```bash
apps/processor/src/cli.py convert <input.pdf> -o <output.docx> [--mode standard|verified] [--max-pages N] [--max-mb N]
```

---

## W8 — Universal Promotion Gate on Whole-Line Blocks

**[x] COMPLETE & VERIFIED** (accepted 2026-10-17). Whole-line promotion in
`src/mathengine/enrich.py` now routes every candidate through `is_promotable`
(ADR-5 single gate; `gate.py` untouched) before `block.kind = "equation"`:
rejections keep the text, set `mathHint` (fallback "text") and count the miss
via `_note_inline_fallback` with the gate's stable reason code. Class fixed:
short answer/option fragments that became standalone OMML (`9) -1`,
`9. a) -8`, `8) C) √13`). 126 tests green (120 → 126;
`tests/test_gate.py::TestWholeLinePromotionGate`); **QueBank G6 = ✅
(omml_fake 3 → 0)** on the 103-page corpus. Accepted side effect (architect
ruling): one flattened MCQ option `(D) 2sin −1 𝑥` demoted on Maths-SQP
(69 → 68 OMML) — intended precision-first behavior. Evidence: `LOOP_LOG.md`.
