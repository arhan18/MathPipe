# LOOP_LOG — Math Engine v2 W3 (G5 closure loop)

Protocol: docs/opencode/LOOP_PROMPT.md. One entry per iteration.
Baseline = scorecard at loop start (= W4b state), snapshot at
/tmp/scorecard_baseline_loop/.

---

## Iteration 1 — G5 via heading span segmentation — REVERTED

**Target gate:** G5 (typeset% ≥ 0.90; fails on 4/4 PDFs; W3 mandate gate).
G6/G8 pass everywhere; G3/G4 are architect-accepted scorecard artifacts.

**Class fixed:** headings skip span segmentation. Two gates blocked the fix:
- `enrich_blocks` gated segmentation at `kind == "paragraph"`
  (src/mathengine/enrich.py, second loop) — headings never segmented;
- builder heading branch (src/word/builder.py) ignored `segments` and
  rendered `content` as one plain run.

**Test-first:** tests/test_heading_segments.py with the two exact
Mathematics - II.pdf leaking heading strings:
- `∫ ( 2 - x 2 - − 1 y 2 2 ) d x + ( x 2 + y 2 ) d y`
- `i) Define Cauchy-Riemann 2 2 / 0 equations. Check whether the function 𝑓(𝑧) = √|𝑥𝑦| satisfies`

4 tests written first → 3 failed (enrich dispatch ×2, builder oMath ×1),
then smallest fix: enrich `kind in ("paragraph", "heading")` + builder
heading branch honours segments via `_append_segments`. All 4 passed;
suite 111 OK.

**SCORE with fix (kept candidate):**

| PDF | recall | order | OMML | fake | typeset% | G5 |
|---|---|---|---|---|---|---|
| ICSE | 0.8499 → 0.8499 | same | 13 → 13 | 0 → 0 | 6 → 6 | ❌ → ❌ |
| MathSample | 0.9043 → 0.9043 | same | 58 → 58 | 0 → 0 | 76 → 76 | ❌ → ❌ |
| Mathematics - II | 0.8697 → **0.8396** | 0.6636 → **0.6490** | 24 → 27 | 0 → 0 | 82 → **100** | ❌ → **✅** |
| Maths-SQP | 0.8380 → 0.8380 | same | 69 → 69 | 0 → 0 | 84 → 84 | ❌ → ❌ |

**kept: no — reverted: word_recall(Mathematics_II) 0.8697 → 0.8396
(−0.0301) and order_recall 0.6636 → 0.6490 (−0.0146), both > 0.01
(protocol rule 7d: revert regardless of other gains).**

Reverted from /tmp/loop_backup/iter_1/{enrich.py,builder.py};
tests/test_heading_segments.py deleted. Post-revert TEST = 107 OK
(one transient failure on the very first post-revert run — test name
not captured; 5 consecutive runs green since). Post-revert SCORE =
baseline exactly.

**Regression root cause — scorecard join artifact, NOT content loss:**

1. Real document text: 0 tokens lost, +3 gained (extraction joining all
   w:t/m:t run texts with spaces). ADR-2 coverage verified by test
   (`"".join(seg.text) == heading text` for both strings).
2. scorecard.py `analyze_docx`: `full_text = " ".join(body_text + omml_text)`
   where each oMath contributes `"".join(m:t texts)` (line 110+118) —
   adjacent single-token m:t runs merge with no separator:
   `['x','2'] → "x2"` → tokenizer sees `x2`, not `x`,`2`.
   Moving 26 tokens from w:t (space-joined) into m:t (""-joined) lost
   25 hit-affecting token occurrences = exactly the 0.0301 drop
   (emulation reproduces 0.8697 / 0.8396 to 4 decimals; src = 798 tokens).
   Same artifact class the architect already ruled on for G3/G4 (W2).
3. Minimal honest variant (promote only the 2 G5-necessary leak headings,
   keep the 3rd equation heading `1 7 - 2 f ( x , y ) = ln ( x 2 + 3 y )`
   as plain text): recall = **0.8509 = −0.0188 → still > 0.01**.
   So NO honest heading fix satisfies rule 7d on Mathematics - II.
   Suppressing the 3rd promotion would be arbitrary (it is a genuine
   promotable equation heading, same rule as paragraphs).
4. Cannot be fixed in omml.py: scorecard joins m:t with "" regardless of
   run granularity; only literal space characters in m:t would separate
   the tokens — that visibly corrupts equation rendering in Word
   (metric gaming, forbidden).

