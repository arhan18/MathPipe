"""Stage 4 — native text extraction with geometry + style evidence (§7)."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import pdfplumber


@dataclass(frozen=True)
class Word:
    text: str
    x0: float
    top: float
    x1: float
    bottom: float
    fontname: str
    size: float


@dataclass(frozen=True)
class PageText:
    page_number: int
    width: float
    height: float
    words: list[Word]


#: Adobe Symbol custom encoding surfaces through pdfplumber as private-use
#: codepoints U+F000+code (the subset embeds no ToUnicode map): U+F0F2 is
#: the integral (code 0xF2), U+F0A2 the prime (0xA2), U+F03E ">" (0x3E).
#: Map per the Adobe Symbol encoding so downstream stages see real Unicode.
#: Codes with uncertain assignments are omitted — leftovers are replaced
#: with U+FFFD at the DOCX boundary, never emitted as font-dependent PUA.
_SYMBOL_CODES: dict[int, str] = {
    0x20: " ", 0x21: "!", 0x22: "∀", 0x23: "#", 0x24: "∃",
    0x25: "%", 0x26: "&", 0x27: "∋", 0x28: "(", 0x29: ")",
    0x2A: "*", 0x2B: "+", 0x2C: ",", 0x2D: "−", 0x2E: ".",
    0x2F: "/",
    0x30: "0", 0x31: "1", 0x32: "2", 0x33: "3", 0x34: "4",
    0x35: "5", 0x36: "6", 0x37: "7", 0x38: "8", 0x39: "9",
    0x3A: ":", 0x3B: ";", 0x3C: "<", 0x3D: "=", 0x3E: ">",
    0x3F: "?", 0x40: "≅",
    0x41: "Α", 0x42: "Β", 0x43: "Χ", 0x44: "Δ", 0x45: "Ε",
    0x46: "Φ", 0x47: "Γ", 0x48: "Η", 0x49: "Ι", 0x4A: "ϑ",
    0x4B: "Κ", 0x4C: "Λ", 0x4D: "Μ", 0x4E: "Ν", 0x4F: "Ο",
    0x50: "Π", 0x51: "Θ", 0x52: "Ρ", 0x53: "Σ", 0x54: "Τ",
    0x55: "Υ", 0x56: "ς", 0x57: "Ω", 0x58: "Ξ", 0x59: "Ψ",
    0x5A: "Ζ",
    0x5B: "[", 0x5C: "∴", 0x5D: "]", 0x5E: "⊥", 0x5F: "_",
    0x61: "α", 0x62: "β", 0x63: "χ", 0x64: "δ", 0x65: "ε",
    0x66: "φ", 0x67: "γ", 0x68: "η", 0x69: "ι", 0x6A: "ϕ",
    0x6B: "κ", 0x6C: "λ", 0x6D: "μ", 0x6E: "ν", 0x6F: "ο",
    0x70: "π", 0x71: "θ", 0x72: "ρ", 0x73: "σ", 0x74: "τ",
    0x75: "υ", 0x76: "ϖ", 0x77: "ω", 0x78: "ξ", 0x79: "ψ",
    0x7A: "ζ",
    0x7B: "{", 0x7C: "|", 0x7D: "}", 0x7E: "~",
    0xA1: "ϒ", 0xA2: "′", 0xA3: "≤", 0xA4: "⁄", 0xA5: "∞",
    0xA6: "ƒ", 0xA7: "♣", 0xA8: "♦", 0xA9: "♥", 0xAA: "♠",
    0xAB: "↔", 0xAC: "←", 0xAD: "↑", 0xAE: "→", 0xAF: "↓",
    0xB0: "°", 0xB1: "±", 0xB2: "″", 0xB3: "≥", 0xB4: "×",
    0xB5: "∝", 0xB6: "∂", 0xB7: "•", 0xB8: "÷", 0xB9: "≠",
    0xBA: "≡", 0xBB: "≈", 0xBC: "…", 0xBF: "↵",
    0xC0: "ℵ", 0xC1: "ℑ", 0xC2: "ℜ", 0xC3: "℘", 0xC4: "⊗",
    0xC5: "⊕", 0xC6: "∅", 0xC7: "∩", 0xC8: "∪", 0xC9: "⊃",
    0xCA: "⊇", 0xCB: "⊄", 0xCC: "⊂", 0xCD: "⊆", 0xCE: "∈",
    0xCF: "∉",
    0xD0: "∠", 0xD1: "∇", 0xD2: "®", 0xD3: "©", 0xD4: "™",
    0xD5: "∏", 0xD6: "√", 0xD7: "⋅", 0xD8: "¬", 0xD9: "∧",
    0xDA: "∨", 0xDB: "⇔", 0xDC: "⇐", 0xDD: "⇑", 0xDE: "⇒",
    0xDF: "⇓",
    0xE0: "◊", 0xE1: "⟨", 0xE5: "∑", 0xF2: "∫",
}

#: PUA codepoint for an Adobe Symbol char code (pdfplumber's fallback).
_SYMBOL_PUA_MAP: dict[str, str] = {
    chr(0xF000 + code): glyph for code, glyph in _SYMBOL_CODES.items()
}

_SYMBOL_FONT_RE = re.compile(r"symbol", re.IGNORECASE)
_MATH_ALPHA_DUP_RE = re.compile(r"([\U0001D400-\U0001D7FF])\1")

#: Custom Type1 / legacy symbol encodings used in Indian exam PDFs (e.g.
#: Wolfram Mathematica MMa* fonts, RupeeForadian, EuclidSymbol) whose
#: ToUnicode/encoding assigns math glyphs to ordinary ASCII characters.
#: Order matters: MMaVariableA and MMaVariableB must match before MMaVariable.
_CUSTOM_FONT_MAPS: tuple[tuple[str, dict[str, str]], ...] = (
    ("mmavariablea", {
        "^": "(", "h": ")",
        "`": "(", "j": ")",
        "a": "(", "k": ")",
        "b": "(", "l": ")",
        "c": "(", "m": ")",
        "d": "(", "n": ")",
        "$": "{", "*": "{", ",": "}",
    }),
    ("mmavariableb", {
        "6": "[", ";": "[", "<": "[", "=": "(", ">": "[", "?": "[",
        "@": "]", "E": "]", "F": "]", "G": ")", "H": "]",
    }),
    ("mmavariable", {
        "#": "∫",
        "R": "⎡", "S": "⎢", "T": "⎣",
        "V": "⎤", "W": "⎥", "X": "⎦",
        "Z": "⎧", "[": "⎨", "\\": "⎩", "]": "⎪",
    }),
    ("mmabinary", {
        "#": "×", "$": "·", "j": "∩", "k": "∪", ",": "∪",
        "d": "∈", "!": "≠", "|": ":",
    }),
    ("mmarelation", {
        "#": "≤", "$": "≥", "1": "⊂", "2": "⊃",
    }),
    ("mmaarrow", {
        '"': "→",
    }),
    ("mmanegate", {
        "!": "≠",
    }),
    ("mmaextra", {
        "1": "<", "2": ">",
    }),
    ("mmaetc", {
        "6": "∀", "v": "\u20d7", "c": "°", "l": "′", "t": "\u0302", "3": "∞",
    }),
    ("rupeeforadian", {
        "`": "₹",
    }),
    ("euclidsymbol", {
        "p": "π", "l": "λ",
    }),
)


def map_symbol_pua(text: str, fontname: str) -> str:
    """Remap Symbol-font PUA and legacy custom-font glyphs to real Unicode.

    Only applies when the word's font is a recognized symbol/custom face:
    PUA values are only meaningful under Adobe Symbol, and custom MMa* /
    RupeeForadian / EuclidSymbol ASCII substitutions are only valid under
    their respective encodings. Other fonts keep their bytes unchanged.
    """
    if not text or not fontname:
        return text
    fn_low = fontname.lower()
    if _SYMBOL_FONT_RE.search(fontname) and any(ch in _SYMBOL_PUA_MAP for ch in text):
        text = "".join(_SYMBOL_PUA_MAP.get(ch, ch) for ch in text)
    for key, table in _CUSTOM_FONT_MAPS:
        if key in fn_low:
            if any(ch in table for ch in text):
                text = "".join(table.get(ch, ch) for ch in text)
            break
    return text


#: Degree marks whose font lacks a ToUnicode entry extract as a small
#: raised "0"/"o" word ("60°" → "60" + "0"); SQP's "67°" arrives as "67"+"𝑜".
#: A genuine zero is full-size, so the size ratio discriminates.
_DEGREE_MARK_TEXTS = frozenset({"0", "o", "O", "°"})

#: Max glyph-size ratio (mark / digits) and max x-gap (fraction of the
#: digit size) for degree gluing. The observed mark sits touching the
#: digits (gap ≈ 0) at 0.63× size; real word gaps are far wider.
_DEGREE_SIZE_RATIO = 0.75
_DEGREE_GAP_FACTOR = 0.35


def _is_degree_mark(cur: Word, prev: Word) -> bool:
    folded = unicodedata.normalize("NFKC", cur.text.strip())
    if folded not in _DEGREE_MARK_TEXTS:
        return False
    if not prev.text or prev.text[-1] not in "0123456789":
        return False
    if cur.text.strip() == "°" or folded == "°":
        return True
    if not prev.size or cur.size > _DEGREE_SIZE_RATIO * prev.size:
        return False
    if cur.x0 - prev.x1 > _DEGREE_GAP_FACTOR * prev.size:
        return False
    return True


def _repair_words(words: list[Word]) -> list[Word]:
    """Font-aware PUA remap, doubled-glyph dedup, and degree-mark gluing. Pure."""
    repaired = [
        Word(
            text=_MATH_ALPHA_DUP_RE.sub(r"\1", map_symbol_pua(w.text, w.fontname)),
            x0=w.x0, top=w.top, x1=w.x1, bottom=w.bottom,
            fontname=w.fontname, size=w.size,
        )
        for w in words
    ]
    out: list[Word] = []
    for w in repaired:
        if out and _is_degree_mark(w, out[-1]):
            prev = out[-1]
            out[-1] = Word(
                text=prev.text + "°",
                x0=prev.x0, top=min(prev.top, w.top),
                x1=max(prev.x1, w.x1), bottom=max(prev.bottom, w.bottom),
                fontname=prev.fontname, size=prev.size,
            )
        else:
            out.append(w)
    return out


#: --- Running furniture suppression (headers/footers/folios) ---
#:
#: Repeated running matter (advert footers, folio codes such as "T26 511")
#: sits at a fixed vertical position in the bottom margin on every page,
#: while body lines move. A line prefix that recurs verbatim on >=3 pages
#: at a consistent y inside the bottom band is furniture, not content.
#: Lone numeric folio lines ("473 425") and URL footers never repeat, so
#: they are caught per page instead. Top-band repetition is deliberately
#: NOT stripped: section titles re-appear at identical y across chapters
#: ("I. MCQ (2 ...") and must be kept.
_FURNITURE_MIN_PAGES = 3
_FURNITURE_Y_TOL = 10.0
_FURNITURE_BOTTOM_FRAC = 0.80
_FURNITURE_PREFIX_TOKENS = 3
_FURNITURE_LINE_TOL = 3.5
_FURNITURE_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
_FURNITURE_NUMERIC_RE = re.compile(r"^[\d\s/.,\-–—:;]+$")
_FURNITURE_GAP_PT = 60.0

#: --- Chunk-independent furniture shapes (single-page backstop) ---
#:
#: The cross-page prefix rule needs >=3 pages in one extraction call, so
#: chunked/single-page extraction has no repetition signal, and short
#: markers ("Turn Over", 2 tokens) never meet the 3-token prefix minimum.
#: These shapes identify the same furniture from one line alone, bottom
#: band only. Every shape requires the line to be code-like throughout:
#: body lines always carry a real word and can never match — verified
#: across ICSE/MathSample/QueBank (matrix rows "0 0 1", binomial "9 9",
#: integral limits "0", option lines "(A) 1 (B) 2" are all kept).
#:
#: Continuation markers: exam-paper furniture by convention ("Turn Over",
#: "P.T.O.", "Continued"). Exact full-line match only — prose merely
#: containing the words ("Turn over the page to continue") never matches.
_FURNITURE_CONT_RE = re.compile(
    r"^(?:please\s+turn\s+over|turn\s*over|turnover"
    r"|p\.?\s*t\.?\s*o\.?"
    r"|continued?(?:\s+on\s+next\s+page)?|contd\.?"
    r"|see\s+next\s+page|overleaf)$"
)
#: Trailing continuation marker after a folio code
#: ("T26 511 I 3 Turn Over"): stripped before the press-code match.
_FURNITURE_CONT_SUFFIX_RE = re.compile(
    r"\s+(?:please\s+turn\s+over|turn\s*over|turnover"
    r"|p\.?\s*t\.?\s*o\.?"
    r"|continued?(?:\s+on\s+next\s+page)?|contd\.?"
    r"|see\s+next\s+page|overleaf)$"
)
#: Press folio codes ("T26 511 I 3"): first token mixes letters+digits
#: (the press signature), the rest are numbers/roman numerals. Pure
#: numeric rows ("0 0 1") and label rows ("(A) 1 (B) 2") cannot match:
#: their first token has no letter+digit mix.
_FURNITURE_PRESS_FIRST_RE = re.compile(r"^(?=.*[a-z])(?=.*\d)[a-z0-9]{2,8}$")
_FURNITURE_PRESS_REST_RE = re.compile(r"^(\d{1,5}|[ivx]{1,5}|[a-z0-9]*\d[a-z0-9]*)$")
#: Lone folio digits at the extreme margin ("9", "9/13"): single short
#: numeric tokens never sit this low in body text (verified: deepest body
#: single numerics are integral limits at frac <= 0.91), and short pairs
#: ("9 13") need an even deeper gate (matrix debris reaches 0.93).
_FURNITURE_LONE_FOLIO_RE = re.compile(r"^\d{1,3}([/:\-–—]\d{1,3})?$")
_FURNITURE_LONE_FRAC = 0.93
_FURNITURE_PAIR_FRAC = 0.95
#: Exam papers print "Page N of M" in the bottom margin. The page number
#: sits at token #2, so the verbatim 3-token prefix rule can never match
#: it ("Page 1 of" vs "Page 2 of" never repeat) — the repetition signal
#: is destroyed by the varying number. Two rules cover it: the digit
#: masked fingerprint below (cross-page) and these shapes (single page).
_FURNITURE_FOLIO_RE = re.compile(
    r"^(?:page|p\.)?\s*\d{1,4}\s*(?:of|/)\s*\d{1,4}\.?$", re.IGNORECASE
)
#: The same folio sharing a line with the wrapped tail of a footer note
#: ("2025-26. Page 1 of 10"): a short numeric/punctuation-only fragment
#: in front of the folio. Body prose ("see page 3 of 10 for details")
#: has real words and never matches either shape.
_FURNITURE_FOLIO_TAIL_RE = re.compile(
    r"^[\d.,:\-–—/]{1,16}\s+(?:page|p\.)?\s*\d{1,4}\s*(?:of|/)\s*\d{1,4}\.?$",
    re.IGNORECASE,
)
#: Digit runs masked to "#" for the cross-page repetition fingerprint.
_FURNITURE_DIGIT_MASK_RE = re.compile(r"\d+")


def _furniture_lines(words: list[Word]) -> list[list[Word]]:
    """Cluster words into visual lines (same tolerance as block grouping)."""
    ordered = sorted(words, key=lambda w: (w.top, w.x0))
    lines: list[list[Word]] = []
    cur: list[Word] = []
    cur_top = 0.0
    for w in ordered:
        if cur and abs(w.top - cur_top) > _FURNITURE_LINE_TOL:
            lines.append(cur)
            cur = []
        if not cur:
            cur_top = w.top
        else:
            cur_top = (cur_top + w.top) / 2
        cur.append(w)
    if cur:
        lines.append(cur)
    return lines


def _line_text(line: list[Word]) -> str:
    return " ".join(w.text for w in sorted(line, key=lambda w: w.x0)).strip()


def _max_gap(line: list[Word]) -> float:
    ordered = sorted(line, key=lambda w: w.x0)
    return max(
        (cur.x0 - prev.x1 for prev, cur in zip(ordered, ordered[1:])),
        default=0.0,
    )


def is_furniture_line(line: list[Word], page_height: float) -> bool:
    """Per-page furniture predicate: URL footers and numeric folio lines.

    Only applies inside the bottom margin band, where body lines always
    carry letters. Numeric-only lines need a folio signature (a long
    number or a huge inter-word gap, e.g. facing-page "473 425") so
    single-digit math debris ("1", "10") is never touched here.
    Chunk-independent shapes (press folio codes such as "T26 511 I 3",
    continuation markers such as "Turn Over", lone extreme-margin folio
    digits) are caught here too, so single-page/chunked extraction — with
    no cross-page repetition signal — strips the same furniture.
    """
    if not line or not page_height:
        return False
    y = min(w.top for w in line)
    if y <= _FURNITURE_BOTTOM_FRAC * page_height:
        return False
    text = _line_text(line)
    if not text:
        return False
    if _FURNITURE_URL_RE.search(text):
        return True
    # Exam-paper folios: "Page 1 of 10", "1 of 10", and the same folio
    # sharing a line with a wrapped footer-note tail ("2025-26. Page 1 of
    # 10"). Body prose that merely mentions a page number has real words
    # in front of the shape and never matches.
    if _FURNITURE_FOLIO_RE.match(text) or _FURNITURE_FOLIO_TAIL_RE.match(text):
        return True
    low = re.sub(r"[.…\s]+$", "", text.strip().lower())
    if not low:
        return False
    # Exact continuation marker ("Turn Over", "P.T.O.", "Continued").
    if len(low.split()) <= 4 and _FURNITURE_CONT_RE.match(low):
        return True
    # Press folio code, optionally trailed by a continuation marker
    # ("T26 511 I 3", "T26 511 I 3 Turn Over").
    core = _FURNITURE_CONT_SUFFIX_RE.sub("", low).strip()
    core_toks = core.split()
    if (
        2 <= len(core_toks) <= 6
        and _FURNITURE_PRESS_FIRST_RE.match(core_toks[0])
        and all(_FURNITURE_PRESS_REST_RE.match(t) for t in core_toks[1:])
    ):
        return True
    # Lone folio digits at the extreme margin ("9", "9/13"): body
    # numerics never sit this low alone (see _FURNITURE_LONE_FRAC note).
    toks = text.split()
    if (
        len(toks) == 1
        and _FURNITURE_LONE_FOLIO_RE.match(toks[0])
        and y >= _FURNITURE_LONE_FRAC * page_height
    ):
        return True
    if (
        len(toks) == 2
        and all(re.fullmatch(r"\d{1,2}", t) for t in toks)
        and y >= _FURNITURE_PAIR_FRAC * page_height
    ):
        return True
    if (
        len(toks) <= 4
        and _FURNITURE_NUMERIC_RE.match(text)
        and (
            any(sum(c.isdigit() for c in t) >= 3 for t in toks)
            or sum(c.isdigit() for c in text) >= 5
            or _max_gap(line) > _FURNITURE_GAP_PT
        )
    ):
        return True
    return False


#: --- Stacked-fraction protection (silent-drop guard) ---
#:
#: Vertically stacked fractions ("1" over "81" for 1/81, no "/" bar in
#: extraction) split into numeric-only lines that mimic folio furniture:
#: bottom-band + numeric-only + huge inter-token gaps ("1 1 1" gap 97pt,
#: "81 100 90" with a 3-digit token). The folio rule would eat them,
#: silently dropping option values (SQP Q18, big2 Q2 c/d). A stacked
#: fraction always sits within ~20pt of its option-label row ("(A) (B)
#: (C) (D)") with horizontal overlap; isolated folio digits ("473 425")
#: never do. Lines meeting this geometry are protected from furniture
#: stripping at both call sites (extraction + block assembly).
_OPTION_LABEL_INLINE_RE = re.compile(r"\([A-Da-d]\)")
_FRACTION_STACK_DY_PT = 20.0


def _line_has_option_label(line: list[Word]) -> bool:
    return bool(_OPTION_LABEL_INLINE_RE.search(" ".join(w.text for w in line)))


def fraction_stack_protected(lines: list[list[Word]]) -> set[int]:
    """Indices of numeric-only lines that are stacked-fraction parts.

    A line qualifies when it is short numeric-only (<=4 tokens, folio-like)
    and sits within _FRACTION_STACK_DY_PT of an option-label row with
    horizontal overlap against the row's union band (column gutters split
    option rows into single-token lines, so pairwise overlap misses offset
    fraction columns). Pure helper — never raises.
    """
    protected: set[int] = set()
    if not lines:
        return protected
    try:
        spans = []
        tops = []
        is_numeric = []
        has_label = []
        for line in lines:
            try:
                txt = _line_text(line)
            except Exception:
                txt = ""
            toks = txt.split()
            spans.append((
                min((w.x0 for w in line), default=0.0),
                max((w.x1 for w in line), default=0.0),
            ))
            try:
                tops.append(min(w.top for w in line))
            except Exception:
                tops.append(0.0)
            is_numeric.append(
                bool(toks)
                and len(toks) <= 4
                and bool(_FURNITURE_NUMERIC_RE.match(txt))
            )
            has_label.append(_line_has_option_label(line))
        for i, numeric in enumerate(is_numeric):
            if not numeric:
                continue
            x0, x1 = spans[i]
            # Union span of NEARBY option-label lines: column gutters split
            # one option row into single-token lines ("(A)", "(B)", ...) that
            # never pairwise-overlap their offset fraction columns ("100" at
            # x=231 vs "(B)" at x=205-221), so pairwise overlap misses them
            # and the folio rule eats 3-digit denominators (SQP Q18 "100").
            # The union band overlaps any column of the same option row while
            # isolated folio digits (no label row within DY) stay unprotected.
            lo: float | None = None
            hi: float | None = None
            for j, labelled in enumerate(has_label):
                if not labelled or i == j:
                    continue
                try:
                    if abs(tops[i] - tops[j]) > _FRACTION_STACK_DY_PT:
                        continue
                except Exception:
                    continue
                jx0, jx1 = spans[j]
                lo = jx0 if lo is None else min(lo, jx0)
                hi = jx1 if hi is None else max(hi, jx1)
            if lo is None or hi is None:
                continue
            if x1 < lo or hi < x0:
                continue
            protected.add(i)
    except Exception:
        return set()
    return protected


def _strip_furniture(pages: list[PageText]) -> list[PageText]:
    """Drop running-furniture words before block assembly. Pure.

    Two layers: (1) bottom-band line prefixes repeated verbatim on >=3
    pages at a consistent y (advert footers, folio codes with varying
    page numbers — the prefix stays identical); (2) the per-page
    :func:`is_furniture_line` predicate (URL footers, numeric folios,
    press folio codes, continuation markers, lone extreme-margin folio
    digits) — the chunk-independent backstop for small extractions.
    """
    if not pages:
        return pages
    lines_by_page = [_furniture_lines(p.words) for p in pages]
    # Prefix -> [(page_index, y)] for bottom-band lines with enough tokens.
    prefix_hits: dict[str, list[tuple[int, float]]] = {}
    for i, page in enumerate(pages):
        for line in lines_by_page[i]:
            toks = _line_text(line).split()
            if len(toks) < _FURNITURE_PREFIX_TOKENS:
                continue
            y = min(w.top for w in line)
            if y <= _FURNITURE_BOTTOM_FRAC * page.height:
                continue
            prefix_hits.setdefault(" ".join(toks[:_FURNITURE_PREFIX_TOKENS]), []).append((i, y))
    drop: set[int] = set()
    for key, hits in prefix_hits.items():
        if len({i for i, _ in hits}) < _FURNITURE_MIN_PAGES:
            continue
        ys = [y for _, y in hits]
        if max(ys) - min(ys) > _FURNITURE_Y_TOL:
            continue
        for i, _ in hits:
            try:
                shielded = fraction_stack_protected(lines_by_page[i])
            except Exception:
                shielded = set()
            for idx, line in enumerate(lines_by_page[i]):
                if idx in shielded:
                    continue
                if " ".join(_line_text(line).split()[:_FURNITURE_PREFIX_TOKENS]) == key:
                    drop.update(id(w) for w in line)
    for i, page in enumerate(pages):
        try:
            shielded = fraction_stack_protected(lines_by_page[i])
        except Exception:
            shielded = set()
        for idx, line in enumerate(lines_by_page[i]):
            if idx in shielded:
                continue
            if is_furniture_line(line, page.height):
                drop.update(id(w) for w in line)
    # (3) Digit-masked fingerprints. The page number sits INSIDE the line
    #     ("Page 1 of 10"), so the verbatim 3-token prefix rule above can
    #     never match it: "Page 1 of" and "Page 2 of" never repeat. Masking
    #     every digit run restores the repetition signal ("page # of #").
    fp_hits: dict[str, list[tuple[int, float]]] = {}
    for i, page in enumerate(pages):
        for line in lines_by_page[i]:
            toks = _line_text(line).split()
            if len(toks) < _FURNITURE_PREFIX_TOKENS:
                continue
            y = min(w.top for w in line)
            if y <= _FURNITURE_BOTTOM_FRAC * page.height:
                continue
            fp = _FURNITURE_DIGIT_MASK_RE.sub("#", " ".join(toks).lower())
            if "#" not in fp:
                continue
            fp_hits.setdefault(fp, []).append((i, y))
    for fp, hits in fp_hits.items():
        if len({i for i, _ in hits}) < _FURNITURE_MIN_PAGES:
            continue
        ys = [y for _, y in hits]
        if max(ys) - min(ys) > _FURNITURE_Y_TOL:
            continue
        for i, _ in hits:
            try:
                shielded = fraction_stack_protected(lines_by_page[i])
            except Exception:
                shielded = set()
            for idx, line in enumerate(lines_by_page[i]):
                if idx in shielded:
                    continue
                toks = _line_text(line).split()
                if len(toks) < _FURNITURE_PREFIX_TOKENS:
                    continue
                if _FURNITURE_DIGIT_MASK_RE.sub("#", " ".join(toks).lower()) == fp:
                    drop.update(id(w) for w in line)
    # (4) Bottom-most line. A folio printed high (books with a wide bottom
    #     margin) still leaves the bottom band, but nothing follows it on the
    #     page, so position-relative detection catches it.
    for i, page in enumerate(pages):
        lines = lines_by_page[i]
        if not lines:
            continue
        try:
            shielded = fraction_stack_protected(lines)
        except Exception:
            shielded = set()
        last_idx = max(range(len(lines)), key=lambda idx: min(w.top for w in lines[idx]))
        if last_idx in shielded:
            continue
        text = _line_text(lines[last_idx])
        if _FURNITURE_FOLIO_RE.match(text) or _FURNITURE_FOLIO_TAIL_RE.match(text):
            drop.update(id(w) for w in lines[last_idx])
    if not drop:
        return pages
    return [
        PageText(p.page_number, p.width, p.height, [w for w in p.words if id(w) not in drop])
        for p in pages
    ]
def extract_page_text(path: str) -> list[PageText]:
    with pdfplumber.open(path) as pdf:
        return _extract_from(pdf, list(range(1, len(pdf.pages) + 1)))


def extract_page_subset(path: str, page_numbers: list[int]) -> list[PageText]:
    """Extract only the requested pages (1-based). Bounds working memory."""
    with pdfplumber.open(path) as pdf:
        return _extract_from(pdf, [n for n in page_numbers if 1 <= n <= len(pdf.pages)])


def _keep_upright_char(obj: dict) -> bool:
    """Filter out rotated diagonal/vertical watermark characters.

    Checks baseline rotation via matrix ``b`` (|sin(theta)| > 0.1) rather
    than ``obj["upright"]`` alone, because tiny floating-point skew noise
    (e.g. -2.4e-7) marks genuine body math upright=False while some 30-deg
    watermarks carry upright=True. Also spares pure italic shear (b == 0).
    """
    if obj.get("object_type") != "char":
        return True
    mat = obj.get("matrix")
    if isinstance(mat, (tuple, list)) and len(mat) >= 4:
        a, b = float(mat[0]), float(mat[1])
        norm = max(1.0, (a * a + b * b) ** 0.5)
        if abs(b) > 0.1 * norm:
            return False
    return True


def _extract_from(pdf, page_numbers: list[int]) -> list[PageText]:
    pages: list[PageText] = []
    for i in page_numbers:
        page = pdf.pages[i - 1]
        try:
            filtered_page = page.filter(_keep_upright_char)
        except Exception:
            filtered_page = page
        try:
            raw = filtered_page.extract_words(extra_attrs=["fontname", "size"]) or []
        except Exception:
            try:
                raw = page.extract_words(extra_attrs=["fontname", "size"]) or []
            except Exception:
                raw = []
        words = [
            Word(
                text=str(w.get("text", "")),
                x0=float(w.get("x0", 0)),
                top=float(w.get("top", 0)),
                x1=float(w.get("x1", 0)),
                bottom=float(w.get("bottom", 0)),
                fontname=str(w.get("fontname", "")),
                size=float(w.get("size", 0) or 0),
            )
            for w in raw
            if str(w.get("text", "")).strip()
        ]
        pages.append(PageText(i, float(page.width), float(page.height), _repair_words(words)))
    return _strip_furniture(pages)
