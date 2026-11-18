"""Stage 7 — partial DocumentModel emission (§10).

Phase 4 covers text structure: paragraphs, headings, reading order, page
geometry and figure-region stubs. Equation / table / asset extraction land
in Phases 5–7 and extend — never reshape — this contract.
"""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import asdict


SCHEMA_VERSION = "document-model/v0.1-partial"


def _stable_id(*parts: str) -> str:
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return h[:16]


def build_partial_model(
    *,
    source_name: str,
    classification: str,
    geometries: list,
    blocks_by_page: dict[int, list],
    figure_regions: dict[int, list],
    figure_assets: dict[str, bytes] | None = None,
) -> dict:
    from ..pipeline.figures import figure_asset_id

    assets_provided = figure_assets is not None
    assets = figure_assets or {}
    pages = []
    for g in geometries:
        blocks = []
        for b in blocks_by_page.get(g.page_number, []):
            entry = {
                "id": b.id,
                "type": b.kind,
                "bbox": b.bbox,
                "readingOrder": b.reading_order,
                "style": {"fontSize": b.size, "bold": b.bold},
                "content": b.text,
                "confidence": b.confidence,
                "provenance": {"source": "scaffold-0.1", "page": g.page_number},
            }
            entry.update(getattr(b, "extra", {}) or {})
            blocks.append(entry)
        # Figures interleave at their vertical position so the DOCX keeps
        # approximate reading order (previously they were appended last).
        fig_entries: list[dict] = []
        for i, (x0, top, x1, bottom) in enumerate(figure_regions.get(g.page_number, [])):
            asset_id = figure_asset_id(g.page_number, i)
            if assets_provided and asset_id not in assets:
                continue
            fig_block: dict = {
                "id": f"p{g.page_number}-fig{i}",
                "type": "figure",
                "bbox": [round(x0, 1), round(top, 1), round(x1, 1), round(bottom, 1)],
                "readingOrder": 0,
                "style": {},
                "assetId": asset_id,
                "confidence": 0.9 if asset_id in assets else 0.0,
                "provenance": {"source": "scaffold-0.1", "page": g.page_number},
            }
            blob = assets.get(asset_id)
            if blob:
                try:
                    fig_block["imageBase64"] = base64.b64encode(blob).decode("ascii")
                except Exception:
                    pass
            else:
                fig_block["pending"] = "figure-engine"
            fig_entries.append(fig_block)
        if fig_entries:
            fig_entries.sort(key=lambda b: b["bbox"][1])
            for fig in fig_entries:
                pos = 0
                while pos < len(blocks) and blocks[pos]["bbox"][1] <= fig["bbox"][1]:
                    pos += 1
                blocks.insert(pos, fig)
        # Renumber sequentially in stored order (figures included).
        for order, b in enumerate(blocks, start=1):
            b["readingOrder"] = order
        pages.append(
            {
                "pageNumber": g.page_number,
                "width": round(g.width, 1),
                "height": round(g.height, 1),
                "rotation": g.rotation,
                "blocks": blocks,
            }
        )
    model = {
        "schemaVersion": SCHEMA_VERSION,
        "document": {
            "id": _stable_id(source_name, str(len(pages))),
            "metadata": {
                "sourceName": source_name,
                "classification": classification,
                "pageCount": len(pages),
                "producer": "scaffold-0.1",
            },
            "pages": pages,
        },
    }
    return model


def dump_model(model: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False, indent=2, sort_keys=True)