**Conflict for architect:** on Mathematics - II, G5 requires moving
leaked symbols w:t → m:t (the definition of the gate), and every such
move charges scorecard recall ~0.019–0.030 — over the 0.01 revert budget.
G5 ≥ 0.90 on all 4 small PDFs and rule 7d are provably incompatible for
this PDF under the current scorecard assembly.

**G5 improvement this iteration: NONE (attempt 1, reverted).**
Files changed (restored): src/mathengine/enrich.py, src/word/builder.py —
both byte-identical to pre-iteration state.

---

## Iteration 2 — G5 via ∠ span classification — REVERTED (no-op)

**Target gate:** G5, worst value = ICSE_sample (typeset 6%, 15 leaked
symbols / 16 total).

**Class:** `∠` is in scorecard MATH_SYMBOLS but was absent from
spans `_MATH_SYMBOLS`, so the exact leaking line

`B A P (a) PSR (b) ∠ BPR (c) ∠ PTS`

produced ZERO math spans (probe: classify_token('∠') == 'PROSE').

**Test-first:** tests/test_angle_spans.py — 4 tests on exact ICSE
strings (ANGLE_LINE above, plus orphan `A ∠` and `∠ R` keep-as-text
guards). 2 failed first (classify → MATH, spans form), then the smallest
fix: add `∠` to spans._MATH_SYMBOLS. 4/4 green; suite 111 OK.

**SCORE with fix:** byte-level IDENTICAL to baseline (0 non-timing
diffs across all 4 metrics.json). All values unchanged: ICSE typeset 6,
G5 ❌ everywhere as before.

**Probe explanation (why no-op):** with ∠ classified, spans DO form —
but every angle span is then honestly rejected by the promotion gate:
- isolated `∠` → `too-short` (core len 1–2 < 3);
- `∠ BPR` / `∠ PTS` → `prose-word` (gate.py:213, `[A-Za-z]{3,}`
  non-function words, checked BEFORE structure) and `no-structure`;
- `A ∠` → `too-short`; `[3] ∠ R` → `no-structure`.
Promoting angle labels would require overriding the prose-word rule for
all-caps geometry labels — i.e. forcing the gate (forbidden), and it
would also misfire on prose acronyms (PSR, TSA) that share the shape.
`∠` exists only in ICSE (verified: 0 runs in the other 3 PDFs), and no
∠-paragraph currently promotes anything, so no promotion changed.

**kept: no — reverted: no metric improvement (0 diffs → keep-only-if-
better rule).** Restored from /tmp/loop_backup/iter_2/spans.py; tests/
test_angle_spans.py deleted. Post-revert TEST = 107 OK; post-revert
SCORE = baseline exactly.

**G5 improvement this iteration: NONE (attempt 2, reverted).**

---

## STOP — 2 consecutive G5 attempts without improvement → escalate

Stop rule from LOOP_PROMPT: same gate failed to improve in 2 consecutive
attempts (iter 1 reverted by rule 7d, iter 2 reverted as no-op). No
third attempt was made: evidence below shows no honest candidate remains
on any PDF. Loop stops at iteration 2 of max 12.

### BASELINE → FINAL (final = baseline; 0 kept, 2 reverted)

| PDF | recall | order | OMML | fake | typeset% | G5 |
|---|---|---|---|---|---|---|
| ICSE sample | 0.8499 → 0.8499 | 0.8498 → 0.8498 | 13 → 13 | 0 → 0 | 6 → 6 | ❌ |
| MathSample | 0.9043 → 0.9043 | 0.7762 → 0.7762 | 58 → 58 | 0 → 0 | 76 → 76 | ❌ |
| Mathematics - II | 0.8697 → 0.8697 | 0.6636 → 0.6636 | 24 → 24 | 0 → 0 | 82 → 82 | ❌ |
| Maths-SQP | 0.8380 → 0.8380 | 0.8439 → 0.8439 | 69 → 69 | 0 → 0 | 84 → 84 | ❌ |

G1/G2/G6/G8 green on 4/4 before and after (unchanged).

### GATES STILL FAILING — 5 representative strings with gate reasons

1. **ICSE** `B A P (a) PSR (b) ∠ BPR (c) ∠ PTS` — 2 leaked ∠.
   Classifier fix tried (iter 2, reverted no-op): formed spans are
   isolated `∠` → `too-short`; `∠ BPR` would be `prose-word` +
   `no-structure`. Honest ceiling even if promoted: ~0.19 < 0.90.
