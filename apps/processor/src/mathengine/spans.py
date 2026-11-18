"""ADR-3 — inline math span detection. Token-level and geometry-free.

Pure functions, no I/O: ``split_math_spans`` partitions a paragraph string
into ordered ``text``/``math`` spans. It never guesses whether a span IS
math — that judgement (recognizer + promotion gate) belongs to the
enricher. The one guarantee here is losslessness::

    "".join(s.text for s in split_math_spans(text)) == text

Whitespace between spans stays inside the preceding text span, so the
partition can be re-emitted without adding or losing a single character.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    kind: str  # "text" | "math"
    text: str


_TOKEN_RE = re.compile(r"\([A-Da-d]\)(?=\S)|\S+")

#: Math glyphs (symbols, Greek, relations) that mark a token as math.
#: Dashes are deliberately absent: they are weak evidence ("pages 3–5")
#: and reach MATH only through digit+operator adjacency, which the gate
#: then re-checks.
_MATH_SYMBOLS = frozenset(
    "∑∫∏√∞∂∇∆±×÷≠≤≥≈≡∈∉∪∩⊂⊃∧∨¬∀∃→←↔⇒⇐⇔"
    "αβγδεζηθικλμνξοπρστυφχψωΓΔΘΛΞΠΣΦΨΩ"
)

#: Digits glued to an operator/letter ("3x", "2024-25", "(8" are digit
#: adjacency, never bare prose.
_DIGIT_OPERATOR_RE = re.compile(r"[A-Za-z+\-*/=^_<>≤≥≠≈()\[\]{}−–—⁄]")

_FUNCTION_PREFIX_RE = re.compile(
    r"^(?:sin|cos|tan|cot|sec|csc|log|ln|exp|lim|max|min|det|sqrt)(?:\(|[^A-Za-z]|$)"
)
#: Single-letter function calls: "f(x)", "E(X)", "g(t)".
_FUNCTION_CALL_RE = re.compile(r"^[A-Za-z]\(")
#: Differentials ("dx", "dy", "dθ", "dt") — math even without digits.
_DIFFERENTIAL_RE = re.compile(r"^d[xyztθλμσφ]$")
#: Bare numbers ("2", "-4", "3.5") join runs; the gate rejects them alone.
_BARE_NUMBER_RE = re.compile(r"^[+.\-−–—]?\d+(?:\.\d+)?$")
_SINGLE_LETTER_RE = re.compile(r"^[A-Za-z]$")
#: Standalone glue: operators, separators and fences between math tokens.
_GLUE_OP_RE = re.compile(r"^[=,+\-−–—×÷±*/<>]$")
_GLUE_FENCE_RE = re.compile(r"^[\(\)\[\]\{\}]$")
#: Option/label fragments like "(C)" glue as fences at run edges.
_LABEL_FENCE_RE = re.compile(r"^\([A-Za-z]\)$")

#: Sentence punctuation trimmed from run edges (kept as text).
_EDGE_PUNCT = ",;:!?."

#: Categories that can join a run.
_RUN_KINDS = frozenset({"MATH", "GLUE"})

# Characters a token must NOT be split on for classification: the token
# stream is whitespace-delimited (ADR-3 step 1); everything inside a token
# stays one unit so scripts ("x^{2}") and fractions ("1/81") survive.


def _fold(tok: str) -> str:
    # NFKC folds math-italic 𝑥 → x and superscripts ² → 2 so the ASCII
    # rules see letters/digits; classification only, spans keep originals.
    try:
        return unicodedata.normalize("NFKC", tok)
    except Exception:
        return tok


def classify_token(tok: str) -> str:
    """MATH | GLUE | PROSE for one whitespace-delimited token."""
    if not tok:
        return "PROSE"
    folded = _fold(tok)
    if _SINGLE_LETTER_RE.match(folded):
        # Single letters are variables: GLUE between math, harmless alone
        # (a run needs at least one MATH token to survive).
        return "GLUE"
    if _FUNCTION_PREFIX_RE.match(folded) or _FUNCTION_CALL_RE.match(folded):
        return "MATH"
    if _DIFFERENTIAL_RE.match(folded):
        return "MATH"
    if any(ch in _MATH_SYMBOLS for ch in folded):
        return "MATH"
    if folded[0] in "^_":
        # Script markers from blocks.py attachment ("^{2}", "_{n}").
        return "MATH"
    if _BARE_NUMBER_RE.match(folded):
        return "MATH"
    if re.search(r"\d", folded) and _DIGIT_OPERATOR_RE.search(folded):
        return "MATH"
    if _LABEL_FENCE_RE.match(folded):
        # Option labels are REGION BOUNDARIES, not math glue. ADR-3 says
        # labels break runs; classifying them as GLUE let a run swallow
        # "(B)", so four MCQ options were parsed as one expression and the
        # labels survived as stray parenthesized letters inside the OMML
        # ("(A)cos-1x(B)cos-1(2x)(C)..."). A label breaks the run and
        # stays text; each option value then becomes its own math span.
        return "PROSE"
    if _GLUE_OP_RE.match(folded) or _GLUE_FENCE_RE.match(folded):
        return "GLUE"
    return "PROSE"


def _is_bare_letter(tok: str) -> bool:
    return bool(_SINGLE_LETTER_RE.match(_fold(tok)))


def split_math_spans(text: str) -> list[Span]:
    """Split ``text`` into ordered text/math spans (lossless, ADR-3).

    Runs are maximal MATH/GLUE token sequences containing at least one
    MATH token; PROSE tokens (words of 3+ letters that are not function
    names, bare punctuation, labels) break runs, so math never swallows
    the prose around it. Leading/trailing non-letter glue (fences,
    dangling operators, option labels) and sentence punctuation are
    trimmed off the run edges and stay text.
    """
    if not text:
        return []
    tokens = [(m.group(0), m.start(), m.end()) for m in _TOKEN_RE.finditer(text)]
    classes = [classify_token(t) for t, _, _ in tokens]

    spans: list[Span] = []
    cursor = 0  # offset where the pending text span starts
    i = 0
    n = len(tokens)
    while i < n:
        if classes[i] not in _RUN_KINDS:
            i += 1
            continue
        j = i
        saw_math = False
        while j < n and classes[j] in _RUN_KINDS:
            if classes[j] == "MATH":
                saw_math = True
            j += 1
        if not saw_math:
            i = j
            continue
        # Trim non-letter glue at the run edges ("(C)", dangling "=").
        start_i, end_i = i, j - 1
        while start_i <= end_i and classes[start_i] == "GLUE" and not _is_bare_letter(tokens[start_i][0]):
            start_i += 1
        while end_i >= start_i and classes[end_i] == "GLUE" and not _is_bare_letter(tokens[end_i][0]):
            end_i -= 1
        if start_i > end_i or not any(classes[k] == "MATH" for k in range(start_i, end_i + 1)):
            i = j
            continue
        start = tokens[start_i][1]
        end = tokens[end_i][2]
        # Sentence punctuation glued to a run edge ("1/81,") stays text.
        while end > start and text[end - 1] in _EDGE_PUNCT:
            end -= 1
        while start < end and text[start] in _EDGE_PUNCT:
            start += 1
        if start >= end:
            i = j
            continue
        if cursor < start:
            spans.append(Span("text", text[cursor:start]))
        spans.append(Span("math", text[start:end]))
        cursor = end
        i = j
    if cursor < len(text):
        spans.append(Span("text", text[cursor:]))
    if not spans:
        spans.append(Span("text", text))
    return spans
