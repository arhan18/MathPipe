"""Fidelity scorecard: run PDFs through the pipeline, grade each DOCX.

Usage (from the repo root, processor venv):
    apps/processor/.venv/bin/python apps/processor/tools/scorecard.py \
        --pdf-dir "$HOME/Downloads/Tests for maths converter" \
        --out-dir /tmp/scorecard [--only MathSample] [--skip-big]

Writes <out-dir>/<tag>/out.docx + metrics.json and <out-dir>/scorecard.md.
Exit code 0 only when every gate passes on every PDF graded.

Metrics are deliberately deterministic and independent of the pipeline's
own self-report (meta.json has lied before): everything is measured from
the finished DOCX package and the raw PDF.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from lxml import etree  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
NS = {"w": W, "m": M}

MATH_SYMBOLS = set("∫∬∭∮∑∏√∞≤≥≠≈≡∂∇±×÷→⇒⇔∈∉∪∩⊂⊆∴∵")
_TOKEN_RE = re.compile(r"[A-Za-z]+|[0-9]+")
_PUA = re.compile("[\ue000-\uf8ff]")

#: Gate thresholds (single source of truth; keep in sync with the spec).
GATES = {
    "G1_completes": "pipeline ok and DOCX written",
    "G2_no_pua": "0 private-use glyphs in DOCX text",
    "G3_word_recall": "token recall >= 0.95",
    "G4_order_recall": "token-bigram recall >= 0.85",
    "G5_math_typeset": "math symbols left as plain text <= 25% of all math symbols",
    "G6_no_fake_omml": "0 OMML blocks with <3 meaningful chars or option-label-only",
    "G7_no_critical": "verification critical == 0",
    "G8_no_duplication": "DOCX token count <= 1.15 x PDF token count (math not emitted twice)",
}


def _tokens(text: str) -> list[str]:
    text = re.sub(r"([\U0001D400-\U0001D7FF])\1", r"\1", text)
    text = unicodedata.normalize("NFKC", text)
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def pdf_tokens(path: str) -> list[str]:
    from src.understanding.text import extract_page_text

    out: list[str] = []
    for page in extract_page_text(path):
        page_text = " ".join(w.text for w in page.words)
        out.extend(_tokens(page_text))
    return out


def _bag(tokens: list[str]) -> dict[str, int]:
    bag: dict[str, int] = {}
    for t in tokens:
        bag[t] = bag.get(t, 0) + 1
    return bag


def _recall(src: list[str], dst: list[str]) -> float:
    if not src:
        return 1.0
    have = _bag(dst)
    hit = 0
    for tok, n in _bag(src).items():
        hit += min(n, have.get(tok, 0))
    return hit / len(src)


def _bigram_recall(src: list[str], dst: list[str]) -> float:
    if len(src) < 2:
        return 1.0
    sb = {(a, b) for a, b in zip(src, src[1:])}
    db = {(a, b) for a, b in zip(dst, dst[1:])}
    return len(sb & db) / len(sb)


def analyze_docx(data_path: str) -> dict:
    from src.mathengine.gate import is_promotable
    from src.mathengine.recognize import DeterministicAsciiRecognizer
    from src.mathengine.spans import split_math_spans

    recognizer = DeterministicAsciiRecognizer()
    with zipfile.ZipFile(data_path) as z:
        root = etree.fromstring(z.read("word/document.xml"))
        media = [n for n in z.namelist() if n.startswith("word/media/")]
    leaked = typeset = 0
    for t in root.iterfind(".//w:t", NS):
        txt = t.text or ""
        if any(ch in MATH_SYMBOLS for ch in txt):
            for sp in split_math_spans(txt):
                if sp.kind != "math" or not any(ch in MATH_SYMBOLS for ch in sp.text):
                    continue
                try:
                    rec = recognizer.recognize(sp.text)
                    ok, _ = is_promotable(sp.text, rec.mathir)
                except Exception:
                    ok = False
                if ok:
                    leaked += sum(1 for ch in sp.text if ch in MATH_SYMBOLS)
    fake = 0
    structure = {"f": 0, "nary": 0, "rad": 0, "sSup": 0, "sSub": 0, "m": 0, "func": 0}
    omaths = root.findall(".//m:oMath", NS)
    for om in omaths:
        s = "".join(x.text or "" for x in om.iterfind(".//m:t", NS))
        typeset += sum(1 for ch in s if ch in MATH_SYMBOLS)
        typeset += len(om.findall(".//m:rad", NS))
        meaningful = re.sub(r"[\s()\[\]]", "", s)
        if len(meaningful) < 3 or re.fullmatch(r"[A-Da-d]\d*", meaningful):
            fake += 1
        for key in structure:
            structure[key] += len(om.findall(f".//m:{key}", NS))
    full_text = " ".join(
        (el.text or "") for el in root.iter(f"{{{W}}}t", f"{{{M}}}t")
    )
    # Table cell text is inside w:t already (python-docx writes w:t runs).
    n_tables = len(root.findall(".//w:tbl", NS))
    total_math_syms = leaked + typeset
    return {
        "text": full_text,
        "omml_total": len(omaths),
        "omml_fake": fake,
        "omml_structure": structure,
        "math_symbols_leaked": leaked,
        "math_symbols_typeset": typeset,
        "math_typeset_ratio": (typeset / total_math_syms) if total_math_syms else 1.0,
        "pua_chars": len(_PUA.findall(full_text)),
        "replacement_chars": full_text.count("\ufffd"),
        "tables": n_tables,
        "media_files": len(media),
    }


def grade(tag: str, pdf_path: str, out_dir: str) -> dict:
    from src.cli import _figure_assets_from_model
    from src.pipeline.runner import run_pipeline
    from src.word.builder import build_docx

    os.makedirs(os.path.join(out_dir, tag), exist_ok=True)
    t0 = time.perf_counter()
    result = run_pipeline(
        pdf_path,
        source_name=os.path.basename(pdf_path),
        max_bytes=250 * 1024 * 1024,
        max_pages=1000,
        mode="standard",
    )
    row: dict = {"tag": tag, "pdf": os.path.basename(pdf_path), "ok": bool(result.ok)}
    verification = result.verification or {}
    row["verification"] = {k: verification.get(k) for k in ("status", "issues", "critical")}
    if not result.ok:
        row["error"] = f"{result.error_code}: {result.message}"
        row["gates"] = {g: False for g in GATES}
        return row
    docx_bytes, report = build_docx(
        result.model, figures=_figure_assets_from_model(result.model)
    )
    docx_path = os.path.join(out_dir, tag, "out.docx")
    with open(docx_path, "wb") as f:
        f.write(docx_bytes)
    row["builder_report"] = report
    m = analyze_docx(docx_path)
    src = pdf_tokens(pdf_path)
    dst = _tokens(m.pop("text"))
    row.update(m)
    row["word_recall"] = round(_recall(src, dst), 4)
    row["order_recall"] = round(_bigram_recall(src, dst), 4)
    row["dup_ratio"] = round(len(dst) / max(1, len(src)), 3)
    row["seconds"] = round(time.perf_counter() - t0, 1)
    row["gates"] = {
        "G1_completes": True,
        "G2_no_pua": m["pua_chars"] == 0,
        "G3_word_recall": row["word_recall"] >= 0.95,
        "G4_order_recall": row["order_recall"] >= 0.85,
        "G5_math_typeset": m["math_typeset_ratio"] >= 0.75,
        "G6_no_fake_omml": m["omml_fake"] == 0,
        "G7_no_critical": (verification.get("critical") or 0) == 0,
        "G8_no_duplication": row["dup_ratio"] <= 1.15,
    }
    with open(os.path.join(out_dir, tag, "metrics.json"), "w") as f:
        json.dump(row, f, indent=1, ensure_ascii=False)
    return row


def render_md(rows: list[dict]) -> str:
    gate_ids = list(GATES)
    lines = ["# Scorecard", ""]
    lines.append("| PDF | recall | order | OMML | fake | frac/nary/rad/mat | typeset% | PUA | tbl | dup | " + " ".join(g.split("_")[0] for g in gate_ids) + " |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|" + "---|" * len(gate_ids))
    for r in rows:
        if "word_recall" not in r:
            lines.append(f"| {r['pdf']} | FAILED: {r.get('error')} |" + " |" * (9 + len(gate_ids)))
            continue
        s = r["omml_structure"]
        gates = " ".join("✅" if r["gates"][g] else "❌" for g in gate_ids)
        lines.append(
            f"| {r['pdf']} | {r['word_recall']:.2f} | {r['order_recall']:.2f} | {r['omml_total']} | {r['omml_fake']} "
            f"| {s['f']}/{s['nary']}/{s['rad']}/{s['m']} | {r['math_typeset_ratio']*100:.0f} | {r['pua_chars']} | {r['tables']} | {r['dup_ratio']:.2f} | {gates} |"
        )
    lines += ["", "## Gates", ""] + [f"- **{g.split('_')[0]}** {g}: {d}" for g, d in GATES.items()]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--out-dir", default="/tmp/scorecard")
    ap.add_argument("--only", help="substring filter on PDF filename")
    ap.add_argument("--skip-big", action="store_true", help="skip PDFs over 40 pages")
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
        print(f"grading {name} ...", flush=True)
        try:
            rows.append(grade(tag, path, args.out_dir))
        except Exception as exc:  # a grader crash is a G1 failure, not a stop
            rows.append({"tag": tag, "pdf": name, "ok": False, "error": f"{type(exc).__name__}: {exc}",
                         "gates": {g: False for g in GATES}})
    os.makedirs(args.out_dir, exist_ok=True)
    md = render_md(rows)
    with open(os.path.join(args.out_dir, "scorecard.md"), "w") as f:
        f.write(md)
    with open(os.path.join(args.out_dir, "scorecard.json"), "w") as f:
        json.dump(rows, f, indent=1, ensure_ascii=False)
    print(md)
    return 0 if rows and all(all(r["gates"].values()) for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
