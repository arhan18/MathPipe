"""Embedded-image region detection + raster extraction.

figure_regions() finds image bboxes via pdfplumber (unchanged contract).
extract_figure_assets() renders each bbox to PNG bytes via pypdfium2 +
Pillow — only actual PDF raster content, never synthesized.
Failures return {} / skip that figure (caller emits a placeholder).

Glyph-filter (§7.3): sub-figure raster scraps (single-glyph XObjects
rendered as 50–95px crops) are rejected by crop size + byte size unless
anchored to a figure caption. Regions overlapping equation blocks are
never rendered as figures — equation fragments must stay text/OMML.
"""

from __future__ import annotations

import io
import re

import pdfplumber

#: Render resolution for cropped figures (dpi). 150 balances legibility
#: against .docx size; scale = dpi / 72.
_FIGURE_DPI = 150

#: Rects smaller than this (points) are skipped — degenerate pdfplumber
#: entries, not real figures.
_MIN_RECT_PT = 4.0

#: Glyph-crop gate: crops smaller than this in BOTH dimensions AND lighter
#: than _MIN_CROP_BYTES are single-glyph scraps (ICSE: 51–95px, <2KB),
#: never real diagrams. Real SQP diagrams measure 300–860px per side.
_MIN_CROP_PX = 150
_MIN_CROP_BYTES = 4096

#: Thin inline strips (equation fragments sliced as images, e.g. 158×47px
#: at 5KB) pass the glyph gate on width alone. A real diagram is never a
#: 60px-tall ribbon: min-dimension below this with a small payload is an
#: inline fragment, not a figure.
_MIN_STRIP_PX = 60
_MIN_STRIP_BYTES = 8192

#: Caption anchor: a small crop beside a genuine caption is a legitimate
#: thumbnail (kept); the same crop adrift in body text is a glyph scrap
#: (rejected). Only numbered Fig./Figure captions anchor — a question stem
#: mentioning "the given diagram" is a reference, not a caption, and must
#: never rescue glyph scraps (ICSE: 21/30 scraps survived on such mentions).
#: Proximity gate in PDF points.
_CAPTION_STRONG_RE = re.compile(r"\bfig\.?\s*\d+|\bfigure\s*\d+", re.IGNORECASE)
_CAPTION_WEAK_RE = re.compile(
    r"\b(diagram|graph|histogram|sketch)\s*\d+", re.IGNORECASE
)
_CAPTION_MAX_CHARS_STRONG = 200
_CAPTION_MAX_CHARS_WEAK = 120
_CAPTION_PROXIMITY_PT = 80.0

#: Overlap padding (points) when testing figure↔equation intersection.
_EQUATION_OVERLAP_PAD_PT = 2.0


def figure_asset_id(page_number: int, index: int) -> str:
    """Stable asset id shared by the model, the extractor and the builder."""
    return f"fig-p{page_number}-{index}"


def table_fallback_asset_id(page_number: int, index: int) -> str:
    """Stable asset id for a table region shipped as an image crop."""
    return f"tblfall-p{page_number}-{index}"


def _boxes_overlap(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    pad: float = 0.0,
) -> bool:
    """True when two top-origin point rects intersect (with padding)."""
    try:
        ax0, atop, ax1, abot = (float(v) for v in a)
        bx0, btop, bx1, bbot = (float(v) for v in b)
    except (TypeError, ValueError):
        return False
    return (
        ax0 - pad < bx1
        and ax1 + pad > bx0
        and atop - pad < bbot
        and abot + pad > btop
    )


def _is_caption_anchored(
    page_number: int,
    rect: tuple[float, float, float, float],
    caption_boxes: dict[int, list[tuple[float, float, float, float]]] | None,
) -> bool:
    """True when a caption box sits within proximity of the figure rect."""
    if not caption_boxes:
        return False
    try:
        x0, top, x1, bottom = (float(v) for v in rect)
    except (TypeError, ValueError):
        return False
    for box in caption_boxes.get(page_number, []):
        try:
            cx0, ctop, cx1, cbot = (float(v) for v in box)
        except (TypeError, ValueError):
            continue
        horizontal_overlap = x0 < cx1 and x1 > cx0
        vertical_gap = max(0.0, ctop - bottom, top - cbot)
        if horizontal_overlap and vertical_gap <= _CAPTION_PROXIMITY_PT:
            return True
        # Caption directly beside a narrow crop: allow side proximity too.
        if vertical_gap <= _CAPTION_PROXIMITY_PT and (
            abs(x0 - cx1) <= _CAPTION_PROXIMITY_PT or abs(cx0 - x1) <= _CAPTION_PROXIMITY_PT
        ):
            return True
    return False


def _is_glyph_scrap(crop_w: int, crop_h: int, nbytes: int, *, anchored: bool) -> bool:
    """True when a rendered crop is a glyph scrap, not a diagram."""
    if anchored:
        return False
    if crop_w < _MIN_CROP_PX and crop_h < _MIN_CROP_PX and nbytes < _MIN_CROP_BYTES:
        return True
    if min(crop_w, crop_h) < _MIN_STRIP_PX and nbytes < _MIN_STRIP_BYTES:
        return True
    return False


