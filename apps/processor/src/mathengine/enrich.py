"""Stage 8 — math enrichment (§11): paragraph lines that are predominantly
mathematics become equation blocks with normalized LaTeX, MathIR, confidence
and linked equation numbers. Uncertain regions keep their text and carry a
warning flag — never a guessed equation.
"""
from __future__ import annotations

import hashlib
import json

from .confidence import route_confidence
from .detect import (
    is_equation_line,
    score_text,
    strip_leading_option_label,
    strip_leading_section_tag,
)
from . import mathir as _mathir
from .gate import (
    _DOUBLED_LETTER_RE,
    _FRACTION_OPERAND_FUNC_RE,
    _GARBAGE_ARTIFACT_CHARS,
    _PROSE_SIDE_RE,
    _is_zero_denominator_text,
    _mathir_has_garbage,
    _mathir_has_zero_denominator,
    _strip_side_fences,
    has_math_kernel,
    is_promotable,
)
from .numbers import split_equation_number
from .recognize import DeterministicAsciiRecognizer
from .spans import split_math_spans

import re

#: Bound debris: values that are never limits ("b l", "^h", "(3", "1+x"
#: are integrand or layout litter — never a bound).
_BOUND_DEBRIS = frozenset({
    "", "^", "_", "h", "^h", "b", "l", "b l",
    "[", "]", "(", ")", "⎛", "⎜", "⎝", "⎞", "⎟", "⎠",
})

#: Stacked fractions as emitted by blocks.py pairing ("1/81", "π/4",
#: "(x-3)/(x-1)^{3}"): vertical adjacency + horizontal overlap, "/" is the
#: bar the PDF drew as untagged ink. Inline option fractions, display
#: fractions and trig fractions all arrive as slash tokens; debris
#: ("^h", "b l", bare folio "2/0", prose "and/or") must never become OMML.
_FRACTION_SLASH_RE = re.compile(r"(?P<num>[^\s]+?)\s*/\s*(?P<den>[^\s]+)")

#: Debris operands that must never form fractions (hat-soup, fence litter).
_FRACTION_OPERAND_DEBRIS = frozenset({
    "", "^", "_", "h", "^h", "b", "l", "b l",
    "[", "]", "(", ")", "{", "}", "⎛", "⎜", "⎝", "⎞", "⎟", "⎠",
    "R", "S", "V", "W", "T", "X", ">H",
    "+", "-", "*", "=", "/", "−", "–", "—",
})

#: Relation characters: an operand holding one is an equation/contour
#: ("|z|=3"), never a fraction side.
_FRACTION_OPERAND_RELATION_RE = re.compile(r"[=<>≤≥≠≈≡∈∉∪∩→←⇒⇐⇔|]")

#: Math evidence inside an operand (digits, operators, known symbols).
_FRACTION_OPERAND_MATH_RE = re.compile(r"[0-9∫∑∏√∞πθλμσφΔ∂∇^_(){}\[\]−–—+\-*/]")
#: _FRACTION_OPERAND_FUNC_RE moved to gate.py (single definition shared
#: with the promotion gate's garbage check); imported from there.

#: Bare integers on both sides ("1/81", "2/0"): option values vs folio
#: debris. Bare pairs need an option label or real math nearby, otherwise
#: folio "2 / 0" would mint fake OMML.
_FRACTION_BARE_INT_RE = re.compile(r"^[−–—-]?\d+$")
_FRACTION_BARE_CONTEXT_RE = re.compile(r"\([A-Da-d]\)|[∫∑∏√∞πθ^_=]")


