"""CLI: PDF → DocumentModel, DocumentModel → DOCX, and one-step PDF → DOCX."""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.contract.document_model import dump_model  # noqa: E402
from src.pipeline.runner import run_pipeline  # noqa: E402


def cmd_process(args) -> int:
    result = run_pipeline(
        args.pdf,
        source_name=os.path.basename(args.pdf),
        max_bytes=args.max_mb * 1024 * 1024,
        max_pages=args.max_pages,
        mode=args.mode,
        chunk_pages=args.chunk_pages,
        work_dir=args.work_dir,
        job_id=args.job_id,
        resume=args.resume,
    )
    if not result.ok:
        print(json.dumps({"ok": False, "error_code": result.error_code, "message": result.message}))
        return 2
    assert result.model is not None
    dump_model(result.model, args.out)
    pages = result.model["document"]["metadata"]["pageCount"]
    blocks = sum(len(p["blocks"]) for p in result.model["document"]["pages"])
    print(json.dumps({
        "ok": True,
        "pages": pages,
        "blocks": blocks,
        "classification": result.model["document"]["metadata"]["classification"],
        "verification": result.verification,
        "page_failures": result.page_failures,
        "chunks": [result.chunks_complete, result.chunks_total],
        "peak_mb": _peak_mb(),
        "stages": [(s.stage, s.duration_ms) for s in result.stages],
    }))
    return 0


def _figure_assets_from_model(model: dict) -> dict[str, bytes]:
    """Recover {assetId: PNG bytes} from figure blocks' inline imageBase64.

    build_partial_model already embeds every extracted figure as base64 on
    its figure block, so a round-tripped JSON model still carries the pixels;
    this feeds them to the builder's primary figures path. A malformed
    payload is skipped — the builder then emits an explicit missing-figure
    placeholder instead of a wrong image.
    """
    assets: dict[str, bytes] = {}
    pages = model.get("document", {}).get("pages", []) or []
    for page in pages:
        for block in (page or {}).get("blocks", []) or []:
            if not isinstance(block, dict) or block.get("type") != "figure":
                continue
            asset_id, payload = block.get("assetId"), block.get("imageBase64")
            if not asset_id or not payload:
                continue
            try:
                assets[str(asset_id)] = base64.b64decode(str(payload))
            except Exception:
                continue
    return assets


def cmd_build_docx(args) -> int:
    from src.word.builder import build_docx

    with open(args.model, encoding="utf-8") as f:
        model = json.load(f)
    data, report = build_docx(model, figures=_figure_assets_from_model(model))
    with open(args.out, "wb") as f:
        f.write(data)
    print(json.dumps({"ok": True, "bytes": len(data), "report": report}))
    return 0


def cmd_convert(args) -> int:
    t0 = time.perf_counter()
    result = run_pipeline(
        args.pdf,
        source_name=os.path.basename(args.pdf),
        max_bytes=args.max_mb * 1024 * 1024,
        max_pages=args.max_pages,
        mode=args.mode,
    )
    if not result.ok:
        print(json.dumps({"ok": False, "error": result.message}))
        return 2
    from src.word.builder import build_docx

    assert result.model is not None
    data, report = build_docx(result.model, figures=_figure_assets_from_model(result.model))
    with open(args.out, "wb") as f:
        f.write(data)
    print(json.dumps({
        "ok": True,
        "docx": args.out,
        "bytes": len(data),
        "pages": result.model["document"]["metadata"]["pageCount"],
        "equations": report["equations"],
        "figures": report["figures"],
        "tables": report["tables"],
        "duration_s": round(time.perf_counter() - t0, 1),
    }))
    return 0


def _peak_mb() -> float:
    try:
        import resource
        import sys
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports kilobytes, macOS reports bytes.
        kb = rss if sys.platform.startswith("linux") else rss / 1024
        return round(kb / 1024, 1)
    except (ImportError, OSError):
        return -1.0


def main() -> int:
    ap = argparse.ArgumentParser(description="MathPipe document pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("process", help="PDF → partial DocumentModel JSON")
    p.add_argument("pdf", help="input PDF path")
    p.add_argument("-o", "--out", required=True, help="output DocumentModel JSON path")
    p.add_argument("--max-mb", type=int, default=25)
    p.add_argument("--max-pages", type=int, default=25)
    p.add_argument("--mode", choices=["standard", "verified"], default="standard")
    p.add_argument("--chunk-pages", type=int, default=10)
    p.add_argument("--work-dir", default=None, help="checkpoint directory (enables resume)")
    p.add_argument("--job-id", default=None)
    p.add_argument("--resume", action="store_true")
    p.set_defaults(fn=cmd_process)

    b = sub.add_parser("build-docx", help="DocumentModel JSON → .docx")
    b.add_argument("model", help="input DocumentModel JSON path")
    b.add_argument("-o", "--out", required=True, help="output .docx path")
    b.set_defaults(fn=cmd_build_docx)

    c = sub.add_parser("convert", help="PDF → .docx in one step")
    c.add_argument("pdf", help="input PDF path")
    c.add_argument("-o", "--out", required=True, help="output .docx path")
    c.add_argument("--mode", choices=["standard", "verified"], default="standard")
    c.add_argument("--max-mb", type=int, default=25)
    c.add_argument("--max-pages", type=int, default=25)
    c.set_defaults(fn=cmd_convert)

    # Back-compat: bare `cli.py PDF -o OUT` means `process`.
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-") and sys.argv[1] not in ("process", "build-docx", "convert"):
        sys.argv.insert(1, "process")
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
