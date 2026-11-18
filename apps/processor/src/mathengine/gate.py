"""ADR-5 — the single promotion gate for inline math.

Every candidate that would become an editable equation passes through
:func:`is_promotable`. Rejection returns a stable reason code so a miss is
observable instead of silent. The gate is precision-first: a wrong editable
equation is worse than plain text, so anything doubtful stays text.

The MathIR guards that used to live scattered in ``enrich.py``
(``_mathir_has_garbage``, ``_mathir_has_zero_denominator`` and the
``has_math_kernel`` call) moved here unchanged and are called from here;
``enrich.py`` imports them from this module (one definition, no copies).
"""
from __future__ import annotations

import re

from .mathir import has_math_kernel

__all__ = [
    "is_promotable",
    "has_math_kernel",
    "_mathir_has_garbage",
    "_mathir_has_zero_denominator",
]

# ---------------------------------------------------------------------------
# MathIR guards (moved from enrich.py — single definition, called from here)
# ---------------------------------------------------------------------------

#: Zero denominator: a fraction over an exact zero (π/0 from limits
#: misread as a fraction) is a division-by-zero hallucination — never an
#: equation. Matched after fence/space stripping ("(0)", "0.0").
_ZERO_DEN_RE = re.compile(r"^[\u2212\u2013\u2014-]?0+(\.0+)?$")

#: Extraction-artifact glyphs that are never valid fraction content:
#: extensible-bracket PUA pieces (⎛⎜⎝⎞⎟⎠) and stray modifier marks
#: (ˆˇ˘˙) from hat-soup ("(sin⎜π)/3", "(1ıˆ–2ˆ–)/5").
_GARBAGE_ARTIFACT_CHARS = frozenset("⎛⎜⎝⎞⎟⎠ˆˇ˘˙")

#: Doubled letters ("1yy", "qqssss", "ππ") are extraction stutter, never
#: math — genuine variables/functions never repeat a letter ("sin", "cos",
#: "log", "exp", "dx"). Digits are excluded ("11", "22" are real).
_DOUBLED_LETTER_RE = re.compile(r"([A-Za-z])\1")

#: Pure-letter runs of length >= 4 that are not function-led ("integrating",
#: "qqssss") are prose/debris, never equation content.
_PROSE_SIDE_RE = re.compile(r"^[A-Za-z]{4,}$")

#: Function-led runs are not prose even when long ("sin", "cos", "log").
_FRACTION_OPERAND_FUNC_RE = re.compile(
    r"^(sin|cos|tan|log|ln|sec|exp|dx|dy|dz|dθ|dt)"
)


def _strip_side_fences(s: str) -> str:
    return re.sub(r"[\s\(\)\[\]\{\}.,;:!?\"\']+", "", s or "")


def _is_zero_denominator_text(den: str) -> bool:
    """True when a denominator side is an exact zero (π/0 hallucination)."""
    import unicodedata as _ud
    try:
        folded = _ud.normalize("NFKC", den or "")
    except Exception:
        folded = den or ""
    return bool(_ZERO_DEN_RE.match(_strip_side_fences(folded)))


def _mathir_text_values_inline(node, out: list) -> list:
    if isinstance(node, dict):
        if node.get("type") in ("text", "operator"):
            out.append(str(node.get("value", node.get("symbol", ""))))
        for value in node.values():
            if isinstance(value, (dict, list)):
                _mathir_text_values_inline(value, out)
    elif isinstance(node, list):
        for value in node:
            _mathir_text_values_inline(value, out)
    return out


def _mathir_has_zero_denominator(mathir_doc: dict) -> bool:
    """True when any fraction node divides by an exact zero."""
    stack: list = [mathir_doc.get("root", {})] if isinstance(mathir_doc, dict) else []
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if cur.get("type") == "fraction":
                den_texts = [t for t in _mathir_text_values_inline(cur.get("denominator"), []) if t.strip()]
                if den_texts and _is_zero_denominator_text(
                    "".join(re.sub(r"\s+", "", t) for t in den_texts)
                ):
                    return True
            for value in cur.values():
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(cur, list):
            stack.extend(cur)
    return False


def _mathir_has_garbage(mathir_doc: dict) -> bool:
    """True when MathIR text nodes carry extraction stutter/artifacts.

    Catches promotion-path hallucinations ("1yy", "227qqssssππ=") that never
    pass through the fraction extractor: doubled letters, artifact glyphs
    and long non-function letter runs are never genuine math content.
    """
    stack: list = [mathir_doc.get("root", {})] if isinstance(mathir_doc, dict) else []
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if cur.get("type") == "text":
                v = str(cur.get("value", ""))
                if any(ch in _GARBAGE_ARTIFACT_CHARS for ch in v):
                    return True
                if _DOUBLED_LETTER_RE.search(v):
                    return True
                core = _strip_side_fences(v)
                if core and _PROSE_SIDE_RE.match(core) and not _FRACTION_OPERAND_FUNC_RE.match(core):
                    return True
            for value in cur.values():
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(cur, list):
            stack.extend(cur)
    return False


# ---------------------------------------------------------------------------
# Span text rules (ADR-5)
# ---------------------------------------------------------------------------