def _valid_fraction_operand(s: str) -> bool:
    """True when a slash side is a genuine math operand, not debris."""
    import unicodedata as _ud
    try:
        _folded = _ud.normalize("NFKC", s or "")
    except Exception:
        _folded = s or ""
    t = _folded.strip().strip(".,;:!?\"'") .strip()
    # Strip one trailing folio-style punctuation layer (",", ".", ";").
    t = re.sub(r"[.,;:!?]+$", "", t).strip()
    if not t or t in _FRACTION_OPERAND_DEBRIS or t in _BOUND_DEBRIS:
        return False
    if len(re.sub(r"\s+", "", t)) > 24:
        return False
    if _FRACTION_OPERAND_RELATION_RE.search(t):
        return False
    # Bare debris runs ("^ h", "b l", "([", "]]").
    core = re.sub(r"[\(\)\[\]\{\}]+", "", t).strip()
    if not core or core in _FRACTION_OPERAND_DEBRIS or core in _BOUND_DEBRIS:
        return False
    if re.fullmatch(r"[\^_bhl\s]+", core):
        return False
    # Long letter runs are prose unless function-led or strongly
    # math-bearing ("sinθ−2)cosθ" vs "and"/"or" vs "case-study"). A lone
    # hyphen is prose punctuation, not math — require digits, operators
    # beyond "-"/"–"/"—", brackets or known symbols.
    if re.search(r"[A-Za-z]{3,}", t) and not (
        _FRACTION_OPERAND_FUNC_RE.match(t)
        or re.search(r"[0-9∫∑∏√∞πθλμσφΔ∂∇^+*/=(){}\[\]]", t)
    ):
        return False
    # Must carry math evidence (digit, symbol, function, or variable).
    if _FRACTION_OPERAND_MATH_RE.search(t):
        return True
    if _FRACTION_OPERAND_FUNC_RE.match(t):
        return True
    if re.fullmatch(r"[a-zA-Zπ](\^\{[^}]+\})?", t):
        if t[0] in ("b", "l", "h", "R", "S", "V", "W", "T", "X"):
            return False
        return True
    return False


def _extract_stacked_fractions(block_text: str) -> list[str]:
    """Return validated "num/den" strings in order, de-duplicated.

    Pure helper: finds slash tokens joined by blocks.py geometry, keeps only
    sides that pass debris/math gates. Bare-integer pairs need option/math
    context (folio "2/0" rejected, option "1/81" kept). Order is preserved
    (numerator was above the bar) — never swapped.
    """
    if not block_text or "/" not in block_text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for m in _FRACTION_SLASH_RE.finditer(block_text):
        num_raw = (m.group("num") or "").strip()
        den_raw = (m.group("den") or "").strip()
        # Trim trailing punctuation that glues to the denominator ("1/81,").
        den_raw = re.sub(r"[.,;:!?\]]+$", "", den_raw)
        # Double-slash debris ("0/1/(2+1)", folio "2/0/5"): operands must
        # never hold "/" themselves.
        if "/" in num_raw or "/" in den_raw:
            continue
        if not num_raw or not den_raw:
            continue
        # Keep the slash sides tight: surrounding words ("Find", "OR") that
        # the regex greedily absorbs (no spaces around "/" means none, but
        # spaced "x / y" captures exactly) — split sides on whitespace and
        # keep the token adjacent to the slash.
        num_tok = num_raw.split()[-1] if num_raw.split() else num_raw
        den_tok = den_raw.split()[0] if den_raw.split() else den_raw
        # Stray fences / label debris ("2)", "a)", "Q5"): unbalanced parens
        # are never fraction sides ("(x-3)" is balanced and stays).
        for _tok in (num_tok, den_tok):
            if _tok.count("(") != _tok.count(")"):
                break
            if _tok.count("[") != _tok.count("]"):
                break
            if re.match(r"^[Qq]\d", _tok) or re.match(r"^[A-Za-z]\d{2,}$", _tok):
                break
            if re.match(r"^\(?[A-Za-z]\)?[\).]$", _tok) and len(
                re.sub(r"[^A-Za-z]", "", _tok)
            ) == 1:
                # Single label-like token ("a)", "(A)") — never a side alone.
                # (Multi-char operands like "(x-3)" contain math and pass.)
                if not _FRACTION_OPERAND_MATH_RE.search(
                    re.sub(r"[\(\)\[\]]", "", _tok)
                ):
                    break
        else:
            pass
        if _tok.count("(") != _tok.count(")") or _tok.count("[") != _tok.count(
            "]"
        ):
            continue
        if re.match(r"^[Qq]\d", num_tok) or re.match(r"^[Qq]\d", den_tok):
            continue
        if not _valid_fraction_operand(num_tok) or not _valid_fraction_operand(den_tok):
            continue
        # Nearby context (40 chars around the slash): folio bare numbers
        # ("2/0", "5/1") never sit near option labels/math, option values
        # ("1/81", "1/10") always do. Whole-block context is too broad for
        # mega-paragraphs that mix folio headers with real questions.
        _ctx = block_text[max(0, m.start() - 40) : m.end() + 40]
        # Bare-integer pairs need MCQ option labels nearby (folio guard):
        # uppercase "(A)"–"(D)" only — lowercase "a)" are maths2 part labels
        # ("a) Give...") that folio headers ("0 5/1 2") borrow in mega-paras.
        if _FRACTION_BARE_INT_RE.match(
            re.sub(r"\s+", "", num_tok)
        ) and _FRACTION_BARE_INT_RE.match(re.sub(r"\s+", "", den_tok)):
            if not re.search(r"\([A-D]\)", _ctx):
                continue
        # Single-letter/single-letter without digits ("x/y" in "x/y-plane")
        # needs real math nearby, otherwise it is prose ("xy-plane").
        _num_nospace = re.sub(r"\s+", "", num_tok)
        _den_nospace = re.sub(r"\s+", "", den_tok)
        if re.fullmatch(
            r"[a-zA-Zπ]", _num_nospace
        ) and re.fullmatch(r"[a-zA-Zπ]", _den_nospace):
            if not re.search(r"[∫∑∏√∞πθ^_=≤≥≠]|\([A-Da-d]\)", _ctx):
                continue
        frac = f"{num_tok}/{den_tok}"
        if frac in seen:
            continue
        # Length guard: stems, not operands.
        if len(frac) > 48:
            continue
        seen.add(frac)
        out.append(frac)
        if len(out) >= 8:
            break
    return out


