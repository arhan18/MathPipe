"""Canonical staged pipeline (§5.1 steps 1–17). Each stage: typed in/out,
no exceptions leak (failures become typed results), timing recorded.

Large documents process in bounded page chunks with durable checkpoints;
one bad page never kills the job (§60.6).
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field

from ..ingestion.validate import validate_pdf
from ..ingestion.classify import classify_pdf
from ..ingestion.geometry import page_geometry
from ..understanding.blocks import Block, segment_blocks
from ..understanding.reading_order import order_blocks
from ..understanding.text import extract_page_subset
from ..contract.document_model import build_partial_model
from ..mathengine.enrich import enrich_blocks
from . import chunks
from .chunks import DEFAULT_CHUNK_PAGES
from .figures import (
    caption_boxes_from_blocks,
    equation_boxes_from_blocks,
    extract_figure_assets,
    figure_regions,
    table_fallback_asset_id,
)

#: A job fails outright only when more than this share of pages fail.
PAGE_FAILURE_THRESHOLD = 0.5


@dataclass
class StageLog:
    stage: str
    duration_ms: int
    detail: str = ""


@dataclass
class PipelineResult:
    ok: bool
    error_code: str | None
    message: str
    model: dict | None = None
    stages: list[StageLog] = field(default_factory=list)
    verification: dict | None = None
    page_failures: dict = field(default_factory=dict)
    chunks_complete: int = 0
    chunks_total: int = 0


def _block_to_dict(block: Block) -> dict:
    return asdict(block)


def _block_from_dict(data: dict) -> Block:
    return Block(
        id=data["id"], kind=data["kind"], page_number=data["page_number"],
        bbox=data["bbox"], text=data["text"], size=data["size"], bold=data["bold"],
        confidence=data["confidence"], reading_order=data.get("reading_order", 0),
        extra=data.get("extra") or {},
    )


def _page_rules(
    path: str, page_numbers: list[int], figure_regions: dict[int, list] | None = None
) -> dict[int, list]:
    """Ruling geometry per page (pdfplumber rects/lines).

    The PDF's own ruling lines are the strongest table evidence: a bordered
    grid survives irregular columns and spanning headers that word geometry
    can never align. Read once per chunk; the detector itself is pure.
    """
    from ..understanding.tables import extract_rules

    out: dict[int, list] = {}
    try:
        import pdfplumber
    except Exception:
        return out
    figure_regions = figure_regions or {}
    try:
        with pdfplumber.open(path) as pdf:
            total = len(pdf.pages)
            for n in page_numbers:
                if n < 1 or n > total:
                    continue
                try:
                    out[n] = extract_rules(
                        pdf.pages[n - 1],
                        image_boxes=figure_regions.get(n),
                    )
                except Exception:
                    out[n] = []
    except Exception:
        return out
    return out


def _table_fallback_regions(blocks_by_page: dict[int, list]) -> dict[int, list]:
    """Regions of tables whose structure could not be trusted.

    A table whose rows disagree with its columns is shipped as an image
    crop of the source region instead of a broken grid.
    """
    out: dict[int, list] = {}
    for page_number, blocks in (blocks_by_page or {}).items():
        rects: list[tuple[float, float, float, float]] = []
        for block in blocks or []:
            extra = getattr(block, "extra", None)
            table = extra.get("table") if isinstance(extra, dict) else None
            if not isinstance(table, dict):
                continue
            if table.get("parseStatus") != "fallback_image":
                continue
            bbox = getattr(block, "bbox", None)
            if not bbox or len(bbox) != 4:
                continue
            try:
                rects.append((float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])))
            except (TypeError, ValueError):
                continue
            table["fallbackIndex"] = len(rects) - 1
        if rects:
            out[int(page_number)] = rects
    return out


def _attach_table_fallbacks(blocks_by_page: dict[int, list], assets: dict[str, bytes]) -> None:
    """Carry the rendered crop into the table block (base64, like figures)."""
    import base64

    for page_number, blocks in (blocks_by_page or {}).items():
        for block in blocks or []:
            extra = getattr(block, "extra", None)
            table = extra.get("table") if isinstance(extra, dict) else None
            if not isinstance(table, dict) or table.get("parseStatus") != "fallback_image":
                continue
            index = table.get("fallbackIndex")
            if index is None:
                continue
            blob = assets.get(table_fallback_asset_id(int(page_number), int(index)))
            if not blob:
                continue
            try:
                table["imageBase64"] = base64.b64encode(blob).decode("ascii")
            except Exception:
                pass


def _process_pages(
    path: str,
    page_numbers: list[int],
    page_widths: dict[int, float],
    figure_regions: dict[int, list] | None = None,
) -> tuple[dict[int, list], dict]:
    """Process one chunk's pages with per-page failure isolation."""
    blocks_by_page: dict[int, list] = {}
    failures: dict = {}
    rules_by_page = _page_rules(path, page_numbers, figure_regions)
    for page in extract_page_subset(path, page_numbers):
        try:
            blocks = segment_blocks(page, rules=rules_by_page.get(page.page_number))
            blocks = order_blocks(blocks, page_widths.get(page.page_number, 612.0))
            blocks = enrich_blocks(blocks)
            blocks_by_page[page.page_number] = blocks
        except Exception as exc:
            failures[page.page_number] = f"{type(exc).__name__}: {exc}"
    return blocks_by_page, failures


