"""DocumentModel → .docx builder (§16). python-docx owns the package;
OMML equations inject as native oMath XML. Tables become native Word
tables; figures embed from PNG bytes (Phase 7 extracts real assets —
here the caller supplies bytes, e.g. fixtures or cropped renders).
"""
from __future__ import annotations

import base64
import io

from docx import Document
from docx.oxml import parse_xml
from docx.shared import Emu, Inches, Pt

from .omml import UnsupportedConstruct, render_node, sanitize_xml_text

#: Relationship type suffix for image parts in document.xml.rels.
_IMAGE_REL_SUFFIX = "relationships/image"


def _reconcile_figure_drawings(docx_bytes: bytes, report: dict) -> int:
    """Count drawings without a grounded image rel+media target.

    Every <w:drawing> must resolve r:embed → rel → media file. A drawing
    whose embed has no relationship or whose target is absent from the
    package is a phantom (big2: 129 drawings, 128 media, missing 0): it
    renders as a broken frame in Word. Each ungrounded drawing increments
    figure_missing so the report never claims a clean embed. Returns the
    ungrounded count; never raises.
    """
    import re
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
            names = set(z.namelist())
            try:
                xml = z.read("word/document.xml").decode("utf-8")
            except KeyError:
                return 0
            try:
                rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
            except KeyError:
                rels = ""
    except Exception:
        return 0
    try:
        drawings = xml.count("<w:drawing")
        embeds = re.findall(r'r:embed="([^"]+)"', xml)
        rel_targets: dict[str, str] = {}
        for match in re.finditer(
            r'<Relationship[^>]*?Id="([^"]+)"[^>]*?Target="([^"]+)"[^>]*?/>', rels
        ):
            rid, target = match.group(1), match.group(2)
            # Only image relationships ground a drawing; keep all then
            # verify type below via a second pass for robustness.
            rel_targets[rid] = target
        image_ids: set[str] = set()
        for match in re.finditer(
            r'<Relationship[^>]*?Id="([^"]+)"[^>]*?Type="[^"]*image[^"]*"[^>]*?/>',
            rels,
            re.IGNORECASE,
        ):
            image_ids.add(match.group(1))
        # Fallback when Type ordering differs: any rel whose target looks
        # like an image still grounds its drawing.
        for rid, target in rel_targets.items():
            low = target.lower()
            if low.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".emf")):
                image_ids.add(rid)
        ungrounded = 0
        for rid in embeds:
            target = rel_targets.get(rid)
            if target is None or rid not in image_ids:
                ungrounded += 1
                continue
            norm = target if target.startswith("word/") else "word/" + target.lstrip("/")
            if norm not in names and target not in names:
                ungrounded += 1
        # Drawings with no embed at all (shape frames) are phantoms too.
        if drawings > len(embeds):
            ungrounded += drawings - len(embeds)
        if ungrounded > 0:
            try:
                report["figure_missing"] = int(report.get("figure_missing", 0)) + ungrounded
            except Exception:
                pass
        return ungrounded
    except Exception:
        return 0


def _append_omath(paragraph, mathir_doc: dict) -> None:
    """Append native editable equation runs to a (blank) paragraph."""
    import xml.etree.ElementTree as ET

    from . import omml as omml_module

    root = mathir_doc.get("root", {"type": "text", "value": ""})
    try:
        holder = omml_module._el("oMath")
        omml_module._render_into(holder, root)
    except UnsupportedConstruct:
        raise
    inner = "".join(ET.tostring(child, encoding="unicode") for child in holder)
    xml = f'<m:oMath xmlns:m="{omml_module.MATH_NS}">{inner}</m:oMath>'
    paragraph._p.append(parse_xml(xml))


def _append_inline_math(paragraph, entries, report: dict) -> None:
    """Render derived equations as inline <m:oMath> runs in ONE paragraph.

    The paragraph already holds the host question text, so every oMath
    emitted here is inline (its parent <w:p> also carries <w:t> runs) —
    never a detached OMML-only paragraph. Render failures fall back to the
    host text (already present) and count honestly.
    """
    for entry in entries or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("mathir"), dict):
            report["equation_fallbacks"] += 1
            continue
        try:
            _append_omath(paragraph, entry["mathir"])
            report["equations"] += 1
        except UnsupportedConstruct:
            report["equation_fallbacks"] += 1


