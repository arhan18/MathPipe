# Math Engine v2 — Architecture Spec

Status: approved design, ready for delegated implementation.
Author role: architect/orchestrator. Implementation role: OpenCode workers.
Acceptance authority: `apps/processor/tools/scorecard.py` (not agent opinion).

## 1. Diagnosis (measured, baseline 2026-10-14)

Command: `apps/processor/.venv/bin/python apps/processor/tools/scorecard.py --pdf-dir "$HOME/Downloads/Tests for maths converter" --skip-big`

| PDF | word recall | order recall | OMML | fake OMML | frac/nary/rad/mat | typeset % |
|---|---|---|---|---|---|---|
| ICSE sample | 0.85 | 0.86 | 0 | 0 | 0/0/0/0 | 0 |
| MathSample | 0.94 | 0.82 | 25 | 11 | 24/0/0/1 | 0 |
| Mathematics - II | 0.95 | 0.72 | 3 | 0 | 3/0/0/0 | 0 |
| Maths-SQP | 0.92 | 0.91 | 42 | 18 | 40/2/5/0 | 4 |

Reading order, tables, XML safety and honest verification were fixed in the
previous round. What remains is almost entirely **math fidelity**.

### Root causes (verified in code, not guessed)

1. **No inline math span segmenter.** `enrich.enrich_blocks` only promotes a
   paragraph to an equation when the *whole line* scores as math
   (`is_equation_line`). Math embedded in prose ("Evaluate ∫ x²y dx dy",
   "then compute ∇×v") never reaches the recognizer. `mathHint` literally says
   "inline splitting lands with the ML stage". That stage does not exist, and
   we do not need ML to do it.
2. **Inline math is appended after the host text, and the host text keeps the
   math.** `builder._append_inline_math` adds `<m:oMath>` runs at the *end* of
   a paragraph whose `w:t` already contains the same math as plain text. Math
   appears twice and in the wrong position. (Gate G8.)
3. **Per-document patches stand in for general logic.**
   `enrich._extract_sqp_bracket_matrices` hard-codes `"32."`, `"each"`,
   `"𝐴𝐵"`, `"and hence"`. Heuristic regex stacks (`_extract_stacked_fractions`,
   `_valid_fraction_operand`, ~250 lines) exist because fractions are
   re-derived from flattened text after geometry was thrown away.
4. **Fake OMML escapes the detector.** 11 and 18 fake blocks (option-letter
   fragments such as `a14`, marks tags) still ship in MathSample/SQP. (G6.)
5. **The OMML renderer is NOT the problem.** `word/omml.py` already renders
   fraction, root, scripts, function, matrix, fence, accent, limit (m:nary),
   underover, cases. Do not rewrite it.

## 2. Architecture decisions

### ADR-1 — The scorecard is the contract
Every task is accepted or rejected by scorecard gates G1–G8 plus the existing
53 unit tests. A worker's claim of completion has no weight.

### ADR-2 — Paragraphs become ordered segments
New optional field on a block: `extra["segments"]`, a list preserving source
order and covering the paragraph text **exactly once**:

```json
[
  {"kind": "text", "text": "Evaluate "},
  {"kind": "math", "text": "∫ x² y dx dy", "mathir": {"schemaVersion": "1.0", "root": {...}},
   "latex": "...", "recognizer": "det-ascii-0.x", "confidence": 0.9},
  {"kind": "text", "text": " over the region R"}
]
```

Invariants (each must be a unit test):
- `"".join(seg["text"] for seg in segments) == block.text` (lossless; whitespace-normalised).
- A `math` segment always carries valid MathIR (`validate_mathir == []`) and
  `has_math_kernel(root) is True`. Otherwise it is demoted to `text` — never guessed.
- Builder emits segments in order inside ONE `<w:p>`: `w:r` for text,
  `<m:oMath>` for math. The covered text is not emitted a second time.
- If a `math` segment fails to render (`UnsupportedConstruct`), the builder
  emits its `text` as a plain run and increments `equation_fallbacks`.
- No `segments` field ⇒ legacy path unchanged (so the change is incremental).

### ADR-3 — Span detection is token-level and geometry-free
New module `mathengine/spans.py`, pure functions, no I/O:

```python
def split_math_spans(text: str) -> list[Span]   # Span(kind, text, start, end)
```