2. **ICSE** `... The value of ACB is : A ∠` — 1 leaked ∠:
   reading-order orphan, `A ∠` → `too-short` (core < 3). Irreducible.
3. **MathSample** `∞ , ∞ ) (B) (–2, 0) (C) (2, ∞ ) (D) (0, 2)` — 3
   leaked ∞ in an option list → gate `no-kernel`. Even if promoted:
   typeset 19→22 of 25 = 0.88 < 0.90 (G5 still fails). Neighbouring
   leaks `3 ×`, `∫ e`, `∫` → `too-short` (sub-3, promoting = G6 fake).
4. **Maths-SQP** `... (B) √34 units ... (D) 5√2 units` — √ leaks →
   `rendered-too-short`: m:rad renders √ outside <m:t>, so a promoted
   radical can never raise typeset% and forcing it would trip G6.
   `×`, `∈ R`, `∞)` → `too-short`. SQP ceiling = current 0.84.
5. **Mathematics - II** `∫ ( 2 - x 2 - − 1 y 2 2 ) d x + ( x 2 + y 2 ) d y`
   — **fix exists** (iter 1: heading segmentation; G5 0.82 → 1.00 ✅,
   fake 0, all tests green) but reverted by rule 7d: word_recall
   0.8697 → 0.8396 (−0.0301) / order −0.0146, both > 0.01. Cost is
   scorecard artifact, not content loss: full token bag loses 0
   (space-joined extraction) while scorecard assembles
   `" ".join(w:t… + per-oMath "".join(m:t))` (scorecard.py:110,118);
   adjacent single-char m:t runs merge (`x`,`2` → `x2`) — 25
   hit-affecting occurrences = exactly the drop; emulation reproduces
   0.8697/0.8396 to 4 dp. Minimal variant (2 leak headings only,
   excluding the genuine 3rd equation heading) = 0.8509 = −0.0188 →
   STILL > 0.01. Same artifact class the architect already ruled on
   for G3/G4 in W2.

### Honest G5 ceilings (proof)

| PDF | now | honest ceiling | blocker |
|---|---|---|---|
| ICSE | 0.06 | ~0.19 (only with ∠ promotion, which the prose-word/no-structure gates forbid) | gate-by-design |
| MathSample | 0.76 | 0.88 even with ∞-option fix | sub-3 leaks = G6 fakes |
| Mathematics - II | 0.82 | **1.00 (fix built & verified)** | rule 7d vs scorecard m:t-join artifact |
| Maths-SQP | 0.84 | 0.84 | rendered-too-short / G6-bound |

**G5 ≥ 0.90 on all 4 small PDFs is not achievable under the current
rules.** Decisions needed from the architect:
(a) reconcile rule 7d with G5 for Mathematics - II (bless the heading
fix as an approved artifact exception, or fix scorecard's m:t
assembly, or amend 7d), and/or
(b) restate the W3 done-criterion to the achievable target (e.g.
MathII ≥ 0.90 + others at honest ceiling), and/or
(c) design change: gate exemptions for geometric all-caps labels after
relation glyphs (touches keep-as-text principle — out of loop scope).

### FILES CHANGED (net after 2 iterations)

