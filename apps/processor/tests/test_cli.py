"""CLI tests: one-step `convert` (PDF → DOCX) and JSON `build-docx` figures."""
from __future__ import annotations

import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(HERE, "..", "src", "cli.py")

sys.path.insert(0, os.path.join(HERE, ".."))

from src.cli import _figure_assets_from_model  # noqa: E402
from src.mathengine.recognize import DeterministicAsciiRecognizer  # noqa: E402


def run_cli(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, CLI, *argv], capture_output=True, text=True, timeout=120
    )


def document_xml(docx_path: str) -> str:
    with zipfile.ZipFile(docx_path) as z:
        return z.read("word/document.xml").decode("utf-8")


def make_png(size: tuple[int, int] = (400, 300)) -> bytes:
    """Small diagram-like PNG: shapes large enough to pass the glyph-scrap gate."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", size, (250, 250, 250))
    draw = ImageDraw.Draw(img)
    draw.rectangle([40, 40, size[0] - 40, size[1] - 40], outline=(30, 30, 30), width=6)
    draw.line([40, size[1] - 40, size[0] // 2, 60], fill=(200, 60, 60), width=8)
    draw.line([size[0] // 2, 60, size[0] - 40, size[1] - 40], fill=(60, 60, 200), width=8)
    draw.ellipse([160, 110, 240, 190], fill=(255, 210, 80), outline=(30, 30, 30), width=4)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestConvertCommand(unittest.TestCase):
    """One-step PDF → DOCX on a locally generated fixture (equation + figure)."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="w6_cli_")
        cls.dir = cls._tmp.name
        png = os.path.join(cls.dir, "diagram.png")
        with open(png, "wb") as f:
            f.write(make_png())

        from reportlab.lib.pagesizes import LETTER
        from reportlab.pdfgen import canvas

        cls.pdf = os.path.join(cls.dir, "fixture.pdf")
        c = canvas.Canvas(cls.pdf, pagesize=LETTER)
        c.setFont("Helvetica", 13)
        c.drawString(72, 710, "1. Solve x^2 + 3x + 2 = 0")
        c.drawString(72, 688, "Solve each equation. Show all steps.")
        c.drawImage(png, 72, 380, width=220, height=165)
        c.showPage()
        c.save()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_convert_writes_docx_with_omath_and_drawing(self):
        out = os.path.join(self.dir, "out.docx")
        proc = run_cli("convert", self.pdf, "-o", out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        summary = json.loads(proc.stdout)
        self.assertEqual(
            set(summary),
            {"ok", "docx", "bytes", "pages", "equations", "figures", "tables", "duration_s"},
        )
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["docx"], out)
        self.assertEqual(summary["pages"], 1)
        self.assertGreaterEqual(summary["equations"], 1)
        self.assertGreaterEqual(summary["figures"], 1)
        self.assertTrue(os.path.exists(out))
        self.assertEqual(summary["bytes"], os.path.getsize(out))
        with zipfile.ZipFile(out) as z:
            self.assertIsNone(z.testzip())
            xml = z.read("word/document.xml").decode("utf-8")
        self.assertIn("<m:oMath", xml)
        self.assertIn("<w:drawing", xml)

    def test_convert_missing_pdf_exits_2_and_writes_nothing(self):
        out = os.path.join(self.dir, "failed.docx")
        proc = run_cli("convert", os.path.join(self.dir, "missing.pdf"), "-o", out)
        self.assertEqual(proc.returncode, 2)
        payload = json.loads(proc.stdout)
        self.assertEqual(set(payload), {"ok", "error"})
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["error"])
        self.assertFalse(os.path.exists(out))


class TestBuildDocxCommand(unittest.TestCase):
    """A JSON model must keep its figures (inline imageBase64) on build."""

    def test_build_docx_from_json_keeps_figures(self):
        rec = DeterministicAsciiRecognizer().recognize("x^2 + 3x + 2 = 0")
        model = {
            "schemaVersion": "document-model/v0.1-partial",
            "document": {
                "id": "t",
                "metadata": {
                    "sourceName": "t.pdf",
                    "classification": "BORN_DIGITAL",
                    "pageCount": 1,
                    "producer": "test",
                },
                "pages": [
                    {
                        "pageNumber": 1,
                        "width": 612.0,
                        "height": 792.0,
                        "blocks": [
                            {
                                "id": "e1", "type": "equation", "bbox": [72, 80, 290, 100],
                                "readingOrder": 1, "style": {},
                                "content": rec.latex, "mathir": rec.mathir,
                            },
                            {
                                "id": "fig1", "type": "figure", "bbox": [72, 300, 292, 420],
                                "readingOrder": 2, "style": {}, "assetId": "fig-p1-0",
                                "imageBase64": base64.b64encode(make_png((240, 160))).decode("ascii"),
                            },
                        ],
                    }
                ],
            },
        }
        with tempfile.TemporaryDirectory(prefix="w6_json_") as d:
            model_path = os.path.join(d, "model.json")
            with open(model_path, "w", encoding="utf-8") as f:
                json.dump(model, f)
            out = os.path.join(d, "out.docx")
            proc = run_cli("build-docx", model_path, "-o", out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["report"]["figures"], 1)
            self.assertEqual(payload["report"]["figure_missing"], 0)
            xml = document_xml(out)
        self.assertIn("<m:oMath", xml)
        self.assertIn("<w:drawing", xml)


class TestFigureAssetsFromModel(unittest.TestCase):
    def test_decodes_valid_and_skips_malformed(self):
        good = base64.b64encode(b"\x89PNG-fixture-bytes").decode("ascii")
        model = {
            "document": {
                "pages": [
                    {
                        "blocks": [
                            {"type": "figure", "assetId": "fig-p1-0", "imageBase64": good},
                            {"type": "figure", "assetId": "fig-p1-1", "imageBase64": "!!! not base64 !!!"},
                            {"type": "figure", "assetId": "fig-p1-2"},
                            {"type": "paragraph", "content": "nope"},
                            "not-a-dict",
                        ]
                    }
                ]
            }
        }
        self.assertEqual(
            _figure_assets_from_model(model),
            {"fig-p1-0": b"\x89PNG-fixture-bytes"},
        )


if __name__ == "__main__":
    unittest.main()