def _reject_fraction_text(frac_text: str) -> str | None:
    """Classify a candidate "num/den" string: None = genuine; else a reason.

    Pure validator (no emission): 'zero-denominator' for division-by-zero
    hallucinations (limits misread as fractions), 'garbage' for artifact
    soup (fence PUA, hat litter, doubled-letter stutter, prose sides).
    Debris the extractor already drops never reaches here.
    """
    import unicodedata as _ud
    try:
        folded = _ud.normalize("NFKC", frac_text or "")
    except Exception:
        folded = frac_text or ""
    if any(ch in _GARBAGE_ARTIFACT_CHARS for ch in folded):
        return "garbage"
    if _DOUBLED_LETTER_RE.search(folded):
        return "garbage"
    parts = folded.split("/")
    if len(parts) != 2:
        return "garbage"
    num, den = parts[0].strip(), parts[1].strip()
    if _is_zero_denominator_text(den):
        return "zero-denominator"
    for side in (num, den):
        core = _strip_side_fences(side)
        if core and _PROSE_SIDE_RE.match(core) and not _FRACTION_OPERAND_FUNC_RE.match(core):
            return "garbage"
    return None


def _note_inline_fallback(block, *, reason: str) -> None:
    """Record an honest fallback on the host paragraph (text is preserved).

    The host keeps its slash text, so nothing is lost; the builder carries
    this count into report["equation_fallbacks"] instead of silently
    dropping the candidate or minting fake OMML.
    """
    try:
        extra = getattr(block, "extra", None)
        if not isinstance(extra, dict):
            return
        extra["inlineFallbacks"] = int(extra.get("inlineFallbacks", 0) or 0) + 1
        if reason == "zero-denominator":
            extra["zeroDenominatorRejected"] = True
    except Exception:
        pass


def _attach_inline_math(block, *, kind: str, text: str, latex: str,
                        mathir_doc: dict, recognizer: str, routing_action: str) -> None:
    """Attach a derived equation to its host paragraph's math stream.

    The host paragraph keeps its text; the builder renders the entry as an
    inline <m:oMath> run in the SAME <w:p> — never a standalone block, so
    genuine OMML is never detached from its owning question paragraph.
    """
    try:
        extra = getattr(block, "extra", None)
        if not isinstance(extra, dict):
            return
        entries = extra.get("inlineMath")
        if not isinstance(entries, list):
            entries = []
            extra["inlineMath"] = entries
        entries.append({
            "text": text,
            "latex": latex,
            "mathir": mathir_doc,
            "mathirHash": hashlib.sha256(
                json.dumps(mathir_doc, sort_keys=True).encode()
            ).hexdigest()[:16],
            "recognizer": recognizer,
            "routing": routing_action,
            "kind": kind,
        })
    except Exception:
        pass


_CELL_RE = re.compile(r"^[−–—-]?(\d+(?:\.\d+)?|[a-zA-Zπ])$")