- `docs/opencode/LOOP_LOG.md` — created (this log).
- src/** and tests/** — byte-identical to loop baseline: enrich.py +
  builder.py restored from /tmp/loop_backup/iter_1, spans.py from
  /tmp/loop_backup/iter_2; test_heading_segments.py and
  test_angle_spans.py deleted. Suite 107 tests (baseline count) OK;
  scorecard identical to baseline (only `seconds` timing differs).

### TESTS

- Baseline suite after both reverts: `Ran 107 tests … OK` (5
  consecutive green runs; one transient failure observed on the first
  post-revert run of iter 1, test not captured, never reproduced).
- Scorecard after final revert: identical to /tmp/scorecard_baseline_loop.

---

## Architect ruling applied — heading fix reinstated + Symbol PUA + W4 verification

Architect ruled on the escalated conflict (2026-10-15): (1) reinstate the
iter-1 heading fix; the rule-7d revert is WAIVED — the Mathematics - II
recall drop (−0.0301 word / −0.0146 order) is the scorecard `"".join(m:t)`
join artifact (scorecard.py:110), not content loss, and do NOT add spaces
in omml.py; (2) G5 amended per-PDF thresholds — Mathematics - II ≥ 0.95,
MathSample ≥ 0.75, Maths-SQP ≥ 0.80, ICSE at baseline; (3) never promote
bare labels or radical fragments that would violate G6; (4) all rows keep
G6 (fake OMML) = 0.

**Reinstatement (test-first).** tests/test_heading_segments.py recreated
with the two exact Mathematics - II.pdf heading strings:

- `∫ ( 2 - x 2 - − 1 y 2 2 ) d x + ( x 2 + y 2 ) d y`
- `i) Define Cauchy-Riemann 2 2 / 0 equations. Check whether the function 𝑓(𝑧) = √|𝑥𝑦| satisfies`

4 tests: 3 failed pre-fix (enrich dispatch ×2, builder oMath ×1), all pass
after the two documented edits:

- src/mathengine/enrich.py — segmentation gate is now
  `if kind in ("paragraph", "heading")` (was `kind == "paragraph"`);
- src/word/builder.py — heading branch honours `segments` via
  `_append_segments` (math rides inside the heading paragraph, content is
  never emitted twice); the legacy branch stays byte-identical for
  segment-less headings.

**Legacy Symbol-font PUA mappings added to src/mathengine/normalize.py**
(preventive layer: extraction remaps PUA only for Symbol-typed fonts via
understanding/text.py `_SYMBOL_CODES`). tests/test_normalize_pua.py: 5
tests failed first, pass after. UNICODE_TO_LATEX gains \uf0f2→\int,
\uf0a2→\prime, \uf070→\pi, \uf071→\theta, \uf06c→\lambda, \uf0a5→\infty,
\uf0b9→\neq, \uf0ce→\in, \uf0c7→\cap; _ASCII_OPERATOR_GLYPHS gains
\uf02d→"-". `\uf0ce` → `\in` per architect follow-up: Adobe Symbol 0xCE is
element-of (∩ is 0xC7); the legacy converter's annotation had the typo.

**W4 verification.** `_extract_sqp_bracket_matrices` and
`_extract_definite_integral` absent from src/ (grep: no matches);
document-specific literal grep on enrich.py: no matches; `_table_is_matrix`
kept (enrich.py:292). Integral absorption verified on the built DOCX
files: every m:nary carries its bounds in m:sub/m:sup (e.g. ∫₋₄², ∫₀¹)
and differentials (dx/dy) sit inside the same m:oMath as formatted m:t
runs — never severed into trailing unformatted w:t. omml_fake = 0 on 4/4.

**SCORE — BEFORE → AFTER** (before = /tmp/scorecard_baseline_loop →
after = /tmp/scorecard):

| PDF | recall | order | OMML | fake | typeset% | G5 (amended) |
|---|---|---|---|---|---|---|
| ICSE sample | 0.8499 → 0.8499 | 0.8498 → 0.8498 | 13 → 13 | 0 → 0 | 6 → 6 | baseline (accepted) |
| MathSample | 0.9043 → 0.9043 | 0.7762 → 0.7762 | 58 → 58 | 0 → 0 | 76 → 76 | ✅ ≥ 0.75 |
| Mathematics - II | 0.8697 → 0.8396* | 0.6636 → 0.6490* | 24 → 27 | 0 → 0 | 82 → 100 | ✅ ≥ 0.95 |
| Maths-SQP | 0.8380 → 0.8380 | 0.8439 → 0.8439 | 69 → 69 | 0 → 0 | 84 → 84 | ✅ ≥ 0.80 |

\* architect-waived scorecard m:t-join artifact, not content loss.

**TESTS:** `Ran 116 tests … OK` (107 baseline + 4 heading + 5 PUA).
G2 PUA = 0, G6 fake = 0, G8 dup ≤ 1.15, G1 completes on 4/4; G3/G4/G7
remain the pre-existing architect-accepted scorecard artifacts.

**KEPT: yes — heading fix reinstated per ruling; PUA mappings added.**
Files changed: src/mathengine/enrich.py, src/word/builder.py,
src/mathengine/normalize.py, tests/test_heading_segments.py (recreated),
tests/test_normalize_pua.py (new). Backups: /tmp/architect_backup/.

---

## W5 — Release sealing & large-corpus verification (2026-10-15)

**Release backup.** Snapshot at `backups/v2_release/` — `apps/processor/src/mathengine/`,
`apps/processor/src/word/`, `apps/processor/tests/` (44 content files + `MANIFEST.sha256`).
`__pycache__/`, `*.pyc` and macOS AppleDouble `._*` sidecars excluded. Copy verified
against source with a checksum-mode rsync dry-run (no content diffs; only directory
mtime noise) and per-file `cmp` on the 5 seal files; `MANIFEST.sha256` (inside the
backup) records sha256 of every archived file.

**sha256 (release seal):**

```
f21ecb0b2f101ef5958a2e1416548c0e3d3f88102aeedfa0ddd473a1be107d4a  apps/processor/src/mathengine/enrich.py
75b1a2d0116ee3d8cae9d2f32cf9cc73dececd24761862bd6a5007575f9f95c0  apps/processor/src/mathengine/spans.py
360e96cb4f066f64cf45183341e46d9a4ac954b5b50e2c9faba967c503602c6d  apps/processor/src/mathengine/gate.py
4024e73d73a74a3e4487cb873d23b479419e83e6a1f9c64e27257ae73db6d65b  apps/processor/src/mathengine/recognize.py
9eeca871f038f15123691163b0e3c853d2785274072c5c666979689e3a3493f7  apps/processor/src/word/builder.py
```

**Final scorecard summary (accepted v2 state; `Ran 116 tests … OK`):**

| PDF | recall | order | OMML | fake | typeset% | G5 (amended) |
|---|---|---|---|---|---|---|
| ICSE sample | 0.8499 | 0.8498 | 13 | 0 | 6 | baseline (accepted) |
| MathSample | 0.9043 | 0.7762 | 58 | 0 | 76 | ✅ ≥ 0.75 |
| Mathematics - II | 0.8396* | 0.6490* | 27 | 0 | 100 | ✅ ≥ 0.95 |
| Maths-SQP | 0.8380 | 0.8439 | 69 | 0 | 84 | ✅ ≥ 0.80 |

\* architect-waived scorecard `m:t`-join artifact (see ruling section above).

**Large-corpus verification (no `--skip-big`).** Command:
`apps/processor/.venv/bin/python apps/processor/tools/scorecard.py
--pdf-dir "$HOME/Downloads/Tests for maths converter" --only "QueBank"
--out-dir /tmp/scorecard_big`. 100+ page `12th_Maths_EngMed_QueBank_MSCERT.pdf`
graded end-to-end in 95.8 s: **G1 ✅ completes (DOCX written), G2 ✅ PUA = 0,
G8 ✅ dup 0.919.** 905 OMML (f 361 / nary 28 / rad 131 / sSup 31 / sSub 65 /
func 31), 12 tables, 4 figures, 10 equation fallbacks.

| PDF | recall | order | OMML | fake | typeset% | PUA | tbl | dup |
|---|---|---|---|---|---|---|---|---|
| 12th_Maths_EngMed_QueBank_MSCERT.pdf | 0.8705 | 0.7772 | 905 | 3 | 60 | 0 | 12 | 0.919 |

Gates: `✅ ✅ ❌ ❌ ❌ ❌ ❌ ✅` (G1 G2 G3 G4 G5 G6 G7 G8). G3/G4/G7 shortfalls are
the pre-existing architect-accepted artifact class (they fail on the 4 acceptance
PDFs too; QueBank's 0.8705 / 0.7772 is in-band with — better than — Mathematics - II).
**G6 = 3 is a new observation for this corpus** (acceptance set = 0 on 4/4): the
three flagged blocks are `-1` (paragraph "9) -1"), `-8` (paragraph "9. a) -8") and a
rad block (`m:rad` element present; visible `m:t` runs = "13", paragraph "8) C) 13")
— all three by the <3-meaningful-chars rule; they are short option/answer values,
exactly the bare-fragment class the promotion gate is meant to keep as text.
Reported for architect disposition; W5 scope is sealing + scalability verification.

Artifacts: `/tmp/scorecard_big/` (`scorecard.md`, `scorecard.json`, per-PDF
`metrics.json` + `out.docx`). Key numbers are mirrored above because `/tmp` is volatile.

**Doc seals.** W1–W4 marked `[x] COMPLETE & VERIFIED` in
`docs/opencode/WORK_ORDERS.md`; spec task graph T1–T4 marked `(DONE)` in
`docs/MATH_ENGINE_V2_SPEC.md` §3.

---

## W6 — Unified End-to-End CLI (`convert`) & figure binding (2026-10-15)

**CLI.** One-step `convert` subcommand in `apps/processor/src/cli.py`
(`convert <input.pdf> -o <output.docx> [--mode standard|verified] [--max-pages N] [--max-mb N]`):
pipeline → DOCX; failures exit 2 with JSON error and write nothing. Figure bytes
are recovered from the model's `imageBase64` (`_figure_assets_from_model()`,
architect-approved canonical path across JSON serialization) and passed to
`build_docx(figures=…)` in both `convert` and `build-docx`.

**Tests.** `Ran 120 tests … OK` (116 → 120; new `tests/test_cli.py`); scorecard
(`--skip-big`) field-by-field vs the accepted baseline: all 4 rows identical,
0 differences.

**Smoke (`Maths-SQP.pdf`, one command).** 1,706,247 bytes / 69 equations /
7 figures / 1 table — in-package: 69 `<m:oMath>`, 7 `<w:drawing>`, 7 media
parts, 0 placeholders.

**Modal parity (W7).** `modal_app.py` `run_job` now passes figures the same way:
`build_docx(result.model, figures=_figure_assets_from_model(result.model))`.

---

## W8 — Universal promotion gate on whole-line blocks (2026-10-17)

**Root cause (W5 QueBank observation).** The whole-line promotion path in
`enrich.py` (`enrich_blocks`) checked the MathIR kernel and the zero-denominator /
garbage guards but never called `is_promotable` (`gate.py`). Short answer/option
fragments (paragraphs `9) -1`, `9. a) -8`, `8) C) √13`) bypassed the
<3-rendered-meaningful-chars rule and became standalone OMML → QueBank G6 = 3.

**Fix.** After the zero/garbage guard and before `block.kind = "equation"`:
`promotable, reason = is_promotable(candidate_text, recognition.mathir)` — on
rejection the block keeps its text, records `mathHint` (fallback "text", reason
in the note) and increments the counted fallback via `_note_inline_fallback`.
Single gate; `gate.py` untouched, no new rules.

**Tests.** `Ran 126 tests … OK` (120 → 126). New
`tests/test_gate.py::TestWholeLinePromotionGate` (6 tests): `9) -1` → stays
text (`too-short`); `9. a) -8` → `too-short`; `8) C) √13` → `rendered-too-short`
(rad trigger recovered from the W5 artifact); `8) C) 13` stays text (invariant —
never promoted); `x^2 + y^2 = 1` and `∫_0^1 f(x)dx` still promote. Pre-fix
reproduction: all three flagged paragraphs promoted to whole-line equations.

**SCORE — BEFORE → AFTER (QueBank; /tmp/scorecard_big → /tmp/scorecard_quebank):**

| PDF | recall | order | OMML | fake | typeset% | PUA | tbl | dup |
|---|---|---|---|---|---|---|---|---|
| 12th_Maths_EngMed_QueBank_MSCERT.pdf | 0.8705 → 0.8737 | 0.7772 → 0.7806 | 905 → 880 | 3 → 0 | 60 → 60 | 0 | 12 | 0.919 → 0.921 |

Gates `✅ ✅ ❌ ❌ ❌ ❌ ❌ ✅` → `✅ ✅ ❌ ❌ ❌ ✅ ❌ ✅` (G1–G8) — **G6 green on
the 103-page corpus**. Net OMML −25 = 27 demoted (the 3 G6 fakes + 24
unstructured / prose-glued fragments: `+c2`, `+cx+4`, `xx+c`, `sin2x+cx`,
`2log4+-`, `π1-log242`, `EX=7,VarX=5.8334`, `secx2+c3`, …) minus 2 inline span
re-promotions (`EX=7`, `EX=0.7`). Fallbacks 10 → 37; typeset ratio
0.6038 → 0.5978.

**Core-4 (`--skip-big`; /tmp/scorecard_w7 → /tmp/scorecard_w8).** Field-level
diff = 5 fields, all Maths-SQP: OMML 69 → 68, equations 69 → 68, fallbacks
0 → 1, dup 0.865 → 0.866, word_recall 0.838 → 0.8384 — single demotion
`(D) 2sin −1 𝑥` (gate reason `no-structure`: flattened superscript leaves no
relation/script/slash/root). ICSE 13/0, MathSample 58/0, Mathematics - II 27/0
byte-identical; G6 = 0 on 4/4.

**Architect ruling (2026-10-17):** APPROVED & ACCEPTED — the SQP demotion and
the QueBank fragment demotions are intended precision-first behavior; G6 is now
green across the entire test corpus.

**Files changed:** `src/mathengine/enrich.py` (whole-line gate call),
`tests/test_gate.py` (6 tests). Backups: `/tmp/worker_backup/w8/`. Artifacts:
`/tmp/scorecard_quebank/`, `/tmp/scorecard_w8/`. Release seal refreshed:
`backups/v2_release/` carries this `enrich.py` + `test_gate.py` with an updated
`MANIFEST.sha256`.
