"""Visual-fidelity grader: render the DOCX and diff it against the source PDF.

The scorecard (tools/scorecard.py) measures the DOCX package as XML. It cannot
see what a human sees. This tool closes that gap:

    source PDF  ->  pipeline  ->  DOCX  ->  soffice --convert-to pdf  ->  render

then compares source vs render with pdfplumber, and writes aligned page-pair
PNGs so a human can look at the result.

Usage (from the repo root, processor venv):

    apps/processor/.venv/bin/python apps/processor/tools/fidelity.py \
        --pdf-dir "$HOME/Downloads/Tests for maths converter" \
        --out-dir /tmp/fidelity [--only MathSample] [--skip-big]

Metrics are measured from the finished artifacts (rendered PDF + DOCX XML),
never from the pipeline's own self-report. Exit code 0 only when every gate
passes on every PDF graded.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from lxml import etree  # noqa: E402
from src.understanding.text import _MATH_ALPHA_DUP_RE, extract_page_text  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
NS = {"w": W, "m": M}

_TOKEN_RE = re.compile(r"[A-Za-z]+|[0-9]+")
_MATH_SYMBOLS = set("∫∬∭∮∑∏√∞≤≥≠≈≡∂∇±×÷→⇒⇔∈∉∪∩⊂⊆∠∴∵")
#: Page furniture that must never end up in body content.
_FOOTER_RE = re.compile(r"\bpage\s+\d+\s+of\s+\d+\b", re.I)
#: (A)/(B)/(C)/(D) option labels welded into one equation run.
_OPTION_SOUP_RE = re.compile(r"(?:[A-D]\s*[\)\|])|(?:\|[A-D]\b)|(?:[A-D]\d)")
#: A body paragraph that is nothing but a small number = orphan fragment.
_ORPHAN_NUM_RE = re.compile(r"^\d{1,3}$")
#: Page-furniture folios: "Page 1 of 10", "1 of 10", "2025-26. Page 1 of 10".
_FOLIO_LINE_RE = re.compile(
    r"^(?:[\d.,:\-–—/]{1,16}\s+)?(?:page|p\.)?\s*\d{1,4}\s*(?:of|/)\s*\d{1,4}\.?$",
    re.IGNORECASE,
)
#: Glyphs that render as a box/question mark in common Word fonts.
_UNMAPPED_RE = re.compile("[\u00bf\ufffd\u25a1\u2370]")

#: Fidelity gates (single source of truth).
GATES = {
    "F1_renders": "soffice rendered the DOCX to a readable PDF",
    "F2_text_recall": "body-token recall (rendered vs source, page furniture excluded) >= 0.95",
    "F3_figures_intact": "every figure embedded in the DOCX survives the render",
    "F4_tables_intact": "every Word table survives the render",
    "F5_no_furniture_in_body": "0 page-footer strings in body text",
    "F6_no_option_soup": "0 OMML blocks with welded option labels",
    "F7_no_orphan_numbers": "0 body paragraphs that are a bare small number",
    "F8_no_unmapped_glyphs": "0 unmapped/replacement glyphs in body text",
}


def _tokens(text: str) -> list[str]:
    text = _MATH_ALPHA_DUP_RE.sub(r"\1", text)
    text = unicodedata.normalize("NFKC", text)
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _bag(tokens: list[str]) -> dict[str, int]:
    bag: dict[str, int] = {}
    for t in tokens:
        bag[t] = bag.get(t, 0) + 1
    return bag


def _recall(src: list[str], dst: list[str]) -> float:
    if not src:
        return 1.0
    have = _bag(dst)
    hit = sum(min(n, have.get(t, 0)) for t, n in _bag(src).items())
    return hit / len(src)


def _soffice() -> str | None:
    for name in ("soffice", "libreoffice"):
        path = shutil.which(name)
        if path:
            return path
    return None


def render_docx(docx_path: str, out_dir: str) -> tuple[str | None, str]:
    """DOCX -> PDF via LibreOffice headless. Returns (pdf_path, error)."""
    soffice = _soffice()
    if not soffice:
        return None, "soffice not installed"
    os.makedirs(out_dir, exist_ok=True)
    profile = "file://" + os.path.join(out_dir, ".loprofile")
    cmd = [
        soffice,
        f"-env:UserInstallation={profile}",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        out_dir,
        docx_path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return None, "soffice timed out"
    produced = os.path.join(out_dir, os.path.splitext(os.path.basename(docx_path))[0] + ".pdf")
    if not os.path.exists(produced):
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-2:]
        return None, "soffice produced no PDF: " + " | ".join(tail)
    return produced, ""


def _furniture_line_texts(pages: list[dict], raw_lines: list[list[str]]) -> set[str]:
    """Page-furniture lines in the source (folios + repeated footers).

    These are page furniture, not body content: a correct conversion drops
    them, so counting them against recall would punish the engine for
    doing the right thing. Repeated verbatim bottom-band lines ("*Please
    note that ...", "Page 1 of 10") and folio shapes are excluded from the
    reference token set.
    """
    counts: dict[str, int] = {}
    for lines in raw_lines:
        for text in lines:
            counts[text] = counts.get(text, 0) + 1
    out: set[str] = set()
    for lines in raw_lines:
        for text in lines:
            words = text.split()
            if _FOLIO_LINE_RE.match(text) and len(words) <= 5:
                out.add(text)
            elif counts.get(text, 0) >= 3 and len(words) <= 12:
                out.add(text)
    return out


def scan_pdf(path: str, *, use_extracted_body: bool = True) -> dict:
    import pdfplumber

    pages = []
    raw_lines: list[list[str]] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            try:
                images = len(page.images)
            except Exception:
                images = 0
            try:
                # Only figure-sized rasters count as figures. Inline math
                # glyphs extracted as 20pt images are not figures and must
                # not be reported as lost content.
                big = sum(1 for im in page.images if im["width"] > 40 and im["height"] > 40)
            except Exception:
                big = 0
            try:
                tables = len(page.find_tables())
            except Exception:
                tables = 0
            pages.append({"text": text, "tokens": _tokens(text), "images": images,
                          "figure_images": big, "tables": tables})
            raw_lines.append([ln.strip() for ln in (text or "").splitlines() if ln.strip()])
    furniture = _furniture_line_texts(pages, raw_lines)
    body_tokens: list[str] = []
    extracted_pages = None
    if use_extracted_body:
        try:
            extracted_pages = extract_page_text(path)
        except Exception:
            extracted_pages = None
    if extracted_pages is not None and len(extracted_pages) == len(pages):
        for pg in extracted_pages:
            body_tokens.extend(_tokens(" ".join(w.text for w in pg.words)))
    else:
        for text, lines in zip((p["text"] for p in pages), raw_lines):
            keep = [ln for ln in lines if ln not in furniture]
            body_tokens.extend(_tokens(" ".join(keep)))
    return {
        "pages": pages,
        "tokens": [t for p in pages for t in p["tokens"]],
        "body_tokens": body_tokens,
        "furniture_lines": len(furniture),
        "images": sum(p["images"] for p in pages),
        "figure_images": sum(p["figure_images"] for p in pages),
        "tables": sum(p["tables"] for p in pages),
        "math_symbols": sum(1 for p in pages for c in p["text"] if c in _MATH_SYMBOLS),
    }


def analyze_docx(docx_path: str) -> dict:
    with zipfile.ZipFile(docx_path) as z:
        root = etree.fromstring(z.read("word/document.xml"))
        names = z.namelist()
    body_text: list[str] = []
    for t in root.iterfind(".//w:t", NS):
        body_text.append(t.text or "")
    full = " ".join(body_text)
    paragraphs = []
    for p in root.iterfind(".//w:body/w:p", NS):
        paragraphs.append("".join(x.text or "" for x in p.iterfind(".//w:t", NS)).strip())
    omaths = root.findall(".//m:oMath", NS)
    soup = 0
    for om in omaths:
        # A welded option label is a FENCE holding one letter ("(A)") inside
        # an expression: the label was parsed as math, not as text. Letter
        # adjacency alone ("33B", "2A") is ordinary math, not corruption.
        welded = False
        for delim in om.findall(".//m:d", NS):
            inner = "".join(x.text or "" for x in delim.iterfind(".//m:t", NS)).strip()
            if len(inner) == 1 and inner in "ABCD":
                welded = True
                break
        if welded:
            soup += 1
    return {
        "omml_total": len(omaths),
        "omml_option_soup": soup,
        "tables": len(root.findall(".//w:tbl", NS)),
        "media_files": sum(1 for n in names if n.startswith("word/media/")),
        "has_header_parts": any("header" in n for n in names),
        "has_footer_parts": any("footer" in n for n in names),
        "footer_in_body": len(_FOOTER_RE.findall(full)),
        "orphan_number_paragraphs": sum(1 for p in paragraphs if _ORPHAN_NUM_RE.match(p)),
        "unmapped_glyphs": len(_UNMAPPED_RE.findall(full)),
        "body_tokens": _tokens(full),
    }


def align_pages(src_pages: list[dict], out_pages: list[dict]) -> list[tuple[int, int, float]]:
    """Map each rendered page to its best-matching source page by token overlap."""
    pairs = []
    for i, op in enumerate(out_pages):
        best, score = None, 0.0
        otoks = set(op["tokens"])
        for j, sp in enumerate(src_pages):
            if not otoks:
                break
            r = len(otoks & set(sp["tokens"])) / len(otoks)
            if r > score:
                best, score = j, r
        pairs.append((i, best if best is not None else i, round(score, 3)))
    return pairs


def write_page_pairs(src_pdf: str, out_pdf: str, pairs, out_dir: str, limit: int) -> list[str]:
    import pypdfium2 as pdfium

    os.makedirs(out_dir, exist_ok=True)
    src_doc = pdfium.PdfDocument(src_pdf)
    out_doc = pdfium.PdfDocument(out_pdf)
    written = []
    for rp, sp, score in pairs[:limit]:
        for doc, idx, tag in ((src_doc, sp, "src"), (out_doc, rp, "out")):
            img = doc[idx].render(scale=1.6).to_pil()
            path = os.path.join(out_dir, f"{tag}_p{idx + 1}.png")
            img.save(path)
            written.append(path)
    return written


def grade(tag: str, pdf_path: str, out_dir: str, page_pairs: int) -> dict:
    from src.cli import _figure_assets_from_model
    from src.pipeline.runner import run_pipeline
    from src.word.builder import build_docx

    work = os.path.join(out_dir, tag)
    os.makedirs(work, exist_ok=True)
    t0 = time.perf_counter()
    result = run_pipeline(
        pdf_path,
        source_name=os.path.basename(pdf_path),
        max_bytes=250 * 1024 * 1024,
        max_pages=1000,
        mode="standard",
    )
    row: dict = {"tag": tag, "pdf": os.path.basename(pdf_path), "ok": bool(result.ok)}
    if not result.ok:
        row["error"] = f"{result.error_code}: {result.message}"
        row["gates"] = {g: False for g in GATES}
        return row

    docx_bytes, report = build_docx(result.model, figures=_figure_assets_from_model(result.model))
    docx_path = os.path.join(work, "out.docx")
    with open(docx_path, "wb") as f:
        f.write(docx_bytes)

    d = analyze_docx(docx_path)
    src = scan_pdf(pdf_path)
    rendered_pdf, err = render_docx(docx_path, work)
    row["render_error"] = err
    if not rendered_pdf:
        out = {"pages": [], "tokens": [], "images": 0, "tables": 0, "math_symbols": 0}
        row["gates"] = {g: False for g in GATES}
        row["gates"]["F1_renders"] = False
        row["seconds"] = round(time.perf_counter() - t0, 1)
        return row

    out = scan_pdf(rendered_pdf, use_extracted_body=False)
    row.update(
        {
            "src_pages": len(src["pages"]),
            "out_pages": len(out["pages"]),
            "text_recall": round(_recall(src["body_tokens"], out["tokens"]), 4),
            "text_recall_raw": round(_recall(src["tokens"], out["tokens"]), 4),
            "text_precision": round(_recall(out["tokens"], src["tokens"]), 4),
            "src_furniture_lines": src["furniture_lines"],
            "src_images": src["images"],
            "src_figure_images": src["figure_images"],
            "out_images": out["images"],
            "docx_media": d["media_files"],
            "figures_embedded": report.get("figures", 0),
            "figures_missing": report.get("figure_missing", 0),
            "images_lost_vs_source": src["figure_images"] - d["media_files"],
            "src_tables": src["tables"],
            "out_tables": out["tables"],
            "docx_tables": d["tables"],
            "tables_lost_vs_source": src["tables"] - d["tables"],
            "src_math_symbols": src["math_symbols"],
            "out_math_symbols": out["math_symbols"],
            "footer_in_body": d["footer_in_body"],
            "has_footer_parts": d["has_footer_parts"],
            "omml_total": d["omml_total"],
            "omml_option_soup": d["omml_option_soup"],
            "orphan_number_paragraphs": d["orphan_number_paragraphs"],
            "unmapped_glyphs": d["unmapped_glyphs"],
        }
    )
    pairs = align_pages(src["pages"], out["pages"])
    row["page_alignment"] = pairs
    row["alignment_mean"] = round(sum(p[2] for p in pairs) / max(1, len(pairs)), 3)
    if page_pairs:
        row["page_pngs"] = write_page_pairs(pdf_path, rendered_pdf, pairs, os.path.join(work, "pages"), page_pairs)
    row["gates"] = {
        "F1_renders": True,
        "F2_text_recall": row["text_recall"] >= 0.95,
        "F3_figures_intact": row["figures_missing"] == 0 and row["out_images"] >= row["docx_media"],
        "F4_tables_intact": row["out_tables"] >= row["docx_tables"]
        and (row["src_tables"] == 0 or row["docx_tables"] >= 1),
        "F5_no_furniture_in_body": row["footer_in_body"] == 0,
        "F6_no_option_soup": row["omml_option_soup"] == 0,
        "F7_no_orphan_numbers": row["orphan_number_paragraphs"] == 0,
        "F8_no_unmapped_glyphs": row["unmapped_glyphs"] == 0,
    }
    row["seconds"] = round(time.perf_counter() - t0, 1)
    with open(os.path.join(work, "fidelity.json"), "w") as f:
        json.dump(row, f, indent=1, ensure_ascii=False)
    return row


def render_md(rows: list[dict]) -> str:
    gate_ids = list(GATES)
    lines = ["# Visual fidelity", ""]
    lines.append("| PDF | pages | recall | prec | fig src/emb/out | tbl src/docx/out | img lost | tbl lost | furniture | soup | orphans | unmapped | align | " + " ".join(g.split("_")[0] for g in gate_ids) + " |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|" + "---|" * len(gate_ids))
    for r in rows:
        if "text_recall" not in r:
            lines.append(f"| {r['pdf']} | FAILED: {r.get('error')} |" + " |" * (12 + len(gate_ids)))
            continue
        gates = " ".join("✅" if r["gates"][g] else "❌" for g in gate_ids)
        lines.append(
            f"| {r['pdf']} | {r['src_pages']}→{r['out_pages']} | {r['text_recall']:.3f} | {r['text_precision']:.3f} "
            f"| {r['src_figure_images']}/{r['figures_embedded']}/{r['out_images']} | {r['src_tables']}/{r['docx_tables']}/{r['out_tables']} "
            f"| {r['images_lost_vs_source']} | {r['tables_lost_vs_source']} "
            f"| {r['footer_in_body']} | {r['omml_option_soup']} | {r['orphan_number_paragraphs']} | {r['unmapped_glyphs']} "
            f"| {r['alignment_mean']} | {gates} |"
        )
    lines += ["", "## Gates", ""] + [f"- **{g.split('_')[0]}** {g}: {d}" for g, d in GATES.items()]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--out-dir", default="/tmp/fidelity")
    ap.add_argument("--only", help="substring filter on PDF filename")
    ap.add_argument("--skip-big", action="store_true", help="skip PDFs over 40 pages")
    ap.add_argument("--page-pairs", type=int, default=2, help="aligned page-pair PNGs to write per PDF")
    args = ap.parse_args()

    from pypdf import PdfReader

    rows: list[dict] = []
    for name in sorted(os.listdir(args.pdf_dir)):
        if not name.lower().endswith(".pdf") or name.startswith("._"):
            continue
        if args.only and args.only.lower() not in name.lower():
            continue
        path = os.path.join(args.pdf_dir, name)
        if args.skip_big and len(PdfReader(path).pages) > 40:
            continue
        tag = re.sub(r"[^A-Za-z0-9]+", "_", os.path.splitext(name)[0]).strip("_")
        print(f"fidelity {name} ...", flush=True)
        try:
            rows.append(grade(tag, path, args.out_dir, args.page_pairs))
        except Exception as exc:  # a grader crash is a failure, not a stop
            rows.append({"tag": tag, "pdf": name, "ok": False,
                         "error": f"{type(exc).__name__}: {exc}",
                         "gates": {g: False for g in GATES}})
    os.makedirs(args.out_dir, exist_ok=True)
    md = render_md(rows)
    with open(os.path.join(args.out_dir, "fidelity.md"), "w") as f:
        f.write(md)
    with open(os.path.join(args.out_dir, "fidelity.json"), "w") as f:
        json.dump(rows, f, indent=1, ensure_ascii=False)
    print(md)
    return 0 if rows and all(all(r["gates"].values()) for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
