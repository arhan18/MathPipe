"""Stage 8a — math region detection (§11.1).

Evidence sources (deterministic, no ML): mathematical symbol density,
operator characters, digit/letter adjacency patterns, italic serif runs,
and equation-number shapes. Each candidate carries its evidence so later
stages can route by confidence (§60.1).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

MATH_SYMBOLS = set("∑∫∏√∞∂∇∆±×÷≠≤≥≈≡∈∉∪∩⊂⊃∧∨¬∀∃→←↔⇒⇐⇔αβγδεζηθικλμνξοπρστυφχψωΓΔΘΛΞΠΣΦΨΩθλμπσφ−–—⁄")
ASCII_MATH_CHARS = set("+-*/=^_()[]{}<>|~\\")

#: Grouping fences inflate symbol density without proving mathematics:
#: "(A) 1", "[1]" and "(8 x 2)" are marks debris, not equations.
_FENCE_CHARS = set("()[]{}")

#: Unicode dashes are minus signs in math ("(–2, 0)") but weak evidence on
#: their own — prose ranges ("pages 3–5") must not pass as equations.
_WEAK_DASHES = set("−–—")


@dataclass(frozen=True)
class MathCandidate:
    text: str
    symbol_density: float
    has_operators: bool
    has_digits: bool
    has_latin_vars: bool
    score: float


def _symbol_density(text: str) -> float:
    if not text:
        return 0.0
    hits = sum(
        1 for ch in text
        if ch in MATH_SYMBOLS or (ch in ASCII_MATH_CHARS and ch not in _FENCE_CHARS)
    )
    return hits / max(1, len(text))


_LATIN_VAR = re.compile(r"[a-zA-Z]")

#: URL/download-stamp traces: footers are never equations.
_URL_RE = re.compile(r"://|www\.|https?|ftp\.")
#: Bare numbers in brackets or alone: "[1]", "[1] [1]", "(6,6)", "36", "3.5".
_BARE_NUMBER_MARKS_RE = re.compile(r"^[\(\[\{]?\s*[\d.,\s]+[\)\]\}]?(\s+[\(\[\{]?\s*[\d.,\s]+[\)\]\}]?)*$")
#: Option letter glued to a bare number: "(A) 1", "(B) 10". Signed numbers
#: ("(D) − 7") are real math and are NOT matched (sign excluded on purpose).
_OPTION_BARE_NUMBER_RE = re.compile(r"^\([A-Za-z]\)\s*[\d.]+\s*$")
#: Marks multipliers: "(8 × 2)", "(8 x 2)" (matched whitespace-free).
_MARKS_MULT_RE = re.compile(r"^\(\d+[×xX*]\d+\)$")
#: Single hyphenated label: "Part-C" (prose hyphen, no digits, no structure).
_HYPHENATED_WORD_RE = re.compile(r"^[A-Za-z]+\-[A-Za-z]+$")
#: Natural-language words (3+ letters); 2+ with only weak math is prose.
_PROSE_WORD_RE = re.compile(r"[A-Za-z]{3,}")
#: Multi-letter runs for the density gate: prose packs letters into words
#: ("Expectedwinningamount"), genuine equations use single-letter variables.
_PROSE_RUN_RE = re.compile(r"[A-Za-z]{2,}")
#: Option labels "(A)", "(d)" and bare "a)", "A.": a row of several is an
#: options list, not one equation ("(C) 1/4 (D) 1", "1/2 ... a) b) c) d)").
#: A label glued to a function or variable ("f(x)", "E(X)", "tan(x)") is
#: grouping, not a label — require a non-letter, non-paren boundary left.
_OPTION_LABEL_RE = re.compile(r"(?<![A-Za-z0-9(.])[(]?[A-Za-z][).](?![A-Za-z0-9])")
#: Bare option-answer keys without parens ("A1B2C0D-1", "A17B18C19D110"):
#: alternating capital-led letter+number runs with no operators.
_OPTION_KEY_RE = re.compile(r"^(?:[A-Z]\d+\s*)+-?\d*\s*$")
#: Capital letter glued to digits ("D2sin-1x"): option debris, never a
#: leading variable (variables are lowercase; "Z = ..." has a space).
_OPTION_LEAD_RE = re.compile(r"^[A-Z]\d")
#: Sentence markers: instruction verbs, conjunctions and prose theorems
#: never occur inside a genuine equation line ("Find the...",
#: "E(X)=11/5 and V(X)=...", "1/2 Theorem 49 log(2+√3)").
#: Whole-word match only, so "forx", "Theorem49", "o r" never trip it.
_SENTENCE_WORD_RE = re.compile(
    r"\b(and|or|if|then|with|when|where|given|find|shows?|evaluate|equal|is"
    r"|theorem|proof|lemma|corollary)\b",
    re.IGNORECASE,
)

#: Fill-in blanks ("tan⁻¹(...) = _______. 6") mark an incomplete stem,
#: never an equation.
_BLANK_RE = re.compile(r"_{3,}")

#: Leading section tags ("Section-D 1 ...", "Part-C"): metadata, scored
#: on the remainder like option labels.
_LEADING_SECTION_RE = re.compile(
    r"^(?P<tag>Section|Part)\s*-\s*[A-Za-z]?\s*(?P<rest>.+)$", re.IGNORECASE
)


def strip_leading_section_tag(text: str) -> tuple[str, str | None]:
    """Split one leading "Section-X"/"Part-X" tag off; (None when absent)."""
    m = _LEADING_SECTION_RE.match(text.strip())
    if not m or len(m.group("rest")) < 2:
        return text, None
    return m.group("rest"), m.group("tag")

#: Bare number juxtapositions ("–1 2", two detached script fragments) are
#: not equations: minting them as OMML fuses them into one value ("-12").
#: Genuine multi-number lines always show structure — a relation, a
#: fraction bar, a script, a math symbol, or a function name.
_STRUCTURE_RE = re.compile(
    r"[=/^_<>≤≥≠≈∫∑∏√∞∂∈∉∪∩±×÷→]|sin|cos|tan|log|ln|lim|exp|sec|sqrt"
)

#: A single leading option label ("(D) −7", "A) x = 1", "(a) log y"): the
#: label is metadata, never equation content. Stripped before scoring so
#: the math core promotes without the letter.
_LEADING_OPTION_LABEL_RE = re.compile(r"^(?P<label>\([A-Za-z]\)|[A-Za-z][.)])\s+(?P<rest>.+)$")


def strip_leading_option_label(text: str) -> tuple[str, str | None]:
    """Split one leading "(X)"/"X)"/"X." label off; (None when absent)."""
    m = _LEADING_OPTION_LABEL_RE.match(text.strip())
    if not m or len(m.group("rest")) < 1:
        return text, None
    return m.group("rest"), m.group("label")


#: Bare label+number ("D223", option "(D) 223" with parens/spaces lost).
#: Single-digit "y2" stays allowed — it may be a genuine variable.
_BARE_LABEL_NUMBER_RE = re.compile(r"^[A-Za-z]\d{2,}$")

#: Max share of characters belonging to multi-letter runs. Above this the
#: line is prose carrying math ("Expected winning amount = Rs. 5.5"), not
#: mathematics carrying words. Genuine function CALLS ("sqrt(x)", "sin(x)")
#: are mathematics, not prose, so they are excluded first; a bare "sin" in
#: "Theprincipalvalueofsin" stays prose. "x^2 + 3x + 2 = 0" scores 0.
_FUNCTION_CALL_RE = re.compile(r"(sin|cos|tan|log|ln|lim|exp|sec|sqrt)\s*\(")
_PROSE_RATIO_LIMIT = 0.35
#: Strong math evidence that survives inside prose: relations, slashes,
#: scripts and named functions.
_STRONG_MATH_RE = re.compile(r"[=/^_]|sin|cos|tan|log|sqrt|lim|exp")


def score_text(text: str) -> MathCandidate:
    """Score a text span for mathematical content. Pure function."""
    stripped = text.strip()
    density = _symbol_density(stripped)
    has_operators = any(ch in stripped for ch in "+-*/=^_") or any(ch in MATH_SYMBOLS for ch in stripped)
    has_digits = any(ch.isdigit() for ch in stripped)
    has_latin_vars = bool(_LATIN_VAR.search(stripped))
    # Weighted evidence fusion (starting point; calibrate on golden corpus).
    score = min(
        1.0,
        density * 2.2
        + (0.25 if has_operators and has_digits else 0.0)
        + (0.15 if has_operators and has_latin_vars else 0.0)
        + (0.10 if ("=" in stripped and (has_digits or has_latin_vars)) else 0.0),
    )
    return MathCandidate(
        text=stripped,
        symbol_density=round(density, 3),
        has_operators=has_operators,
        has_digits=has_digits,
        has_latin_vars=has_latin_vars,
        score=round(score, 3),
    )


def is_equation_line(text: str, *, threshold: float = 0.45) -> bool:
    """Block-level gate: is this line predominantly mathematics?"""
    stripped = text.strip()
    # Leading option labels and section tags are metadata: score the math
    # core instead ("(D) −7" → "−7", "Section-D 1 ..." → "1 ...").
    stripped, _ = strip_leading_option_label(stripped)
    stripped, _ = strip_leading_section_tag(stripped)
    if len(stripped) < 2:
        return False
    # Compatibility glyphs (math-italic 𝑥, bold 𝟐) fold to ASCII so the
    # prose/option guards see letters, not opaque symbols. NFKC is the
    # identity on plain ASCII, so ASCII behavior is unchanged.
    folded = unicodedata.normalize("NFKC", stripped)
    low = folded.lower()
    # Prose guard: long natural-language runs are not equations even with symbols.
    words = folded.split()
    if len(words) > 12:
        return False
    # Footers, download stamps and URLs are never equations.
    if _URL_RE.search(low):
        return False
    if any(len(tok) > 25 for tok in words):
        return False
    # Fill-in blanks mark an incomplete stem, never an equation.
    if _BLANK_RE.search(folded):
        return False
    # Marks debris and option-label fragments: bare numbers in brackets
    # ("[1]", "[1] [1]", "36"), option letter + bare number ("(A) 1"),
    # marks multipliers ("(8 × 2)"), hyphenated labels ("Part-C").
    if _BARE_NUMBER_MARKS_RE.match(folded):
        return False
    if _OPTION_BARE_NUMBER_RE.match(folded):
        return False
    if _MARKS_MULT_RE.match(re.sub(r"\s+", "", folded)):
        return False
    if _HYPHENATED_WORD_RE.match(folded):
        return False
    # Prose carrying only a weak hyphen/dash ("Case Study -2") is not an
    # equation. Genuine prose+math shows =, /, scripts, functions or a
    # non-dash math symbol.
    if len(_PROSE_WORD_RE.findall(folded)) >= 2 and not (
        _STRONG_MATH_RE.search(low)
        or any(ch in MATH_SYMBOLS and ch not in _WEAK_DASHES for ch in folded)
    ):
        return False
    # Math-density gate: prose and option debris must never become OMML.
    # A wrong editable equation is worse than text — inline math inside a
    # stem stays a paragraph with a mathHint; only math-dominant lines
    # promote. A single leading label was stripped above, so any label
    # here is either one of several or debris.
    labels = list(_OPTION_LABEL_RE.finditer(folded))
    if len(labels) >= 2:
        return False
    if len(labels) == 1 and labels[0].start() != 0:
        return False
    if _OPTION_KEY_RE.match(folded) or _OPTION_LEAD_RE.match(folded):
        return False
    if _BARE_LABEL_NUMBER_RE.match(folded):
        return False
    # Sentences are not equations, however much math they carry.
    if _SENTENCE_WORD_RE.search(folded):
        return False
    # Bare number runs are not equations either.
    if sum(1 for ch in folded if ch.isdigit()) >= 2 and not _STRUCTURE_RE.search(low):
        return False
    prose_chars = sum(len(m) for m in _PROSE_RUN_RE.findall(_FUNCTION_CALL_RE.sub("", folded)))
    if prose_chars / max(1, len(folded)) > _PROSE_RATIO_LIMIT:
        return False
    return score_text(folded).score >= threshold