Algorithm:
1. Whitespace tokenise keeping offsets.
2. Classify each token: `MATH` (contains digit+operator, `^`/`_` braces from
   blocks.py script attachment, Greek, `∫∑∏√∞≤≥≠≈∂∇±×÷`, function names
   `sin cos tan log ln exp lim sec`, differentials `dx dy dz dθ dt`,
   fraction tokens `a/b`, single-letter variables adjacent to a MATH token),
   `GLUE` (single letters, `(`, `)`, `,`, `=`, `+`, `-` between two MATH
   tokens), or `PROSE`.
3. Grow maximal runs of `MATH`/`GLUE`; trim leading/trailing GLUE and
   sentence punctuation; balance brackets; never cross a prose word of 3+
   letters that is not a function name.
4. Promote a run only if the recognizer returns structure
   (`has_math_kernel`) with confidence not `escalate`, and the run passes the
   single promotion gate in ADR-5. Otherwise the run stays `text`.

### ADR-4 — Recognizer grows by data, not by special cases
Extend `recognize.py` / `normalize.py` only for constructs that spans can now
reach: definite integrals with braced bounds, `√`, inverse trig (`sin⁻¹ x` →
`function sin` with `superscript -1`), `d/dx` operator pair, `|x|`, vectors
with hats, `lim_{x→a}`. Each gets a unit test with the exact PDF-extracted
string as input.

### ADR-5 — One promotion gate (kills fake OMML)
`mathengine/gate.py: is_promotable(span_text, mathir) -> tuple[bool, str]`.
Replaces the scattered guards. Reasons are returned and counted so rejection
is observable. Rejects: option-label-only, marks tags `(N x M)`, bare
numbers, URL/long-token, stutter/garbage glyphs, zero denominators, anything
under 3 meaningful characters. Existing helpers
(`_mathir_has_garbage`, `_mathir_has_zero_denominator`, `has_math_kernel`)
move here unchanged and are called from here.

### ADR-6 — Delete overfitting
Remove `_extract_sqp_bracket_matrices` and its call site. Matrices are
recovered only from the geometry path (table blocks → `_table_is_matrix`),
which is general. Document-specific literals ("32.", "each", "𝐴𝐵") must not
remain anywhere in `src/`. Keep `_extract_definite_integral`'s idea but fold
it into spans (bounds become part of the span instead of a side channel).

### ADR-7 — Reported numbers must be measured
`builder.report["equations"]` counts only OMML blocks actually written to the
package. The scorecard re-measures from the DOCX; any disagreement larger than
0 is a bug in the builder report.

## 3. Task graph

```
T0 scorecard (DONE)
 └─ T1 segments contract + builder      (no behaviour change; unlocks everything) (DONE)
     ├─ T2 spans.py + gate.py + enrich integration   (the core feature) (DONE)
     │    └─ T3 recognizer gap closure (data-driven from T2 failures) (DONE)
     └─ T4 delete SQP hack + fold integral extractor (after T2 proves general path) (DONE)
T5 repetition loop (see docs/opencode/LOOP_PROMPT.md) drives T3 until gates pass
T6 figures: OUT OF SCOPE here (separate track; asset extraction exists, G-gates
   do not cover it yet)
```

| Task | Files | Owner | Done when |
|---|---|---|---|
| T1 (DONE) | `word/builder.py`, `understanding/blocks.py` (Block.extra), `contract/document_model.py` (pass-through) | OpenCode | New tests pass; scorecard unchanged on all gates (pure refactor) |
| T2 (DONE) | new `mathengine/spans.py`, `mathengine/gate.py`; edit `mathengine/enrich.py` | OpenCode, reviewed by Gemini | G6 passes (0 fake), G8 passes, OMML count rises on MathSample/SQP/Maths-II, 53+new tests green |
| T3 (DONE) | `mathengine/recognize.py`, `normalize.py` | OpenCode loop | G5 ≥ 0.90 on the 4 small PDFs |
| T4 (DONE) | `mathengine/enrich.py` | OpenCode | `grep -rn "sqp\|each\\s+" src/` clean, scorecard not worse |

Escalation: if a worker fails the same gate twice, stop and return the
failing sample strings to the architect rather than adding another regex.

## 4. Out of scope (stated honestly)

- Figures/diagrams (ICSE has 30 figure placeholders). Separate track.
- ML recognizer. The deterministic span approach must be exhausted first;
  `GatedRecognizer` already exists for a licensed model later.
- Handwritten or scanned PDFs.

## 5. Risks

- Span growth can swallow prose around a variable ("Find y if x = 2"). Mitigation:
  the 3-letter prose-word stop rule and mandatory kernel gate; any doubt keeps text.
- Over-promotion is worse than under-promotion (a wrong editable equation
  misleads). Gates favour precision; recall is raised by the loop, one failing
  sample at a time.