def _table_is_matrix(content: str, grid: list[list[str]]) -> bool:
    """True when a table grid is a genuine math matrix (not prose/options)."""
    if not grid or not all(grid):
        return False
    nrows, ncols = len(grid), len(grid[0])
    if not (2 <= nrows <= 5 and 2 <= ncols <= 5):
        return False
    if any(len(r) != ncols for r in grid):
        return False
    # Fence evidence: matrix tables carry brackets; option/frequency tables
    # ("2 𝑎 2 𝑎 | ...") do not. Without fences this is not a matrix.
    if not any(f in content for f in ("⎛", "⎜", "⎝", "[", "]", "(", ")")):
        return False
    # Every cell short math; at least half the cells carry digits (numeric
    # matrix). Letter-soup ("b l", "R S") fails here and stays text.
    total = nrows * ncols
    digit_cells = 0
    for row in grid:
        for cell in row:
            c = (cell or "").strip()
            if not c or len(re.sub(r"\s+", "", c)) > 6:
                return False
            if c in _BOUND_DEBRIS or c in ("b l", "^h", ">H", "R", "S", "V", "W", "T", "X"):
                return False
            if not _CELL_RE.match(re.sub(r"\s+", "", c)):
                return False
            if any(ch.isdigit() for ch in c):
                digit_cells += 1
    return digit_cells / total >= 0.5


_ITEM_LABEL_RE = re.compile(r"^(?P<label>(?:Q\d+|\d+|[a-z]|[ivx]+)[.):-])\s+(?P<rest>.+)$", re.IGNORECASE)

#: Parenthesized question numbers ("(1) E(X) = 7"): item metadata, never
#: equation content. Handled separately from _ITEM_LABEL_RE so math
#: fences ("(x+1)(x+2) = 0") are never stripped — only bare digits.
_PAREN_NUMBER_RE = re.compile(r"^(?P<label>\(\d+\))\s+(?P<rest>.+)$")


def split_item_label(text: str) -> tuple[str, str | None]:
    """Strip leading list markers ("1.", "(a)", "(1)", "Q7:") into metadata."""
    m = _ITEM_LABEL_RE.match(text.strip())
    if m and len(m.group("rest")) >= 2:
        return m.group("rest"), m.group("label")
    m = _PAREN_NUMBER_RE.match(text.strip())
    if m and len(m.group("rest")) >= 2:
        return m.group("rest"), m.group("label")
    return text, None


def _segment_paragraph(text: str, recognizer) -> list | None:
    """ADR-2/ADR-3: split a paragraph into ordered text/math segments.

    Every math span is run through the recognizer and the single
    promotion gate; only spans that keep confidence out of ``escalate``,
    pass ``is_promotable`` and validate as MathIR stay math — everything
    else is demoted to text (never guessed). Returns None when no span
    survives, so the block keeps its plain paragraph path.
    """
    spans = split_math_spans(text)
    if not any(s.kind == "math" for s in spans):
        return None
    segments: list[dict] = []
    promoted = False
    for span in spans:
        if span.kind != "math":
            segments.append({"kind": "text", "text": span.text})
            continue
        try:
            rec = recognizer.recognize(span.text)
        except Exception:
            segments.append({"kind": "text", "text": span.text})
            continue
        routing = route_confidence(rec.confidence)
        ok, _reason = is_promotable(span.text, rec.mathir)
        if (
            routing.action != "escalate"
            and ok
            and _mathir.validate_mathir(rec.mathir) == []
        ):
            segments.append({
                "kind": "math",
                "text": span.text,
                "mathir": rec.mathir,
                "latex": rec.latex,
                "recognizer": rec.recognizer,
                "confidence": rec.confidence,
            })
            promoted = True
        else:
            # A wrong editable equation is worse than plain text.
            segments.append({"kind": "text", "text": span.text})
    if not promoted:
        return None
    return segments


