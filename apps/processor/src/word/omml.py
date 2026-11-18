"""MathIR → OMML renderer (§12, §60.2). Deterministic, versioned, model-free.

Unsupported constructs produce an explicit UnsupportedConstruct error — never
a silent wrong equation. The caller routes those to the product fallback
(image + warning metadata).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
import re

MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
XML_NS = "http://www.w3.org/XML/1998/namespace"
ET.register_namespace("m", MATH_NS)

#: XML 1.0 illegal chars that lxml/python-docx reject ("All strings must be
#: XML compatible"). \t \n \r are legal and preserved; everything else in
#: C0 controls plus lone surrogates and FFFE/FFFF becomes U+FFFD so
#: surrounding content is never dropped.
_ILLEGAL_XML_CHARS_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")

#: Unmapped private-use codepoints (font-dependent boxes in Word).
#: Extraction remaps known Symbol-font PUA; anything reaching the builder
#: is unidentifiable, so it becomes U+FFFD — an honest, font-independent
#: marker. This is the single choke point for all DOCX text, so output
#: carries an assertion-grade guarantee: zero PUA codepoints.
_UNMAPPED_PUA_RE = re.compile("[\ue000-\uf8ff\U000f0000-\U000ffffd\U00100000-\U0010fffd]")

#: Symbol extensible-bracket pieces exposed as PUA when the font embeds no
#: ToUnicode map (quebank 104 chars, ICSE matrix brackets as U+FFFD already).
#: Adobe Symbol codes E6-E8/F6-F8 are paren top/mid/bottom (U+239B etc.),
#: E9-EB/F9-FB are square top/mid/bottom (U+23A1 etc.). Each bracket draws
#: as 1-4 pieces that pdfplumber groups into one Word; collapse each
#: within-word run to a single ASCII bracket so fallback text stays
#: readable ("Differentiate sin ... w.r.t. x"). Cross-word vertical stacks
#: (4 single-piece Words for one bracket) merge in understanding/blocks.py
#: where y-geometry distinguishes them from genuine "((" nesting; here only
#: within-word runs (no spaces) collapse, never across spaces.
_PUA_LEFT_PAREN_RE = re.compile("[\uf0e6\uf0e7\uf0e8]+")
_PUA_RIGHT_PAREN_RE = re.compile("[\uf0f6\uf0f7\uf0f8]+")
_PUA_LEFT_SQUARE_RE = re.compile("[\uf0e9\uf0ea\uf0eb]+")
_PUA_RIGHT_SQUARE_RE = re.compile("[\uf0f9\uf0fa\uf0fb]+")

#: C0 controls with no Unicode (Wingdings bullets, zero-width mis-extracts
#: such as big2's 500x U+0001). Stripped, never FFFD: they are decorative
#: vector/graphic scraps, not content. Lone surrogates and FFFE/FFFF stay
#: FFFD (real encoding loss, flagged critical via the model-text check since
#: any surviving FFFD in model content trips verification).
_STRIPPABLE_CONTROLS_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")
_LOSS_CHARS_RE = re.compile("[\ud800-\udfff\ufffe\uffff]")


def sanitize_xml_text(value: str) -> str:
    """Best-effort ASCII fallback with FFFD only as a flagged last resort.

    Order: Symbol bracket-piece PUA runs collapse to "()" / "[]" first;
    decorative C0 controls strip to "" (no FFFD); any surviving PUA or
    surrogate/FFFE/FFFF becomes U+FFFD. Survivors are already present in
    model content, so verification.check_replacement_chars flags them
    critical — FFFD never ships silently.
    """
    if not value:
        return value
    value = _PUA_LEFT_PAREN_RE.sub("(", value)
    value = _PUA_RIGHT_PAREN_RE.sub(")", value)
    value = _PUA_LEFT_SQUARE_RE.sub("[", value)
    value = _PUA_RIGHT_SQUARE_RE.sub("]", value)
    value = _STRIPPABLE_CONTROLS_RE.sub("", value)
    value = _UNMAPPED_PUA_RE.sub("\ufffd", value)
    return _LOSS_CHARS_RE.sub("\ufffd", value)

RENDERER_VERSION = "omml-0.1"

SUPPORTED_NODE_TYPES = frozenset({
    "text", "row", "fraction", "superscript", "subscript", "root",
    "operator", "function", "matrix", "cases", "fence", "accent",
    "limit", "underover",
})

ACCENT_CHARS = {
    "hat": "^", "bar": "¯", "dot": ".", "ddot": "..", "tilde": "~",
    "vec": "→", "acute": "´", "grave": "`", "breve": "˘", "check": "ˇ",
}

NARY_CHARS = {"∫": "∫", "∑": "∑", "∏": "∏"}


class UnsupportedConstruct(Exception):
    pass


def _el(tag: str, text: str | None = None, **attrs: str) -> ET.Element:
    namespaced = {}
    for k, v in attrs.items():
        # OOXML val-type attributes live in the math namespace (m:val).
        namespaced[k if (k.startswith("{") or ":" in k) else f"{{{MATH_NS}}}{k}"] = sanitize_xml_text(v)
    el = ET.Element(f"{{{MATH_NS}}}{tag}", namespaced)
    if text is not None:
        el.text = sanitize_xml_text(text)
    return el


def _sub(parent: ET.Element, tag: str, **attrs: str) -> ET.Element:
    """Namespaced-attribute SubElement (m:val etc. per OOXML)."""
    namespaced = {}
    for k, v in attrs.items():
        namespaced[k if (k.startswith("{") or ":" in k) else f"{{{MATH_NS}}}{k}"] = sanitize_xml_text(v)
    return ET.SubElement(parent, f"{{{MATH_NS}}}{tag}", namespaced)


def _run(text: str) -> ET.Element:
    r = _el("r")
    t = ET.SubElement(r, f"{{{MATH_NS}}}t")
    t.set(f"{{{XML_NS}}}space", "preserve")
    t.text = sanitize_xml_text(text)
    return r


def _content(node: dict) -> list[ET.Element]:
    """Render a MathIR node where element content is expected.

    Rows expand inline (OMML allows sibling elements directly); every other
    node yields exactly one element.
    """
    kind = node.get("type")
    if kind in ("text", "operator"):
        return [_run(str(node.get("value", node.get("symbol", ""))))]
    try:
        return [render_node(node)]
    except _RowGroup as group:
        return group.elements


def render_node(node: dict) -> ET.Element:
    kind = node.get("type")
    if kind not in SUPPORTED_NODE_TYPES:
        raise UnsupportedConstruct(f"unknown node type: {kind!r}")
    if kind == "text":
        return _run(str(node.get("value", "")))
    if kind == "operator":
        return _run(str(node.get("symbol", "")))
    if kind == "row":
        out: list[ET.Element] = []
        for child in node.get("children", []):
            out.extend(_content(child))
        raise _RowGroup(out)
    if kind == "fraction":
        # Debris fractions ("^h/2", "b l/2", bare brackets) are never real
        # equations — honest fallback instead of fake <m:f>. Single letters
        # stay allowed ("a/b" is a valid test fixture): only hat-soup,
        # multi-char litter and bare fences are debris here.
        if _is_debris_fraction_side(
            node.get("numerator")
        ) or _is_debris_fraction_side(node.get("denominator")):
            raise UnsupportedConstruct("debris fraction is not an equation")
        # Zero denominators (pi/0 from limits misread as a fraction) are
        # division-by-zero hallucinations - honest fallback, never OMML.
        den_texts = [t for t in _bound_texts(node.get("denominator"), []) if t.strip()]
        if den_texts and _is_zero_denominator_text(
            "".join(re.sub(r"\s+", "", t) for t in den_texts)
        ):
            raise UnsupportedConstruct("zero denominator is not an equation")
        # Garbage sides (fence-PUA/hat artifacts, doubled-letter stutter)
        # are extraction debris - never OMML.
        for _side in (node.get("numerator"), node.get("denominator")):
            for _t in _bound_texts(_side, []):
                if any(_ch in _GARBAGE_ARTIFACT_CHARS for _ch in _t):
                    raise UnsupportedConstruct("garbage fraction side is not an equation")
                if _DOUBLED_LETTER_RE.search(_t):
                    raise UnsupportedConstruct("garbage fraction side is not an equation")
        f = _el("f")
        num = ET.SubElement(f, f"{{{MATH_NS}}}num")
        for e in _content(node["numerator"]):
            num.append(e)
        den = ET.SubElement(f, f"{{{MATH_NS}}}den")
        for e in _content(node["denominator"]):
            den.append(e)
        return f
    if kind == "superscript":
        s = _el("sSup")
        e = ET.SubElement(s, f"{{{MATH_NS}}}e")
        for c in _content(node["base"]):
            e.append(c)
        sup = ET.SubElement(s, f"{{{MATH_NS}}}sup")
        for c in _content(node["script"]):
            sup.append(c)
        return s
    if kind == "subscript":
        s = _el("sSub")
        e = ET.SubElement(s, f"{{{MATH_NS}}}e")
        for c in _content(node["base"]):
            e.append(c)
        sub = ET.SubElement(s, f"{{{MATH_NS}}}sub")
        for c in _content(node["script"]):
            sub.append(c)
        return s
    if kind == "root":
        r = _el("rad")
        if "degree" in node:
            deg = ET.SubElement(r, f"{{{MATH_NS}}}deg")
            for c in _content(node["degree"]):
                deg.append(c)
        e = ET.SubElement(r, f"{{{MATH_NS}}}e")
        for c in _content(node["radicand"]):
            e.append(c)
        return r
    if kind == "function":
        fn = _el("func")
        name = ET.SubElement(fn, f"{{{MATH_NS}}}fName")
        name.append(_run(str(node.get("name", ""))))
        args = node.get("arguments", [])
        if not args:
            # A bare name ("sin" with no call) is not a function call:
            # emitting <m:func> with an empty <m:e/> is malformed OMML
            # Word renders as a broken box. Return the name as a run.
            return _run(str(node.get("name", "")))
        e = ET.SubElement(fn, f"{{{MATH_NS}}}e")
        for arg in args:
            for c in _content(arg):
                e.append(c)
        return fn
    if kind == "matrix":
        rows = node.get("rows", [])
        widths = {len(r) for r in rows}
        if len(widths) > 1:
            raise UnsupportedConstruct("ragged matrix")
        if not rows or max(widths or [0]) == 0:
            raise UnsupportedConstruct("empty matrix")
        # Debris grids ("b l" litter, ">H", "R S/V...") are not equations:
        # every cell fence/hat litter means honest text fallback.
        flat_cells = [c for r in rows for c in r]
        if flat_cells and all(_is_debris_bound(c) for c in flat_cells):
            raise UnsupportedConstruct("debris matrix is not an equation")
        m = _el("m")
        mpr = ET.SubElement(m, f"{{{MATH_NS}}}mPr")
        _sub(mpr, 'count', val=str(max(widths or [0])))
        for row_cells in rows:
            mr = ET.SubElement(m, f"{{{MATH_NS}}}mr")
            for cell in row_cells:
                e = ET.SubElement(mr, f"{{{MATH_NS}}}e")
                for c in _content(cell):
                    e.append(c)
        return m
    if kind == "fence":
        d = _el("d")
        dpr = ET.SubElement(d, f"{{{MATH_NS}}}dPr")
        _sub(dpr, 'begChr', val=str(node.get("left", "(")))
        _sub(dpr, 'endChr', val=str(node.get("right", ")")))
        e = ET.SubElement(d, f"{{{MATH_NS}}}e")
        for c in _content(node["child"]):
            e.append(c)
        return d
    if kind == "accent":
        accent_kind = str(node.get("kind", ""))
        if accent_kind not in ACCENT_CHARS:
            raise UnsupportedConstruct(f"unsupported accent: {accent_kind!r}")
        a = _el("acc")
        accpr = ET.SubElement(a, f"{{{MATH_NS}}}accPr")
        _sub(accpr, 'chr', val=ACCENT_CHARS[accent_kind])
        e = ET.SubElement(a, f"{{{MATH_NS}}}e")
        for c in _content(node["child"]):
            e.append(c)
        return a
    if kind == "limit":
        return _nary_or_stacked(node["base"], node.get("lower"), node.get("upper"))
    if kind == "underover":
        return _stacked(node["base"], node.get("under"), node.get("over"))
    if kind == "cases":
        arr = _el("eqArr")
        for case in node.get("cases", []):
            e = ET.SubElement(arr, f"{{{MATH_NS}}}e")
            for c in _content(case.get("expression", {"type": "text", "value": ""})):
                e.append(c)
            cond = case.get("condition")
            if cond:
                e.append(_run("  "))
                for c in _content(cond):
                    e.append(c)
        return arr
    raise UnsupportedConstruct(f"unhandled node type: {kind!r}")


class _RowGroup(Exception):
    """Internal: row children expand inline at the parent level."""

    def __init__(self, elements: list[ET.Element]):
        super().__init__("row group")
        self.elements = elements


def _render_into(parent: ET.Element, node: dict) -> None:
    try:
        parent.append(render_node(node))
    except _RowGroup as group:
        for el in group.elements:
            parent.append(el)


#: Text values that are bracket litter / hat-soup, never real bounds or
#: cells ("^h", "b l", ">H", "R S"). Rendering them as OMML would mint a
#: fake equation — the caller must fall back to honest text instead.
_DEBRIS_TEXTS = frozenset({
    "", "^", "_", "h", "^h", "b", "l", "b l",
    "[", "]", "(", ")", "{", "}", "⎛", "⎜", "⎝", "⎞", "⎟", "⎠",
    ">H", "R", "S", "V", "W", "T", "X",
})


#: Narrow debris for fraction sides: hat-soup, "b l" litter and bare
#: fences. Single letters ("a", "b", "x") stay valid variables so the
#: "a/b" fixture keeps rendering <m:f>.
_FRACTION_SIDE_DEBRIS = frozenset({
    "", "^", "_", "^h", "b l",
    "[", "]", "(", ")", "{", "}", "⎛", "⎜", "⎝", "⎞", "⎟", "⎠",
    ">H",
})


#: Exact-zero denominator ("0", "(0)", "0.0"): a fraction over zero is a
#: division-by-zero hallucination (limits misread as a fraction) - never
#: an equation. The caller falls back to honest text instead of fake OMML.
_ZERO_DEN_RE = re.compile(r"^[\u2212\u2013\u2014-]?0+(\.0+)?$")

#: Extraction-artifact glyphs that are never genuine fraction content
#: (extensible-bracket PUA pieces, hat-soup modifiers).
_GARBAGE_ARTIFACT_CHARS = frozenset("\u239b\u239c\u239d\u239e\u239f\u23a0\u02c6\u02c7\u02d8\u02d9")

#: Doubled letters ("1yy", "qqssss") are extraction stutter, never math.
#: Digits are excluded ("11" is real).
_DOUBLED_LETTER_RE = re.compile(r"([A-Za-z])\1")


def _is_zero_denominator_text(value: str) -> bool:
    core = re.sub(r"[\s\(\)\[\]\{\}.,;:!?]+", "", value or "")
    return bool(core and _ZERO_DEN_RE.match(core))


def _is_debris_fraction_side(node: dict | None) -> bool:
    if node is None:
        return False
    texts = [t for t in _bound_texts(node, []) if t]
    if not texts:
        return True
    joined = " ".join(texts).strip()
    if joined in _FRACTION_SIDE_DEBRIS:
        return True
    if all(t in _FRACTION_SIDE_DEBRIS for t in texts):
        return True
    return False


def _bound_texts(node: dict | None, out: list[str]) -> list[str]:
    if node is None:
        return out
    if isinstance(node, dict):
        if node.get("type") in ("text", "operator"):
            out.append(str(node.get("value", node.get("symbol", ""))).strip())
        for value in node.values():
            if isinstance(value, (dict, list)):
                _bound_texts(value, out)
    elif isinstance(node, list):
        for value in node:
            _bound_texts(value, out)
    return out


def _is_debris_bound(node: dict | None) -> bool:
    if node is None:
        return False
    texts = [t for t in _bound_texts(node, []) if t]
    if not texts:
        return True
    joined = " ".join(texts).strip()
    if joined in _DEBRIS_TEXTS:
        return True
    # Every fragment fence litter ("[ ]", "b l", "^ h").
    if all(t in _DEBRIS_TEXTS for t in texts):
        return True
    return False


def _nary_or_stacked(base: dict, lower: dict | None, upper: dict | None) -> ET.Element:
    if _is_debris_bound(lower) or _is_debris_bound(upper):
        raise UnsupportedConstruct("debris bound is not an equation")
    base_text = None
    if base.get("type") == "text":
        base_text = base.get("value")
    elif base.get("type") == "operator":
        base_text = base.get("symbol")
    if base_text in NARY_CHARS:
        n = _el("nary")
        pr = ET.SubElement(n, f"{{{MATH_NS}}}naryPr")
        _sub(pr, 'chr', val=NARY_CHARS[base_text])
        _sub(pr, 'limLoc', val="subSup")
        _sub(pr, 'supHide', val="0")
        _sub(pr, 'subHide', val="0")
        if lower is not None:
            sub = ET.SubElement(n, f"{{{MATH_NS}}}sub")
            _render_into(sub, lower)
        if upper is not None:
            sup = ET.SubElement(n, f"{{{MATH_NS}}}sup")
            _render_into(sup, upper)
        e = ET.SubElement(n, f"{{{MATH_NS}}}e")
        e.append(_run(base_text))
        return n
    return _stacked(base, lower, upper)


def _stacked(base: dict, under: dict | None, over: dict | None) -> ET.Element:
    inner: ET.Element | None = None
    container: ET.Element | None = None
    if under is not None:
        low = _el("limLow")
        e = ET.SubElement(low, f"{{{MATH_NS}}}e")
        _render_into(e, base)
        lim = ET.SubElement(low, f"{{{MATH_NS}}}lim")
        _render_into(lim, under)
        inner = low
    if over is not None:
        upp = _el("limUpp")
        e = ET.SubElement(upp, f"{{{MATH_NS}}}e")
        if inner is not None:
            e.append(inner)
        else:
            _render_into(e, base)
        lim = ET.SubElement(upp, f"{{{MATH_NS}}}lim")
        _render_into(lim, over)
        container = upp
    if container is not None:
        return container
    if inner is not None:
        return inner
    fallback = _el("e")
    _render_into(fallback, base)
    return fallback


def render_omath(mathir_doc: dict, *, numbered: str | None = None) -> str:
    """Render a MathIR document to a standalone <m:oMathPara> XML string."""
    root = mathir_doc.get("root", {"type": "text", "value": ""})
    para = _el("oMathPara")
    omath = ET.SubElement(para, f"{{{MATH_NS}}}oMath")
    _render_into(omath, root)
    xml = ET.tostring(para, encoding="unicode")
    if numbered:
        # Equation numbers render as adjacent (non-math) text in the paragraph,
        # linked by proximity — full tab-stop alignment lands with layout work.
        xml += f"<!--eqnum:{sanitize_xml_text(numbered)}-->"
    return xml