def caption_boxes_from_blocks(
    blocks_by_page: dict[int, list],
) -> dict[int, list[tuple[float, float, float, float]]]:
    """Collect caption-like block bboxes per page for anchoring.

    Only genuine captions anchor: numbered Fig./Figure labels (strong) or
    short numbered Diagram/Graph/Histogram labels (weak). A body paragraph
    that merely mentions "the given diagram" is a reference, never a
    caption. Pure helper — no I/O, never raises.
    """
    out: dict[int, list[tuple[float, float, float, float]]] = {}
    for page_number, blocks in (blocks_by_page or {}).items():
        for block in blocks:
            try:
                text = str(getattr(block, "text", "") or "").strip()
                bbox = getattr(block, "bbox", None)
            except Exception:
                continue
            if not text or not bbox or len(bbox) != 4:
                continue
            strong = (
                _CAPTION_STRONG_RE.search(text)
                and len(text) <= _CAPTION_MAX_CHARS_STRONG
            )
            weak = (
                not strong
                and _CAPTION_WEAK_RE.search(text)
                and len(text) <= _CAPTION_MAX_CHARS_WEAK
            )
            if not (strong or weak):
                continue
            try:
                out.setdefault(int(page_number), []).append(
                    (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
                )
            except (TypeError, ValueError):
                continue
    return out


def equation_boxes_from_blocks(
    blocks_by_page: dict[int, list],
) -> dict[int, list[tuple[float, float, float, float]]]:
    """Collect equation block bboxes per page for overlap suppression."""
    out: dict[int, list[tuple[float, float, float, float]]] = {}
    for page_number, blocks in (blocks_by_page or {}).items():
        for block in blocks:
            try:
                kind = getattr(block, "kind", "")
                bbox = getattr(block, "bbox", None)
            except Exception:
                continue
            if kind != "equation" or not bbox or len(bbox) != 4:
                continue
            try:
                out.setdefault(int(page_number), []).append(
                    (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
                )
            except (TypeError, ValueError):
                continue
    return out


def figure_regions(path: str) -> dict[int, list[tuple[float, float, float, float]]]:
    out: dict[int, list[tuple[float, float, float, float]]] = {}
    try:
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                try:
                    images = page.images or []
                except Exception:
                    images = []
                rects = []
                for img in images:
                    try:
                        rects.append((float(img["x0"]), float(img["top"]), float(img["x1"]), float(img["bottom"])))
                    except (KeyError, TypeError, ValueError):
                        continue
                if rects:
                    out[i] = rects
    except Exception:
        pass
    return out


def extract_figure_assets(
    path: str,
    regions: dict[int, list[tuple[float, float, float, float]]],
    *,
    dpi: int = _FIGURE_DPI,
    equation_boxes: dict[int, list[tuple[float, float, float, float]]] | None = None,
    caption_boxes: dict[int, list[tuple[float, float, float, float]]] | None = None,
    id_fn=None,
) -> dict[str, bytes]:
    """Render each region to PNG bytes (actual PDF raster, never invented).

    One render per page; each bbox is cropped from the page bitmap and
    saved as PNG via Pillow. Coordinates are pdfplumber top-origin points;
    the pypdfium2 bitmap shares the same top-origin layout, so scaling by
    dpi/72 aligns them. Any failure skips that figure (never raises).

    Glyph gate: crops under _MIN_CROP_PX in both dims AND under
    _MIN_CROP_BYTES (plus thin inline strips under _MIN_STRIP_PX /
    _MIN_STRIP_BYTES) are rejected as glyph scraps unless anchored to a
    figure caption. Regions overlapping equation blocks are never
    rendered — equation fragments must stay text/OMML, not images.
    """
    if not regions:
        return {}
    id_fn = id_fn or figure_asset_id
    try:
        import pypdfium2 as pdfium
    except Exception:
        return {}
    try:
        from PIL import Image  # noqa: F401  (ensures Pillow present)
    except Exception:
        return {}
    scale = max(1.0, float(dpi) / 72.0)
    assets: dict[str, bytes] = {}
    try:
        with pdfium.PdfDocument(path) as doc:
            for page_number, rects in regions.items():
                if not rects:
                    continue
                try:
                    page = doc[page_number - 1]
                except Exception:
                    continue
                try:
                    bitmap = page.render(scale=scale)
                    pil_page = bitmap.to_pil()
                except Exception:
                    continue
                try:
                    page_w, page_h = pil_page.size
                    for idx, rect in enumerate(rects):
                        try:
                            x0, top, x1, bottom = (float(v) for v in rect)
                        except (TypeError, ValueError):
                            continue
                        if x1 - x0 < _MIN_RECT_PT or bottom - top < _MIN_RECT_PT:
                            continue
                        # Equation-fragment suppression: a raster region that
                        # overlaps an equation block is an equation rendered
                        # as an image — never a figure. Skip before rendering.
                        if equation_boxes:
                            overlapped = any(
                                _boxes_overlap(
                                    (x0, top, x1, bottom), eq,
                                    pad=_EQUATION_OVERLAP_PAD_PT,
                                )
                                for eq in equation_boxes.get(page_number, [])
                            )
                            if overlapped:
                                continue
                        # Small padding so anti-aliased edges are not clipped.
                        pad = 2.0
                        bx0 = max(0, int((x0 - pad) * scale))
                        btop = max(0, int((top - pad) * scale))
                        bx1 = min(page_w, int((x1 + pad) * scale))
                        bbot = min(page_h, int((bottom + pad) * scale))
                        if bx1 - bx0 < 8 or bbot - btop < 8:
                            continue
                        crop = pil_page.crop((bx0, btop, bx1, bbot))
                        buf = io.BytesIO()
                        crop.save(buf, format="PNG")
                        blob = buf.getvalue()
                        if not blob:
                            continue
                        crop_w, crop_h = crop.size
                        anchored = _is_caption_anchored(page_number, (x0, top, x1, bottom), caption_boxes)
                        if _is_glyph_scrap(crop_w, crop_h, len(blob), anchored=anchored):
                            continue
                        assets[id_fn(page_number, idx)] = blob
                finally:
                    try:
                        page.close()
                    except Exception:
                        pass
    except Exception:
        pass
    return assets
