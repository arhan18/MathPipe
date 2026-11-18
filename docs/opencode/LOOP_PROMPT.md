# OpenCode Repetition Loop — "fix the worst failing gate, keep only if better"

Use for W3 (recognizer gap closure) and any later tuning. Paste the block
below into OpenCode once; it iterates on its own and stops by rule, not by feel.
Run AFTER W1 and W2 are merged and green.

```
ROLE: You are an iterative fixer for MathPipe's math engine. You run a
measure → fix → re-measure loop and keep a change ONLY if metrics improve.

SETUP (once)
- Repo: /Volumes/Arhan/MathPipe/math-pdf-to-word  Python: apps/processor/.venv/bin/python
- Editable: apps/processor/src/mathengine/**, apps/processor/src/word/**,
  apps/processor/tests/**. Nothing else. No new dependencies. No commits.
- Read docs/MATH_ENGINE_V2_SPEC.md (ADR-3, ADR-4, ADR-5).
- Create/append the log docs/opencode/LOOP_LOG.md (one entry per iteration).
- Snapshot baseline: run the SCORE command and save the output as BASELINE.

SCORE COMMAND
  apps/processor/.venv/bin/python apps/processor/tools/scorecard.py \
    --pdf-dir "$HOME/Downloads/Tests for maths converter" \
    --out-dir /tmp/scorecard --skip-big
TEST COMMAND
  apps/processor/.venv/bin/python -m unittest discover -s apps/processor/tests 2>&1 | tail -5

LOOP (max 12 iterations)
 1. Run SCORE. Pick ONE target: the first failing gate in this priority order
    G6 (fake OMML) → G8 (duplication) → G5 (math typeset %) → G3/G4 (recall/order).
    Within it pick the PDF with the worst value.
 2. Find concrete evidence. Open /tmp/scorecard/<tag>/out.docx text, or run the
    pipeline on that PDF, and collect 3-5 EXACT strings that fail the gate
    (e.g. an unconverted "∫ x 2 y dx dy", or a fake OMML like "a14").
    Write them into the iteration's log entry. No evidence → no change.
 3. Classify the failure as a CLASS, never a one-off:
    - span not detected / span too short or too long  → mathengine/spans.py
    - recognized but wrong structure                  → recognize.py / normalize.py
    - fake or hallucinated equation shipped           → gate.py
    - renders badly in Word                           → word/omml.py (rare)
 4. Write the failing strings as a unit test FIRST. Run TEST: it must fail.
 5. BEFORE editing any file, back it up (this folder is NOT a git repo):
      mkdir -p /tmp/loop_backup/iter_N && cp <file> /tmp/loop_backup/iter_N/
    Then make the smallest fix for the class. Rules:
    - NO literals tied to a document (question numbers, file names, a single
      sample string). If the fix only works for one string, it is wrong.
    - Precision beats recall: when unsure, keep text.
 6. Run TEST then SCORE.
 7. DECIDE (mechanical):
    KEEP only if ALL of:
      - all unit tests pass (old and new)
      - the target metric improved
      - no gate that passed in the previous SCORE now fails
      - no PDF's word_recall or order_recall dropped by more than 0.01
      - omml_fake did not increase on any PDF
    Otherwise REVERT: copy every file from /tmp/loop_backup/iter_N/ back to its
    original path (delete any new file you created this iteration), re-run TEST
    to confirm green, and log "reverted: <metric that regressed>".
 8. Append to docs/opencode/LOOP_LOG.md:
      iteration N | target gate/PDF | evidence strings | class | files
      | before → after (key metric) | KEEP or REVERT
 9. Repeat.

STOP when ANY of:
 - all gates G1–G8 pass on all four PDFs → write "ALL GATES PASS" and the final table
 - 12 iterations used
 - the same gate failed to improve in 2 consecutive KEPT-or-REVERTED attempts
   → STOP and report the 5 failing strings to the architect. Do not add another
   regex to force it. (Escalation: Claude/Gemini reviews the design.)

FINAL REPORT (exactly)
  ITERATIONS: n (kept k, reverted r)
  BASELINE → FINAL: scorecard rows
  GATES STILL FAILING: list with the evidence strings
  FILES CHANGED: list
  TESTS: last TEST output tail
Never say a gate passes unless the last SCORE output shows it. Paste the table.
```

## How to run it unattended

1. Merge W1, W2 first (they change the data contract).
2. Paste the block above into OpenCode with a free model.
3. When it stops, check `docs/opencode/LOOP_LOG.md` and run the SCORE command
   yourself. A stop with "GATES STILL FAILING" means it needs architect review,
   not another loop.

## Why this loop is safe for a weak worker

- Acceptance is numeric (scorecard), so "looks fine" never counts.
- Every change is reverted automatically on any regression.
- Precision-first rule stops the classic failure mode (a worker forcing
  recall up by minting fake equations): G6 and `omml_fake` block it.
- Anti-overfit rule + class-based fixes stop one-sample patching.
- It escalates instead of grinding when stuck.