#: Meaningful characters — the scorecard's own G6 definition (whitespace
#: and brackets stripped), so the gate can never be more permissive than
#: the detector it must satisfy.
_MEANINGFUL_RE = re.compile(r"[\s()\[\]]+")

#: Option-label-only fragments: "(A)", "a14", "A 1", "B2". G6 flags the
#: same set; the gate rejects it before it can become OMML.
_OPTION_ONLY_RE = re.compile(r"[A-Da-d]\d*")

#: Marks multipliers: "(8 × 2)", "(8 x 2)" (matched whitespace-free).
_MARKS_MULT_RE = re.compile(r"^\(\d+[×xX*]\d+\)$")

#: A bare integer (option values, folio debris, page numbers) is never an
#: equation on its own.
_BARE_NUMBER_RE = re.compile(r"^[−–—+-]?\d+(?:\.\d+)?$")

#: URL / download-stamp traces: footers are never equations.
_URL_RE = re.compile(r"://|www\.|https?://|ftp\.", re.IGNORECASE)

#: Genuine structure: relations, scripts, fraction bars, n-ary/integral
#: symbols, roots, relations and differentials. Weak characters ("+", "-")
#: are deliberately NOT structure — a date range ("2024-25") or a prose
#: dash must never pass on them alone.
_STRUCTURE_RE = re.compile(
    r"[=<>≤≥≠≈≡^_/∫∑∏√∞∂∇±×÷→←∈∉∪∩]"
    r"|[⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉]"
    r"|d[xyztθ]"
)

#: Natural-language word of 3+ letters inside a span: prose glued to math
#: ("x/2-plane", "Evaluate∫...") is not an equation. Function names are
#: exempt because they ARE mathematics.
_PROSE_WORD_RE = re.compile(r"[A-Za-z]{3,}")
_FUNCTION_WORDS = frozenset({
    "sin", "cos", "tan", "cot", "sec", "csc", "log", "ln", "exp", "lim",
    "max", "min", "det", "gcd", "inf", "sup", "sinh", "cosh", "tanh",
})


def _span_has_prose_word(span_text: str) -> bool:
    for word in _PROSE_WORD_RE.findall(span_text):
        if word.lower() not in _FUNCTION_WORDS:
            return True
    return False


def _rendered_meaningful_len(mathir_doc: dict) -> int:
    """Meaningful length of the text the renderer will put in <m:t>.

    Mirrors the scorecard's G6 measurement exactly: it concatenates every
    <m:t> of one oMath block (no separators) and strips whitespace and
    brackets. We approximate the same value from the MathIR by joining
    every inline text/operator value with no separator.
    """
    joined = "".join(_mathir_text_values_inline(mathir_doc, []))
    return len(_MEANINGFUL_RE.sub("", joined))


def is_promotable(span_text: str, mathir_doc: dict) -> tuple[bool, str]:
    """(promotable, reason). Text rules first, then MathIR guards.

    ``reason`` is "ok" on success; otherwise a stable reason code the
    caller can count ("too-short", "option-label-only", "marks-tag",
    "bare-number", "url", "long-token", "prose-word", "no-structure",
    "no-mathir", "no-kernel", "rendered-too-short", "rendered-label-only",
    "garbage", "zero-denominator").
    """
    text = span_text or ""
    core = _MEANINGFUL_RE.sub("", text)
    if len(core) < 3:
        return False, "too-short"
    if _URL_RE.search(text):
        return False, "url"
    if _OPTION_ONLY_RE.fullmatch(core):
        return False, "option-label-only"
    if _MARKS_MULT_RE.fullmatch(re.sub(r"\s+", "", text)):
        return False, "marks-tag"
    if _BARE_NUMBER_RE.fullmatch(core):
        return False, "bare-number"
    if _span_has_prose_word(text):
        return False, "prose-word"
    if not _STRUCTURE_RE.search(text):
        if max((len(t) for t in text.split()), default=0) > 24:
            return False, "long-token"
        return False, "no-structure"
    if not isinstance(mathir_doc, dict) or not isinstance(mathir_doc.get("root"), dict):
        return False, "no-mathir"
    root = mathir_doc.get("root")
    if not has_math_kernel(root):
        return False, "no-kernel"
    if _mathir_has_garbage(mathir_doc):
        return False, "garbage"
    if _mathir_has_zero_denominator(mathir_doc):
        return False, "zero-denominator"
    # G6 measured on the RENDERED equation, not the span text: a span can
    # be long enough yet type set to nothing meaningful ("5 / 2" renders
    # as "52", "√34" as "34", "5√2" as "5 2"). The scorecard counts any
    # oMath whose <m:t> concatenation has <3 meaningful chars or looks
    # like an option label as fake OMML, so the gate must reject those
    # renders before they can exist.
    rendered_core = _MEANINGFUL_RE.sub(
        "", "".join(_mathir_text_values_inline(mathir_doc, []))
    )
    if len(rendered_core) < 3:
        return False, "rendered-too-short"
    if _OPTION_ONLY_RE.fullmatch(rendered_core):
        return False, "rendered-label-only"
    return True, "ok"