def _carry_inline_fallbacks(block: dict, report: dict) -> None:
    """Count enrich-stage rejections honestly (host text was preserved)."""
    try:
        carried = int(block.get("inlineFallbacks", 0) or 0)
    except (TypeError, ValueError):
        carried = 0
    if carried > 0:
        try:
            report["equation_fallbacks"] = int(report.get("equation_fallbacks", 0)) + carried
        except Exception:
            pass


def _append_segments(paragraph, segments, report: dict) -> None:
    """Emit ADR-2 ordered segments inside ONE <w:p>: w:r for text,
    <m:oMath> for math. The host content/inlineMath is NOT emitted again
    (segments are the single covering of the paragraph text).

    A math segment with valid MathIR is emitted as <m:oMath> ONLY — never
    a duplicate plain-text run — so the equation is covered exactly once
    and G8 (token duplication) stays bounded. A math segment that fails to
    render (UnsupportedConstruct) or lacks valid MathIR falls back to its
    plain text and counts as a fallback — never a lost span, never a wrong
    equation.
    """
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        kind = seg.get("kind")
        text = str(seg.get("text", ""))
        if kind == "math" and isinstance(seg.get("mathir"), dict):
            try:
                _append_omath(paragraph, seg["mathir"])
                report["equations"] += 1
            except UnsupportedConstruct:
                paragraph.add_run(sanitize_xml_text(text))
                report["equation_fallbacks"] += 1
        else:
            # "text", unknown kinds and math-without-MathIR all keep the
            # source text: plain text is always safe, a guessed equation
            # is not.
            paragraph.add_run(sanitize_xml_text(text))


def _apply_cell_borders(cell, spec: dict) -> None:
    """Per-cell borders from the source ruling lines.

    Only the sides the source actually draws get a line; the rest are
    explicitly ``nil`` so a Word style cannot re-box the cell.
    """
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    try:
        tcPr = cell._tc.get_or_add_tcPr()
    except Exception:
        return
    for el in tcPr.findall(qn("w:tcBorders")):
        tcPr.remove(el)
    borders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{side}")
        if spec.get(side):
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "auto")
        else:
            el.set(qn("w:val"), "nil")
        borders.append(el)
    try:
        tcPr.insert_element_before(
            borders,
            "w:shd", "w:noWrap", "w:tcMar", "w:textDirection",
            "w:tcFitText", "w:vAlign", "w:hideMark",
        )
    except Exception:
        tcPr.append(borders)