def _segment_cell_line_fallback(line: str, recognizer) -> list[dict] | None:
    """Fallback segmentation for a table-cell line when _segment_paragraph returns None.

    Checks (1) whole-line equation promotion (preserving leading labels and
    trailing equation numbers as text segments) and (2) validated stacked
    fractions, always covering ``line`` losslessly without duplicating text.
    """
    if not line or not line.strip():
        return None
    numbered = split_equation_number(line)
    candidate_text, _ = split_item_label(numbered.body)
    candidate_text, section_tag = strip_leading_section_tag(candidate_text)
    if section_tag is not None:
        candidate_text, _ = split_item_label(candidate_text)
    candidate_text, _ = strip_leading_option_label(candidate_text)
    candidate_text = candidate_text.strip()
    if candidate_text and is_equation_line(candidate_text):
        idx = line.find(candidate_text)
        if idx >= 0:
            try:
                rec = recognizer.recognize(candidate_text)
            except Exception:
                rec = None
            if rec is not None:
                routing = route_confidence(rec.confidence)
                ok, _ = is_promotable(candidate_text, rec.mathir)
                if (
                    routing.action != "escalate"
                    and ok
                    and _mathir.validate_mathir(rec.mathir) == []
                ):
                    prefix = line[:idx]
                    suffix = line[idx + len(candidate_text) :]
                    segs: list[dict] = []
                    if prefix:
                        segs.append({"kind": "text", "text": prefix})
                    segs.append({
                        "kind": "math",
                        "text": candidate_text,
                        "mathir": rec.mathir,
                        "latex": rec.latex,
                        "recognizer": rec.recognizer,
                        "confidence": rec.confidence,
                    })
                    if suffix:
                        segs.append({"kind": "text", "text": suffix})
                    return segs
    if "/" in line:
        segs = []
        cursor = 0
        promoted = False
        for frac_text in _extract_stacked_fractions(line):
            if _reject_fraction_text(frac_text) is not None:
                continue
            try:
                rec = recognizer.recognize(frac_text)
            except Exception:
                continue
            routing = route_confidence(rec.confidence)
            if (
                routing.action == "escalate"
                or "fraction" not in str(rec.mathir)
                or _mathir.validate_mathir(rec.mathir) != []
            ):
                continue
            ok, _ = is_promotable(frac_text, rec.mathir)
            if not ok:
                continue
            pos = line.find(frac_text, cursor)
            if pos < 0:
                continue
            if pos > cursor:
                segs.append({"kind": "text", "text": line[cursor:pos]})
            segs.append({
                "kind": "math",
                "text": frac_text,
                "mathir": rec.mathir,
                "latex": rec.latex,
                "recognizer": rec.recognizer,
                "confidence": rec.confidence,
            })
            cursor = pos + len(frac_text)
            promoted = True
        if promoted:
            if cursor < len(line):
                segs.append({"kind": "text", "text": line[cursor:]})
            return segs
    return None


def _enrich_table_cells(blocks: list, recognizer) -> None:
    """Segment the mathematics inside table cells (ADR-2/ADR-3).

    An exam paper keeps its questions and options inside a ruled grid, so
    the mathematics lives in CELLS, not in body paragraphs. Without this
    pass a source with ruling lines loses every equation: SQP went from 85
    OMML blocks to 0 once the grid was reconstructed. Each cell line is
    segmented on its own (segments cover a line exactly once) and the
    result is attached to the table spec for the builder.
    """
    for block in blocks:
        if getattr(block, "kind", "") != "table":
            continue
        extra = getattr(block, "extra", None)
        if not isinstance(extra, dict):
            continue
        spec = extra.get("table")
        if not isinstance(spec, dict):
            continue
        rows = spec.get("rows") or []
        if not rows:
            continue
        cell_segments: list[list] = []
        found = False
        for row in rows:
            row_segments: list[list] = []
            for cell in row:
                line_segments: list = []
                for line in str(cell or "").split("\n"):
                    segs = _segment_paragraph(line, recognizer) if line.strip() else None
                    if segs is None and line.strip():
                        segs = _segment_cell_line_fallback(line, recognizer)
                    line_segments.append(segs)
                    if segs:
                        found = True
                row_segments.append(line_segments)
            cell_segments.append(row_segments)
        if found:
            spec["cellSegments"] = cell_segments