def run_pipeline(
    path: str,
    *,
    source_name: str,
    max_bytes: int,
    max_pages: int,
    mode: str = "standard",
    chunk_pages: int = DEFAULT_CHUNK_PAGES,
    work_dir: str | None = None,
    job_id: str | None = None,
    resume: bool = False,
) -> PipelineResult:
    stages: list[StageLog] = []

    def timed(stage: str, fn, *args, **kwargs):
        t0 = time.perf_counter()
        try:
            out = fn(*args, **kwargs)
        except Exception as exc:  # last-resort guard; stages handle their own errors
            dt = int((time.perf_counter() - t0) * 1000)
            stages.append(StageLog(stage, dt, f"unexpected: {exc}"))
            raise
        dt = int((time.perf_counter() - t0) * 1000)
        stages.append(StageLog(stage, dt))
        return out

    try:
        valid = timed("validate", validate_pdf, path, max_bytes=max_bytes, max_pages=max_pages)
        if not valid.ok:
            return PipelineResult(False, valid.error_code, valid.message, None, stages)

        classification = timed("classify", classify_pdf, path)
        geometries = timed("geometry", page_geometry, path)
        page_widths = {g.page_number: g.width for g in geometries}
        figures = timed("figure_regions", figure_regions, path)

        page_numbers = [g.page_number for g in geometries]
        plans = chunks.plan_chunks(page_numbers, chunk_pages)

        use_checkpoints = work_dir is not None
        manifest = None
        manifest_file = ""
        chunk_file = None
        if use_checkpoints:
            jid = job_id or f"job-{abs(hash((source_name, valid.page_count))) % 10**8:08d}"
            manifest_file = chunks.manifest_path(work_dir, jid)
            _, chunk_file = chunks.work_paths(work_dir, jid)
            if resume:
                manifest = chunks.load_manifest(manifest_file)
            if manifest is None or [c.pages for c in manifest.chunks] != [p.pages for p in plans]:
                manifest = chunks.Manifest(job_id=jid, chunk_pages=chunk_pages, chunks=plans)
                chunks.save_manifest(manifest_file, manifest)

        blocks_by_page: dict[int, list] = {}
        page_failures: dict = dict(manifest.page_failures) if manifest else {}
        complete = 0
        for plan in (manifest.chunks if manifest else plans):
            if use_checkpoints and resume and plan.status == "complete":
                saved = chunks.load_checkpoint(chunk_file(plan.index))
                if saved:
                    for num, blist in saved.get("blocks", {}).items():
                        blocks_by_page[int(num)] = [_block_from_dict(b) for b in blist]
                    page_failures.update(saved.get("page_failures", {}))
                    complete += 1
                    stages.append(StageLog(f"chunk_{plan.index}", 0, "resumed from checkpoint"))
                    continue
            plan.status = "processing"
            plan.attempts += 1
            t0 = time.perf_counter()
            chunk_blocks, failures = _process_pages(path, plan.pages, page_widths, figures)
            dt = int((time.perf_counter() - t0) * 1000)
            blocks_by_page.update(chunk_blocks)
            page_failures.update({str(k): v for k, v in failures.items()})
            plan.status = "complete"
            complete += 1
            stages.append(StageLog(f"chunk_{plan.index}", dt, f"{len(plan.pages)} pages"))
            if use_checkpoints and manifest:
                chunks.save_checkpoint(chunk_file(plan.index), {
                    "blocks": {str(n): [_block_to_dict(b) for b in blist] for n, blist in chunk_blocks.items()},
                    "page_failures": {str(k): v for k, v in failures.items()},
                })
                manifest.page_failures = dict(page_failures)
                chunks.save_manifest(manifest_file, manifest)

        failed_share = len(page_failures) / max(1, len(page_numbers))
        if failed_share > PAGE_FAILURE_THRESHOLD:
            return PipelineResult(
                False, "PROCESSING_FAILED",
                f"{len(page_failures)}/{len(page_numbers)} pages failed; above abandon threshold.",
                None, stages, None, dict(page_failures), complete, len(plans),
            )

        # Figure assets render AFTER block segmentation so glyph scraps and
        # equation fragments can be suppressed with equation/caption context.
        # Regions stay pre-chunk (stable asset ids); only the raster render
        # is equation-aware.
        equation_boxes = equation_boxes_from_blocks(blocks_by_page)
        caption_boxes = caption_boxes_from_blocks(blocks_by_page)
        figure_assets = timed(
            "figure_assets", extract_figure_assets, path, figures,
            equation_boxes=equation_boxes, caption_boxes=caption_boxes,
        )
        # A table whose structure could not be trusted ships as an image
        # crop of its own region (never as a broken grid).
        fallback_regions = _table_fallback_regions(blocks_by_page)
        if fallback_regions:
            fallback_assets = timed(
                "table_fallback_assets", extract_figure_assets, path, fallback_regions,
                id_fn=table_fallback_asset_id,
            )
            _attach_table_fallbacks(blocks_by_page, fallback_assets)

        model = timed(
            "build_model",
            build_partial_model,
            source_name=source_name,
            classification=classification.label,
            geometries=geometries,
            blocks_by_page=blocks_by_page,
            figure_regions=figures,
            figure_assets=figure_assets,
        )
    except Exception as exc:
        return PipelineResult(False, "PROCESSING_FAILED", f"Pipeline failed: {exc}", None, stages)

    from ..verification.stage import run_verification

    verification = timed("verify", run_verification, model, path, mode=mode)
    message = "OK" if not page_failures else f"OK with {len(page_failures)} page warnings"
    return PipelineResult(True, None, message, model, stages, verification.summarize(), dict(page_failures), complete, len(plans))