def _mark_repeat_header(row) -> None:
    """Mark a table row as a repeating header row (``w:tblHeader``)."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    try:
        trPr = row._tr.get_or_add_trPr()
    except Exception:
        return
    for el in trPr.findall(qn("w:tblHeader")):
        trPr.remove(el)
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    try:
        trPr.insert_element_before(
            header, "w:tblCellSpacing", "w:jc", "w:hidden",
            "w:ins", "w:del", "w:trPrChange",
        )
    except Exception:
        trPr.append(header)


def _set_column_widths(doc: Document, table, widths) -> None:
    """Give the table the source's column proportions.

    Word's autofit gives every column the same width, which squeezes a
    wide text column and inflates the page count. The ruled table knows
    its own column boundaries, so the widths are taken from the source
    geometry (scaled down when the source table is wider than the page).
    """
    if not widths:
        return
    try:
        section = doc.sections[0]
        available = float(section.page_width) - float(section.left_margin) - float(section.right_margin)
        total = float(sum(widths))
        if total <= 0 or available <= 0:
            return
        scale = 1.0 if total <= available else available / total
        table.autofit = False
        for c, width in enumerate(widths):
            emu = Emu(int(float(width) * scale * 12700))
            try:
                if c < len(table.columns):
                    table.columns[c].width = emu
            except Exception:
                pass
            for r in range(len(table.rows)):
                try:
                    table.cell(r, c).width = emu
                except Exception:
                    pass
    except Exception:
        pass


def _fill_cell(cell, text: str, *, bold: bool = False, segments=None, report: dict | None = None) -> None:
    """Write a cell's text, one paragraph per source line.

    A reconstructed cell can hold several source lines (a merged header, a
    question with its options); each line becomes its own paragraph so the
    cell keeps the line structure of the page. When the enricher segmented
    a line (``segments``), the line is emitted as ordered segments (text
    runs + <m:oMath>) instead of plain text — the mathematics inside a
    table cell stays editable, exactly like body text.
    """
    lines = str(text).split("\n") if text else [""]
    try:
        cell._tc.clear_content()
    except Exception:
        cell.text = ""
    for i, line in enumerate(lines):
        paragraph = cell.paragraphs[0] if i == 0 and cell.paragraphs else cell.add_paragraph()
        # The source's cell lines are tightly set: no paragraph spacing, so
        # a long cell keeps the page's own line rhythm instead of growing
        # by a blank line per row.
        try:
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = 1.0
        except Exception:
            pass
        segs = None
        if segments and i < len(segments):
            segs = segments[i]
        if segs and report is not None:
            _append_segments(paragraph, segs, report)
            continue
        run = paragraph.add_run(sanitize_xml_text(line))
        if bold:
            run.bold = True


def _add_caption(doc: Document, text: str) -> None:
    cap = doc.add_paragraph(style="Caption")
    cap.add_run(sanitize_xml_text(str(text)))


def _add_fallback_image(doc: Document, spec: dict, bbox=None) -> None:
    """A table whose structure could not be trusted ships as a crop.

    The region is rendered from the source PDF by the pipeline and carried
    in the block as base64; a broken structure is never shipped as a
    half-empty grid.
    """
    data = None
    payload = spec.get("imageBase64")
    if payload:
        try:
            data = base64.b64decode(str(payload))
        except Exception:
            data = None
    if data:
        try:
            width_pt = 396.0
            if bbox and len(bbox) == 4:
                width_pt = max(10.0, float(bbox[2]) - float(bbox[0]))
            doc.add_picture(io.BytesIO(data), width=Inches(min(5.5, max(1.0, width_pt / 72.0))))
            return
        except Exception:
            pass
    placeholder = doc.add_paragraph()
    placeholder.add_run("[Table image missing: invalid structure]")


def _add_table(
    doc: Document,
    spec: dict,
    *,
    figures: dict[str, bytes] | None = None,
    bbox=None,
    report: dict | None = None,
) -> None:
    """Render one table as a native Word table.

    ``spec`` carries ``rows`` (the cell grid), optional ``spans`` (merged
    cells, as per-row column ranges), ``headerRows`` (rows that repeat as
    the table header), ``borders`` (per-cell edge map) and ``parseStatus``.
    Borders come from the source ruling lines — "Table Grid" is never
    applied blanket, because that boxes cells the source leaves open.
    """
    status = str(spec.get("parseStatus") or "ok")
    if status == "fallback_image":
        caption = spec.get("caption")
        if caption and spec.get("captionPosition") == "above":
            _add_caption(doc, caption)
        _add_fallback_image(doc, spec, bbox)
        if caption and spec.get("captionPosition") != "above":
            _add_caption(doc, caption)
        return
    rows = spec.get("rows") or []
    if not rows:
        return
    caption = spec.get("caption")
    caption_above = bool(caption) and spec.get("captionPosition") == "above"
    if caption_above:
        _add_caption(doc, caption)
    ncols = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=ncols)
    borders = spec.get("borders") or []
    if borders:
        # Ruled table: every edge is drawn from the source rules. "Table
        # Grid" is never applied blanket — that boxes cells the source
        # leaves open.
        try:
            table.style = None
        except Exception:
            pass
    else:
        # No ruling evidence (a table found by word geometry only): keep the
        # grid visible so the table survives the render.
        try:
            table.style = "Table Grid"
        except Exception:
            pass
    spans = spec.get("spans") or []
    _set_column_widths(doc, table, spec.get("columnWidths") or [])
    for r, row_spans in enumerate(spans):
        if r >= len(rows):
            break
        for pair in row_spans or []:
            try:
                c0, c1 = int(pair[0]), int(pair[1])
            except (TypeError, ValueError, IndexError):
                continue
            if c1 <= c0 or c1 >= ncols:
                continue
            try:
                table.cell(r, c0).merge(table.cell(r, c1))
            except Exception:
                pass
    header_rows = set()
    for i in spec.get("headerRows") or []:
        try:
            header_rows.add(int(i))
        except (TypeError, ValueError):
            continue
    for r, row in enumerate(rows):
        row_spans = spans[r] if r < len(spans) else None
        cell_segments = (spec.get("cellSegments") or [])[r] if r < len(spec.get("cellSegments") or []) else None
        if row_spans:
            for si, pair in enumerate(row_spans):
                try:
                    c0 = int(pair[0])
                except (TypeError, ValueError, IndexError):
                    continue
                cell = table.cell(r, c0)
                text = str(row[c0]) if c0 < len(row) else ""
                segs = cell_segments[c0] if cell_segments and c0 < len(cell_segments) else None
                _fill_cell(cell, text, bold=(r in header_rows), segments=segs, report=report)
                try:
                    edge = borders[r][si]
                except (IndexError, TypeError):
                    edge = None
                if edge:
                    _apply_cell_borders(cell, edge)
            continue
        for c in range(ncols):
            cell = table.cell(r, c)
            text = str(row[c]) if c < len(row) else ""
            segs = cell_segments[c] if cell_segments and c < len(cell_segments) else None
            _fill_cell(cell, text, bold=(r in header_rows), segments=segs, report=report)
    for r in sorted(header_rows):
        try:
            _mark_repeat_header(table.rows[r])
        except Exception:
            pass
    if caption and not caption_above:
        _add_caption(doc, caption)


def build_docx(model: dict, *, figures: dict[str, bytes] | None = None) -> bytes:
    """Render a partial DocumentModel to .docx bytes.

    figures: assetId → PNG bytes. Equation blocks without valid MathIR fall
    back to plain text (never a wrong equation); the miss is recorded in the
    returned report.
    """
    figures = figures or {}
    doc = Document()
    styles = doc.styles["Normal"]
    styles.font.size = Pt(11)

    report = {"equations": 0, "equation_fallbacks": 0, "tables": 0, "figures": 0, "figure_missing": 0}
    pages = model.get("document", {}).get("pages", [])
    for page in pages:
        for block in page.get("blocks", []):
            kind = block.get("type")
            if kind == "heading":
                segs = block.get("segments")
                if isinstance(segs, list) and len(segs) > 0:
                    # ADR-2: heading text is covered exactly once by ordered
                    # segments (text runs + <m:oMath>), same contract as
                    # paragraphs — content is never emitted a second time.
                    h = doc.add_heading("", level=1)
                    _append_segments(h, segs, report)
                else:
                    doc.add_heading(sanitize_xml_text(str(block.get("content", ""))), level=1)
            elif kind == "equation" and isinstance(block.get("mathir"), dict):
                p = doc.add_paragraph()
                # Item/option/section labels ("(1)", "(D)", "Section-D") are
                # stripped into metadata for scoring, never equation content —
                # but they must still reach the DOCX as text. Without this,
                # equation promotion silently consumes them: the OMML holds
                # only the math core, the paragraph holds no w:t, and the
                # whole item (quebank Section-D (1)-(4)) vanishes from text
                # search with no placeholder. Labels ride as a leading text
                # run; OMML emission below is untouched.
                try:
                    _labels = []
                    for _key in ("sectionTag", "itemLabel", "optionLabel"):
                        _v = block.get(_key)
                        if isinstance(_v, str) and _v.strip():
                            _labels.append(_v.strip())
                    if _labels:
                        p.add_run(sanitize_xml_text(" ".join(_labels) + " "))
                except Exception:
                    pass
                # Derived equations (extra derivedFrom) must never ship as
                # empty OMML-only paragraphs detached from their question:
                # the surface text rides along so the oMath parent holds w:t.
                try:
                    if block.get("derivedFrom") and str(block.get("content", "")).strip():
                        p.add_run(sanitize_xml_text(str(block.get("content", "")) + " "))
                except Exception:
                    pass
                try:
                    _append_omath(p, block["mathir"])
                    report["equations"] += 1
                except UnsupportedConstruct:
                    p.add_run(sanitize_xml_text(str(block.get("content", ""))))
                    report["equation_fallbacks"] += 1
                _carry_inline_fallbacks(block, report)
                try:
                    _append_inline_math(p, block.get("inlineMath"), report)
                except Exception:
                    pass
                number = block.get("number")
                if number:
                    p.add_run(sanitize_xml_text(f"   ({number})"))
            elif kind == "table" and isinstance(block.get("table"), dict):
                _add_table(doc, block["table"], figures=figures, bbox=block.get("bbox"), report=report)
                report["tables"] += 1
            elif kind == "figure":
                asset = block.get("assetId")
                data = figures.get(asset) if asset else None
                if data is None and block.get("imageBase64"):
                    try:
                        data = base64.b64decode(str(block["imageBase64"]))
                    except Exception:
                        data = None
                embedded = False
                if data:
                    try:
                        bbox = block.get("bbox") or [0, 0, 396, 200]
                        try:
                            w_pt = max(10.0, float(bbox[2]) - float(bbox[0]))
                        except (TypeError, ValueError, IndexError):
                            w_pt = 396.0
                        w_in = min(5.5, max(1.0, w_pt / 72.0))
                        doc.add_picture(io.BytesIO(data), width=Inches(w_in))
                        report["figures"] += 1
                        embedded = True
                    except Exception:
                        embedded = False
                        data = None
                if not embedded:
                    report["figure_missing"] += 1
                    context = (
                        block.get("caption")
                        or block.get("content")
                        or asset
                        or block.get("id")
                        or f"page {page.get('pageNumber', '?')}"
                    )
                    placeholder = doc.add_paragraph()
                    placeholder.add_run(
                        sanitize_xml_text(f"[Figure missing: {context}]")
                    )
                caption = block.get("caption")
                if caption:
                    cap = doc.add_paragraph(style="Caption")
                    cap.add_run(sanitize_xml_text(str(caption)))
            elif kind == "caption":
                cap = doc.add_paragraph(style="Caption")
                cap.add_run(sanitize_xml_text(str(block.get("content", ""))))
            else:
                content = sanitize_xml_text(str(block.get("content", "")))
                segs = block.get("segments")
                has_segments = isinstance(segs, list) and len(segs) > 0
                inl = block.get("inlineMath")
                has_inline = isinstance(inl, list) and len(inl) > 0
                try:
                    carried = int(block.get("inlineFallbacks", 0) or 0)
                except (TypeError, ValueError):
                    carried = 0
                if has_segments:
                    # ADR-2: segments cover the paragraph text exactly once
                    # and take precedence over content/inlineMath — the
                    # legacy branches below are skipped for this block.
                    p = doc.add_paragraph()
                    _append_segments(p, segs, report)
                    if carried:
                        try:
                            report["equation_fallbacks"] = int(
                                report.get("equation_fallbacks", 0)
                            ) + carried
                        except Exception:
                            pass
                elif has_inline or carried:
                    # Host question paragraph: full text plus each derived
                    # equation as an inline <m:oMath> run in the same <w:p>.
                    p = doc.add_paragraph()
                    if content.strip():
                        p.add_run(content)
                    else:
                        # Host text empty (should not happen): entry surfaces
                        # keep the paragraph non-empty and searchable.
                        try:
                            surf = " ".join(
                                str(e.get("text", "")) for e in inl
                                if isinstance(e, dict)
                            ).strip()
                        except Exception:
                            surf = ""
                        if surf:
                            p.add_run(sanitize_xml_text(surf))
                    if carried:
                        try:
                            report["equation_fallbacks"] = int(
                                report.get("equation_fallbacks", 0)
                            ) + carried
                        except Exception:
                            pass
                    _append_inline_math(p, inl if has_inline else [], report)
                elif content.strip():
                    doc.add_paragraph(content)

    buf = io.BytesIO()
    doc.save(buf)
    docx_bytes = buf.getvalue()
    # Reconcile drawings↔rels↔media: phantoms (drawing without a grounded
    # image) must surface as figure_missing, never a silent clean embed.
    _reconcile_figure_drawings(docx_bytes, report)
    return docx_bytes, report