def enrich_blocks(blocks: list, *, recognizer=None) -> list:
    recognizer = recognizer or DeterministicAsciiRecognizer()
    _enrich_table_cells(blocks, recognizer)
    for block in blocks:
        if getattr(block, "kind", "") != "paragraph":
            continue
        numbered = split_equation_number(block.text)
        if numbered.number is not None:
            block.extra["number"] = numbered.number
        candidate_text, item_label = split_item_label(numbered.body)
        if item_label is not None:
            block.extra["itemLabel"] = item_label
        # Leading section tags ("Section-D (1) ...") are metadata: strip
        # before the item/option splits so "(1)" is seen and recorded.
        candidate_text, section_tag = strip_leading_section_tag(candidate_text)
        if section_tag is not None:
            block.extra["sectionTag"] = section_tag
            candidate_text, item_label = split_item_label(candidate_text)
            if item_label is not None:
                block.extra["itemLabel"] = item_label
        # A leading option label ("(D) −7") is metadata: the math core
        # promotes without the letter, never as "(D)−7" OMML.
        candidate_text, option_label = strip_leading_option_label(candidate_text)
        if option_label is not None:
            block.extra["optionLabel"] = option_label
        candidate = score_text(candidate_text)
        if not is_equation_line(candidate_text):
            if candidate.score >= 0.25:
                block.extra["mathHint"] = {
                    "score": candidate.score,
                    "note": "inline math suspected; inline splitting lands with the ML stage",
                }
            continue
        recognition = recognizer.recognize(candidate_text)
        routing = route_confidence(recognition.confidence)
        if routing.action == "escalate" or not has_math_kernel(
            recognition.mathir.get("root", {})
        ):
            # A wrong editable equation is worse than a marked fallback:
            # structure-free parses ("(A) 1", "[1]", "Part-C") keep their
            # text and carry a warning flag — never a guessed equation.
            block.extra["mathHint"] = {
                "score": candidate.score,
                "recognitionConfidence": recognition.confidence,
                "note": "low confidence; preserved as text with image-fallback flag",
                "fallback": "image",
            }
            continue
        _zero_hit = _mathir_has_zero_denominator(recognition.mathir)
        _garbage_hit = _mathir_has_garbage(recognition.mathir)
        if _zero_hit or _garbage_hit:
            # Hallucinated equation ("1yy", "227qqssss", "pi/0"): an editable
            # equation would be confidently wrong, so the text is preserved
            # with a counted fallback flag instead of fake OMML.
            block.extra["mathHint"] = {
                "score": candidate.score,
                "recognitionConfidence": recognition.confidence,
                "note": "rejected as hallucinated equation (zero denominator or garbage content); preserved as text",
                "fallback": "text",
            }
            _note_inline_fallback(
                block, reason="zero-denominator" if _zero_hit else "garbage"
            )
            continue
        # ADR-5: the single promotion gate owns whole-line promotions too.
        # Short answer/option fragments (bare numbers, lone constants) pass
        # the kernel guard yet render as <3-meaningful-char OMML — the gate
        # keeps them as text and the miss is counted, never fake OMML.
        promotable, reason = is_promotable(candidate_text, recognition.mathir)
        if not promotable:
            block.extra["mathHint"] = {
                "score": candidate.score,
                "recognitionConfidence": recognition.confidence,
                "note": f"rejected by promotion gate ({reason}); preserved as text",
                "fallback": "text",
            }
            _note_inline_fallback(block, reason=reason)
            continue
        block.kind = "equation"
        block.confidence = recognition.confidence
        block.extra.update(
            {
                "latex": recognition.latex,
                "mathir": recognition.mathir,
                "mathirHash": hashlib.sha256(
                    json.dumps(recognition.mathir, sort_keys=True).encode()
                ).hexdigest()[:16],
                "recognizer": recognition.recognizer,
                "routing": routing.action,
            }
        )
    # --- End-to-end structure pass: definite integrals → limit (m:nary),
    # bracket grids → matrix (m:m). Derived equations MERGE back into their
    # host paragraph's math stream (inline <m:oMath> in the same <w:p>) —
    # never standalone blocks — so OMML is never detached from its question.
    # Table matrices stay standalone (their host is a table, not prose).
    # A failed extraction simply yields no equation: honest fallback, never
    # fake. Rejected hallucinations count as host fallbacks.
    try:
        from ..understanding.blocks import Block as _Block
    except Exception:
        _Block = None  # type: ignore
    if _Block is not None:
        additions: list = []
        for block in blocks:
            kind = getattr(block, "kind", "")
            text = getattr(block, "text", "") or ""
            extra = getattr(block, "extra", None)
            if not isinstance(extra, dict):
                extra = {}
            # ADR-3/ADR-2: paragraphs and headings that were not promoted
            # whole-line get inline span segmentation. When any span
            # survives the single promotion gate, the block carries ordered
            # segments covering its text exactly once — and the legacy
            # inline passes below are skipped for this block so math is
            # never emitted twice.
            if kind in ("paragraph", "heading") and not extra.get("segments"):
                segments = _segment_paragraph(text, recognizer)
                if segments:
                    extra["segments"] = segments
                    block.extra = extra
            if extra.get("segments"):
                continue
            # Matrix tables → MathIR matrix (MathSample Q32 p6-t0).
            if kind == "table":
                extra = getattr(block, "extra", {}) or {}
                grid = (extra.get("table") or {}).get("rows") if isinstance(extra, dict) else None
                if isinstance(grid, list) and _table_is_matrix(text, grid):
                    rows = [[_mathir.text(str(c).strip()) for c in r] for r in grid]
                    doc = _mathir.wrap(_mathir.matrix(rows))
                    if _mathir.validate_mathir(doc) == [] and has_math_kernel(doc.get("root", {})):
                        additions.append(
                            _Block(
                                id=f"{block.id}-mat",
                                kind="equation",
                                page_number=getattr(block, "page_number", 0),
                                bbox=list(getattr(block, "bbox", [0, 0, 1, 1])),
                                text="matrix " + " ; ".join(" ".join(str(c) for c in r) for r in grid),
                                size=float(getattr(block, "size", 10.0) or 10.0),
                                bold=False,
                                confidence=0.92,
                                extra={
                                    "latex": "matrix",
                                    "mathir": doc,
                                    "mathirHash": hashlib.sha256(
                                        json.dumps(doc, sort_keys=True).encode()
                                    ).hexdigest()[:16],
                                    "recognizer": "matrix-geometry-0.1",
                                    "routing": "secondary_check",
                                    "derivedFrom": block.id,
                                },
                            )
                        )
            # Stacked fractions inside prose stems/options (Q12 1/10, Q18
            # 1/81, Q22 π/4+x/2+dy/dx, Q23A (x-3)/(x-1)^3, Q33A/B). Each
            # validated slash token becomes a derived equation (m:f); debris
            # stays text. Original paragraphs keep their text.
            # Stacked fractions inside prose stems/options (Q12 1/10, Q18
            # 1/81, Q22 π/4+x/2+dy/dx, Q23A (x-3)/(x-1)^3, Q33A/B). Each
            # validated slash token MERGES back into its host paragraph's
            # math stream (inline <m:oMath> in the same <w:p>) — never a
            # standalone block, so OMML is never detached from its question.
            # Zero denominators and garbage are rejected with a counted
            # fallback; debris stays text. Host paragraphs keep their text.
            if kind == "paragraph" and "/" in text:
                for frac_text in _extract_stacked_fractions(text):
                    reason = _reject_fraction_text(frac_text)
                    if reason is not None:
                        # Zero-denominator hallucinations and garbage that
                        # survived extraction: host text is preserved, the
                        # miss is counted — never fake OMML.
                        _note_inline_fallback(block, reason=reason)
                        continue
                    try:
                        rec = recognizer.recognize(frac_text)
                    except Exception:
                        _note_inline_fallback(block, reason="unrecognized")
                        continue
                    routing2 = route_confidence(rec.confidence)
                    root = rec.mathir.get("root", {})
                    if (
                        routing2.action == "escalate"
                        or not has_math_kernel(root)
                        or "fraction" not in str(rec.mathir)
                    ):
                        continue
                    if _mathir.validate_mathir(rec.mathir) != []:
                        continue
                    if _mathir_has_zero_denominator(rec.mathir):
                        _note_inline_fallback(block, reason="zero-denominator")
                        continue
                    if _mathir_has_garbage(rec.mathir):
                        _note_inline_fallback(block, reason="garbage")
                        continue
                    ok, reason = is_promotable(frac_text, rec.mathir)
                    if not ok:
                        _note_inline_fallback(block, reason=reason)
                        continue
                    _attach_inline_math(
                        block,
                        kind="fraction",
                        text=frac_text,
                        latex=rec.latex,
                        mathir_doc=rec.mathir,
                        recognizer=rec.recognizer,
                        routing_action=routing2.action,
                    )
        blocks.extend(additions)
    return blocks
