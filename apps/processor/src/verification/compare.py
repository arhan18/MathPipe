"""Deterministic verification checks (§18.2). No AI, no GPU — cheap signals
first. Every check returns typed issues; absence of issues is itself data.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import pdfplumber

from ..mathengine.mathir import validate_mathir
from ..mathengine.normalize import normalize_latex
from ..understanding.text import extract_page_text

OMATH_RE = re.compile(r"<m:oMath(?:\s|>)")

#: Raw LaTeX control sequences must never survive inside MathIR text nodes.
#: Structured MathIR uses operator/function/root nodes; a literal "\int" text
#: node means the recognizer gave up mid-parse and stuffed source text into
#: the tree. The DOCX builder renders it verbatim, so the equation ships
#: corrupted (e.g. a 5-mark integral reading "\int ...") with no warning.
LATEX_CMD_RE = re.compile(r"\\[a-zA-Z]+")

#: U+FFFD (replacement character) is an honest marker for an unmapped glyph —
#: content was LOST on the way in (missing ToUnicode, unmapped PUA). A single
#: FFFD means a corrupted symbol shipped as "�"; ICSE shipped 12–14 with
#: critical:0/shippable True. Any FFFD in model text or DOCX-bound strings
#: is critical (shippable False).
REPLACEMENT_CHAR = "\ufffd"

#: Unmapped private-use codepoints become U+FFFD at the DOCX boundary (see
#: word/omml.sanitize_xml_text). Flag them in the model too: they will ship
#: as "�" even though the model JSON looks clean.
_UNMAPPED_PUA_RE = re.compile("[\ue000-\uf8ff\U000f0000-\U000ffffd\U00100000-\U0010fffd]")

#: Math-symbol density gate for the zero-OMML check. Source pages carrying
#: at least this many math symbols are math-heavy; shipping ~0 genuine OMML
#: for them means equations were dropped or image-fallbacked silently.
#: SQP carries 45 symbols across 10 pages with 1 oMath — firmly above.
MATH_SYMBOLS = "∫∑πθ√∞±×÷≤≥≠≈∂∇∈∉∆"
_MATH_SYMBOL_THRESHOLD = 10
#: Genuine-OMML counts at or below this are "~0" (SQP shipped 0–1 oMath for
#: 45 symbols — a near-total equation miss, not a rounding error).
_MATH_DENSITY_OMML_FLOOR = 1
#: Proportional backstop: equation detection keeps improving (parallel
#: mathengine work), so an absolute floor alone goes stale. When the source
#: carries >= _MATH_DENSITY_PROPORTIONAL_MIN symbols yet each emitted
#: equation covers fewer than ~1/6 of them, the miss is still critical
#: (SQP: 45 symbols, 5–6 oMath → 30–36 < 45, fires stably across runs).
_MATH_DENSITY_PROPORTIONAL_MIN = 20
_MATH_DENSITY_SYMBOLS_PER_EQUATION = 6

#: Top-level question labels ("22", "23A", "33B") at source line starts.
#: Compared source→model; a label present in the PDF but absent from the
#: model means a whole question never survived block segmentation.
QUESTION_LABEL_RE = re.compile(r"(?m)^[ \t]*(\d{1,2})[ \t]*([AB])?[ \t]*[.\)]")

#: Recall floor: below this share of a page's source vocabulary present in
#: the model, content was dropped on the way in (not merely reworded).
COVERAGE_FLOOR = 0.85
#: Pages with fewer source tokens than this are too small to judge.
MIN_COVERAGE_TOKENS = 30
#: Cap per-check issue spam on very broken documents.
MAX_SEQUENCE_ISSUES = 25


@dataclass
class Issue:
    page_number: int
    block_id: str | None
    category: str  # missing_text | equation_structure | equation_count | table | figure | reading_order
    severity: str  # critical | warning
    detail: str
    suggested_action: str = "review"


@dataclass
class CheckReport:
    check: str
    issues: list[Issue] = field(default_factory=list)
    checked: int = 0


def check_text_presence(pdf_path: str, model: dict) -> CheckReport:
    """Every model text block should be findable in the source PDF text."""
    report = CheckReport(check="text_presence")
    try:
        with pdfplumber.open(pdf_path) as pdf:
            source = "\n".join((page.extract_text() or "") for page in pdf.pages)
    except Exception:
        return CheckReport(check="text_presence", issues=[
            Issue(0, None, "missing_text", "warning", "source unreadable for comparison", "retry"),
        ])
    norm_source = "".join(source.split())
    for page in model.get("document", {}).get("pages", []):
        for block in page.get("blocks", []):
            content = block.get("content") or ""
            if block.get("type") not in ("paragraph", "heading") or len(content.strip()) < 12:
                continue
            report.checked += 1
            probe = "".join(content.split())[:60]
            if probe and probe not in norm_source:
                report.issues.append(Issue(
                    page.get("pageNumber", 0), block.get("id"), "missing_text", "warning",
                    f"text not found in source: {content[:60]!r}", "review",
                ))
    return report


def _mathir_text_values(node, out: list) -> list:
    """Collect every text-node value in a MathIR tree."""
    if isinstance(node, dict):
        if node.get("type") == "text":
            out.append(str(node.get("value", "")))
        for value in node.values():
            _mathir_text_values(value, out)
    elif isinstance(node, list):
        for value in node:
            _mathir_text_values(value, out)
    return out


def check_equation_structure(model: dict) -> CheckReport:
    """Re-validate every equation block: MathIR schema + LaTeX normalization."""
    report = CheckReport(check="equation_structure")
    for page in model.get("document", {}).get("pages", []):
        for block in page.get("blocks", []):
            if block.get("type") != "equation":
                continue
            report.checked += 1
            mathir = block.get("mathir")
            if not isinstance(mathir, dict):
                report.issues.append(Issue(
                    page.get("pageNumber", 0), block.get("id"), "equation_structure",
                    "critical", "equation block has no MathIR", "repair",
                ))
                continue
            violations = validate_mathir(mathir)
            if violations:
                report.issues.append(Issue(
                    page.get("pageNumber", 0), block.get("id"), "equation_structure",
                    "critical", f"MathIR invalid: {violations[0]}", "repair",
                ))
            latex = block.get("latex", "")
            if latex != normalize_latex(latex):
                report.issues.append(Issue(
                    page.get("pageNumber", 0), block.get("id"), "equation_structure",
                    "warning", "stored LaTeX is not in normalized form", "repair",
                ))
            leaked = sorted({
                m.group(0)
                for value in _mathir_text_values(mathir, [])
                for m in LATEX_CMD_RE.finditer(value)
            })
            if leaked:
                report.issues.append(Issue(
                    page.get("pageNumber", 0), block.get("id"), "equation_structure",
                    "critical",
                    f"unclean equation parse (confidence {block.get('confidence', '?')}): "
                    f"raw LaTeX {leaked} embedded in MathIR text; DOCX will show "
                    f"literal {leaked[0]} instead of the equation",
                    "review",
                ))
    return report


def check_docx_consistency(model: dict, docx_bytes: bytes) -> CheckReport:
    """Cross-check the built DOCX against the model that produced it."""
    import io
    import zipfile

    report = CheckReport(check="docx_consistency")
    try:
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
    except Exception:
        return CheckReport(check="docx_consistency", issues=[
            Issue(0, None, "equation_count", "critical", "DOCX unreadable", "retry"),
        ])
    expected_equations = sum(
        1 for p in model.get("document", {}).get("pages", [])
        for b in p.get("blocks", [])
        if b.get("type") == "equation" and isinstance(b.get("mathir"), dict)
    )
    report.checked = expected_equations
    found = len(OMATH_RE.findall(xml))
    if found < expected_equations:
        report.issues.append(Issue(
            0, None, "equation_count", "critical",
            f"model has {expected_equations} native equations but DOCX has {found} oMath",
            "repair",
        ))
    expected_tables = sum(
        1 for p in model.get("document", {}).get("pages", [])
        for b in p.get("blocks", []) if b.get("type") == "table"
    )
    if expected_tables and f"<w:tbl" not in xml:
        report.issues.append(Issue(0, None, "table", "critical", "model tables missing from DOCX", "repair"))
    return report


_DOUBLED_MATH_ALNUM_RE = re.compile(r"([\U0001D400-\U0001D7FF])\1")


def _word_tokens(text: str) -> set[str]:
    text = _DOUBLED_MATH_ALNUM_RE.sub(r"\1", text)
    text = unicodedata.normalize("NFKC", text)
    return {t for t in re.findall(r"[A-Za-z0-9]+", text.lower()) if len(t) >= 2}


def _block_text_parts(block: dict) -> list[str]:
    """Collect text strings from a model block, its labels, segments, and table rows."""
    parts: list[str] = []
    content = block.get("content")
    if isinstance(content, str) and content:
        parts.append(content)
    for key in ("itemLabel", "optionLabel", "sectionTag"):
        val = block.get(key)
        if isinstance(val, str) and val:
            parts.append(val)
    segments = block.get("segments")
    if isinstance(segments, list):
        for seg in segments:
            if isinstance(seg, dict):
                text = seg.get("text")
                if isinstance(text, str) and text:
                    parts.append(text)
    table = block.get("table")
    if isinstance(table, dict):
        rows = table.get("rows")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, list):
                    for cell in row:
                        if isinstance(cell, str) and cell:
                            parts.append(cell)
    return parts


def check_source_coverage(pdf_path: str, model: dict) -> CheckReport:
    """Recall direction: how much of the SOURCE page survived into the model.

    check_text_presence only asks "is model text grounded in the source?"
    (precision). A whole dropped question passes that check trivially —
    absent text cannot mismatch. This check inverts it per page and escalates
    to critical when a page's vocabulary goes missing en masse.
    """
    report = CheckReport(check="source_coverage")
    try:
        extracted_pages = extract_page_text(pdf_path)
        sources = [(p.page_number, " ".join(w.text for w in p.words)) for p in extracted_pages]
    except Exception:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                sources = [(i + 1, page.extract_text() or "") for i, page in enumerate(pdf.pages)]
        except Exception:
            return CheckReport(check="source_coverage", issues=[
                Issue(0, None, "missing_text", "warning", "source unreadable for comparison", "retry"),
            ])
    model_pages = {p.get("pageNumber", 0): p for p in model.get("document", {}).get("pages", [])}
    for page_number, source in sources:
        report.checked += 1
        src_tokens = _word_tokens(source)
        if len(src_tokens) < MIN_COVERAGE_TOKENS:
            continue
        page = model_pages.get(page_number, {})
        model_tokens = _word_tokens(" ".join(
            part
            for b in page.get("blocks", [])
            for part in _block_text_parts(b)
        ))
        recall = len(src_tokens & model_tokens) / len(src_tokens)
        if recall < COVERAGE_FLOOR:
            missing = sorted(src_tokens - model_tokens)[:8]
            report.issues.append(Issue(
                page_number, None, "missing_text", "critical",
                f"page {page_number}: only {recall:.0%} of source vocabulary present "
                f"in model (e.g. missing {missing}); content dropped before verification",
                "review",
            ))
    return report


def check_question_sequence(pdf_path: str, model: dict) -> CheckReport:
    """Every numbered question label in the source must exist in the model.

    Labels ("22", "23A", "33B") are the cheapest whole-question-drop signal:
    a label with no counterpart in any model block means that question never
    survived segmentation, regardless of downstream causes.
    """
    report = CheckReport(check="question_sequence")
    try:
        with pdfplumber.open(pdf_path) as pdf:
            sources = [(i + 1, page.extract_text() or "") for i, page in enumerate(pdf.pages)]
    except Exception:
        return CheckReport(check="question_sequence", issues=[
            Issue(0, None, "missing_text", "warning", "source unreadable for comparison", "retry"),
        ])
    model_text = "\n".join(
        part
        for p in model.get("document", {}).get("pages", [])
        for b in p.get("blocks", [])
        for part in _block_text_parts(b)
    )
    seen: set[str] = set()
    for page_number, source in sources:
        for match in QUESTION_LABEL_RE.finditer(source):
            label = match.group(1) + (match.group(2) or "")
            if label in seen:
                continue
            seen.add(label)
            report.checked += 1
            probe = re.compile(r"(?<![0-9A-Z])" + re.escape(label) + r"(?![0-9A-Za-z])")
            if not probe.search(model_text):
                report.issues.append(Issue(
                    page_number, None, "missing_text", "critical",
                    f"question {label} present in source (page {page_number}) "
                    f"but absent from model; whole question dropped",
                    "review",
                ))
                if len(report.issues) >= MAX_SEQUENCE_ISSUES:
                    return report
    return report


def check_figure_assets(model: dict) -> CheckReport:
    """Every figure stub must carry an extracted asset.

    Figure blocks with assetId None render as nothing: the DOCX builder only
    counts them as figure_missing and that count never reaches verification.
    Question-critical figures (graphs, shaded regions) vanish silently.
    Glyph-scrap rejection (pipeline/figures) leaves the region stub with a
    pending flag and no payload — that is a missing figure too.
    """
    report = CheckReport(check="figure_assets")
    for page in model.get("document", {}).get("pages", []):
        for block in page.get("blocks", []):
            if block.get("type") != "figure":
                continue
            report.checked += 1
            if not block.get("assetId") or block.get("pending") or not block.get("imageBase64"):
                report.issues.append(Issue(
                    page.get("pageNumber", 0), block.get("id"), "figure", "critical",
                    "figure has no extracted asset; figure content will be "
                    "absent from DOCX (dangling figure-engine stub)",
                    "review",
                ))
    return report


def _model_docx_bound_strings(block: dict) -> list[str]:
    """Every string from a block that reaches the DOCX (sanitized)."""
    out: list[str] = []
    for key in ("content", "latex", "caption"):
        value = block.get(key)
        if isinstance(value, str) and value:
            out.append(value)
    table = block.get("table")
    if isinstance(table, dict):
        for row in table.get("rows", []) or []:
            if isinstance(row, list):
                out.extend(str(cell) for cell in row if isinstance(cell, str))
            elif isinstance(row, str):
                out.append(row)
    mathir = block.get("mathir")
    if isinstance(mathir, dict):
        try:
            out.extend(_mathir_text_values(mathir, []))
        except Exception:
            pass
    return out


def check_replacement_chars(
    model: dict, docx_bytes: bytes | None = None,
) -> CheckReport:
    """Any U+FFFD (or unmapped PUA that becomes one) is a critical loss.

    U+FFFD means a glyph arrived unidentifiable and ships as "�" — a
    corrupted symbol, not a rendering choice. ICSE shipped 12–14 with
    critical:0/shippable True. Both model text and DOCX-bound strings are
    scanned; DOCX bytes (when supplied) are scanned for shipped FFFDs too.
    """
    report = CheckReport(check="replacement_chars")
    for page in model.get("document", {}).get("pages", []):
        for block in page.get("blocks", []):
            report.checked += 1
            strings = _model_docx_bound_strings(block)
            if not strings:
                continue
            fffd = sum(s.count(REPLACEMENT_CHAR) for s in strings)
            pua = sum(len(_UNMAPPED_PUA_RE.findall(s)) for s in strings)
            if fffd or pua:
                parts = []
                if fffd:
                    parts.append(f"{fffd} U+FFFD replacement char(s)")
                if pua:
                    parts.append(f"{pua} unmapped PUA codepoint(s) (ships as U+FFFD)")
                report.issues.append(Issue(
                    page.get("pageNumber", 0), block.get("id"), "missing_text",
                    "critical",
                    f"unrecoverable glyph loss ({', '.join(parts)}) in "
                    f"{block.get('type', '?')} block; DOCX will show "
                    f"� instead of source content",
                    "review",
                ))
    if docx_bytes is not None:
        import io
        import zipfile

        try:
            with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
                xml = z.read("word/document.xml").decode("utf-8")
        except Exception:
            xml = ""
        if xml:
            report.checked += 1
            count = xml.count(REPLACEMENT_CHAR)
            if count:
                report.issues.append(Issue(
                    0, None, "missing_text", "critical",
                    f"built DOCX contains {count} U+FFFD replacement char(s); "
                    f"source glyphs shipped as �",
                    "review",
                ))
    return report


#: Exact-zero denominator shared with the enrich/OMML validators: a
#: fraction over zero is a division-by-zero hallucination (limits misread
#: as a fraction), never an equation.
_HALLUC_ZERO_DEN_RE = re.compile(r"^[\u2212\u2013\u2014-]?0+(\.0+)?$")

#: Extraction-artifact glyphs that are never genuine equation content.
_HALLUC_ARTIFACTS = frozenset("\u239b\u239c\u239d\u239e\u239f\u23a0\u02c6\u02c7\u02d8\u02d9")

#: Doubled letters ("1yy", "qqssss") are extraction stutter, never math.
_HALLUC_DOUBLED_RE = re.compile(r"([A-Za-z])\1")

#: Pure-letter runs of length >= 4 that are not function-led
#: ("integrating", "qqssss") are prose/debris, never math content.
_HALLUC_PROSE_RE = re.compile(r"^[A-Za-z]{4,}$")
#: Function/differential prefixes: implicit multiplication ("logx", "cosx",
#: "dy") is genuine math, so prefix match (not word-boundary) decides. Must
#: stay in sync with the enrich/OMML validators.
_HALLUC_FUNC_LEAD = re.compile(r"^(sin|cos|tan|log|ln|sec|exp|sqrt|lim|dx|dy|dz|dt)", re.IGNORECASE)


def _halluc_strip(value: str) -> str:
    return re.sub(r"[\s\(\)\[\]\{\}.,;:!?]+", "", value or "")


def _halluc_walk(mathir_doc: dict) -> tuple[bool, bool]:
    """Return (has_zero_denominator, has_garbage) for one MathIR document."""
    zero = False
    garbage = False
    stack: list = [mathir_doc.get("root", {})] if isinstance(mathir_doc, dict) else []
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if cur.get("type") == "fraction":
                den_texts = [
                    t for t in _mathir_text_values(cur.get("denominator"), [])
                    if t.strip()
                ]
                if den_texts and _HALLUC_ZERO_DEN_RE.match(_halluc_strip(
                    "".join(re.sub(r"\s+", "", t) for t in den_texts)
                ) or " "):
                    zero = True
            if cur.get("type") == "text":
                v = str(cur.get("value", ""))
                if any(ch in _HALLUC_ARTIFACTS for ch in v):
                    garbage = True
                elif _HALLUC_DOUBLED_RE.search(v):
                    garbage = True
                else:
                    core = _halluc_strip(v)
                    if core and _HALLUC_PROSE_RE.match(core) and not _HALLUC_FUNC_LEAD.match(core):
                        garbage = True
            for value in cur.values():
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(cur, list):
            stack.extend(cur)
    return zero, garbage


def check_hallucinated_equations(model: dict) -> CheckReport:
    """Zero-denominator and garbage-text equations must never ship.

    Post-hoc safety net behind the enrich/OMML validators: a fraction over
    an exact zero (pi/0 from limits misread as a fraction) or MathIR text
    carrying extraction stutter ("1yy", "qqssss" artifacts, fence-PUA/hat
    litter, prose words) is a hallucination. Each offending equation or
    inline entry is critical; honest text fallback is the only valid route.
    """
    report = CheckReport(check="hallucinated_equations")
    targets: list[tuple[int, str | None, str, dict]] = []
    for page in model.get("document", {}).get("pages", []):
        for block in page.get("blocks", []):
            if block.get("type") == "equation" and isinstance(block.get("mathir"), dict):
                targets.append((
                    page.get("pageNumber", 0), block.get("id"),
                    "equation", block["mathir"],
                ))
            inl = block.get("inlineMath")
            if isinstance(inl, list):
                for i, entry in enumerate(inl):
                    if isinstance(entry, dict) and isinstance(entry.get("mathir"), dict):
                        targets.append((
                            page.get("pageNumber", 0), block.get("id"),
                            f"inlineMath[{i}]", entry["mathir"],
                        ))
    for page_number, block_id, label, mathir_doc in targets:
        report.checked += 1
        try:
            zero, garbage = _halluc_walk(mathir_doc)
        except Exception:
            continue
        if zero:
            report.issues.append(Issue(
                page_number, block_id, "equation_structure",
                "critical",
                f"hallucinated equation ({label}): fraction with zero "
                f"denominator (e.g. pi/0 from limits misread as a fraction); "
                f"honest text fallback required, never OMML",
                "review",
            ))
        if garbage:
            report.issues.append(Issue(
                page_number, block_id, "equation_structure",
                "critical",
                f"hallucinated equation ({label}): MathIR text carries "
                f"extraction garbage (doubled-letter stutter, fence/hat "
                f"artifacts or prose words); honest text fallback required",
                "review",
            ))
    return report


def _count_cell_segment_math(table: object) -> int:
    """Count MathIR-backed math segments inside RuledTable cellSegments."""
    if not isinstance(table, dict):
        return 0
    cell_segments = table.get("cellSegments")
    if not isinstance(cell_segments, list):
        return 0
    count = 0
    for row in cell_segments:
        if not isinstance(row, list):
            continue
        for cell in row:
            if not isinstance(cell, list):
                continue
            for line in cell:
                if not isinstance(line, list):
                    continue
                for seg in line:
                    if isinstance(seg, dict) and seg.get("kind") == "math" and isinstance(seg.get("mathir"), dict):
                        count += 1
    return count


def check_math_density(
    pdf_path: str, model: dict, docx_bytes: bytes | None = None,
) -> CheckReport:
    """Math-heavy source with ~0 genuine OMML is a critical equation miss.

    SQP ships shippable True with 0–1 <m:oMath> on a 45-symbol math paper:
    the equation recognizer missed nearly everything yet verification stays
    green because it only compares model→DOCX (both empty). This check
    compares source→output: when the PDF carries math symbols above
    _MATH_SYMBOL_THRESHOLD and genuine OMML is at/below
    _MATH_DENSITY_OMML_FLOOR, equations were dropped before verification.
    A proportional backstop (symbols >= 20 with < 1 equation per 6 symbols)
    keeps the signal stable as block detection improves but still misses
    most inline math.
    """
    report = CheckReport(check="math_density")
    try:
        with pdfplumber.open(pdf_path) as pdf:
            source = "\n".join((page.extract_text() or "") for page in pdf.pages)
    except Exception:
        return report
    symbol_total = sum(source.count(sym) for sym in MATH_SYMBOLS)
    report.checked = symbol_total
    if symbol_total < _MATH_SYMBOL_THRESHOLD:
        return report
    if docx_bytes is not None:
        import io
        import zipfile

        try:
            with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
                xml = z.read("word/document.xml").decode("utf-8")
            omath_count = len(OMATH_RE.findall(xml))
        except Exception:
            omath_count = 0
    else:
        # Standalone equations, inlineMath entries, inline segments, and
        # RuledTable cellSegments all ship as genuine <m:oMath>.
        omath_count = 0
        for p in model.get("document", {}).get("pages", []):
            for b in p.get("blocks", []):
                if b.get("type") == "equation" and isinstance(b.get("mathir"), dict):
                    omath_count += 1
                omath_count += sum(
                    1 for e in (b.get("inlineMath") or [])
                    if isinstance(e, dict) and isinstance(e.get("mathir"), dict)
                )
                omath_count += sum(
                    1 for seg in (b.get("segments") or [])
                    if isinstance(seg, dict) and seg.get("kind") == "math" and isinstance(seg.get("mathir"), dict)
                )
                omath_count += _count_cell_segment_math(b.get("table"))
    absolute_miss = omath_count <= _MATH_DENSITY_OMML_FLOOR
    proportional_miss = (
        symbol_total >= _MATH_DENSITY_PROPORTIONAL_MIN
        and omath_count * _MATH_DENSITY_SYMBOLS_PER_EQUATION < symbol_total
    )
    if absolute_miss or proportional_miss:
        report.issues.append(Issue(
            0, None, "equation_count", "critical",
            f"source carries {symbol_total} math symbols "
            f"({''.join(sorted({s for s in MATH_SYMBOLS if s in source}))}) "
            f"but output has {omath_count} genuine OMML equation(s); "
            f"math-heavy document shipped with near-zero editable equations",
            "review",
        ))
    return report
