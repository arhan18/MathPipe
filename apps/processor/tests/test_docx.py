"""DOCX/OMML engine tests: renderer tags, builder output validity."""
from __future__ import annotations

import io
import os
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.word import omml  # noqa: E402
from src.word.builder import build_docx  # noqa: E402
from src.mathengine import mathir as M  # noqa: E402
from src.mathengine.recognize import DeterministicAsciiRecognizer  # noqa: E402


def render(text: str) -> str:
    rec = DeterministicAsciiRecognizer().recognize(text)
    return omml.render_omath(rec.mathir)


class TestOmmlTags(unittest.TestCase):
    def test_fraction(self):
        self.assertIn("<m:f>", render("a / b"))

    def test_superscript_subscript(self):
        xml = render("x^2 + a_n")
        self.assertIn("<m:sSup>", xml)
        self.assertIn("<m:sSub>", xml)

    def test_root_function_fence(self):
        xml = render("sqrt(x) + sin(x)")
        self.assertIn("<m:rad>", xml)
        self.assertIn("<m:func>", xml)

    def test_matrix(self):
        doc = M.wrap(M.matrix([[M.text("a"), M.text("b")], [M.text("c"), M.text("d")]]))
        xml = omml.render_omath(doc)
        self.assertIn("<m:mr>", xml)
        self.assertEqual(xml.count("<m:mr>"), 2)

    def test_nary_integral_with_bounds(self):
        from src.mathengine import mathir as M

        doc = M.wrap(
            __import__("src.docx.omml", fromlist=["x"]).__dict__ and M.operator("∫")
            if False
            else {
                "type": "limit",
                "base": {"type": "text", "value": "∫"},
                "lower": {"type": "text", "value": "0"},
                "upper": {"type": "text", "value": "1"},
            }
        )
        xml = omml.render_omath(doc)
        self.assertIn("<m:nary>", xml)
        self.assertIn("<m:limLoc", xml)
        self.assertIn("<m:sub>", xml)
        self.assertIn("<m:sup>", xml)
        doc = M.wrap(M.fence("(", ")", M.text("x")))
        xml = omml.render_omath(doc)
        self.assertIn('m:val="("', xml)

    def test_unsupported_raises(self):
        with self.assertRaises(omml.UnsupportedConstruct):
            omml.render_node({"type": "teleport"})

    def test_accent_gate(self):
        with self.assertRaises(omml.UnsupportedConstruct):
            omml.render_node(M.accent("squiggle", M.text("x")) if hasattr(M, "accent") else {"type": "accent", "kind": "squiggle", "child": M.text("x")})


def sample_model() -> dict:
    rec = DeterministicAsciiRecognizer()
    eq1 = rec.recognize("x^2 + 3x + 2 = 0")
    eq2 = rec.recognize("(x^2 + 1) / (x - 1)")
    return {
        "schemaVersion": "document-model/v0.1-partial",
        "document": {
            "id": "test",
            "metadata": {"sourceName": "t", "classification": "BORN_DIGITAL", "pageCount": 1, "producer": "test"},
            "pages": [
                {
                    "pageNumber": 1,
                    "width": 612.0,
                    "height": 792.0,
                    "blocks": [
                        {"id": "h", "type": "heading", "bbox": [0, 0, 1, 1], "readingOrder": 1, "style": {}, "content": "Algebra"},
                        {"id": "e1", "type": "equation", "bbox": [0, 0, 1, 1], "readingOrder": 2, "style": {},
                         "content": eq1.latex, "mathir": eq1.mathir, "number": "4"},
                        {"id": "e2", "type": "equation", "bbox": [0, 0, 1, 1], "readingOrder": 3, "style": {},
                         "content": eq2.latex, "mathir": eq2.mathir},
                        {"id": "t1", "type": "table", "bbox": [0, 0, 1, 1], "readingOrder": 4, "style": {},
                         "table": {"rows": [["a", "b"], ["c", "d"]], "caption": "Table 1. Symbols."}},
                        {"id": "p1", "type": "paragraph", "bbox": [0, 0, 1, 1], "readingOrder": 5, "style": {},
                         "content": "Done."},
                    ],
                }
            ],
        },
    }


class TestBuilder(unittest.TestCase):
    def test_docx_is_valid_zip_with_omath(self):
        data, report = build_docx(sample_model())
        self.assertTrue(data[:4] == b"PK\x03\x04")
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            self.assertIn("word/document.xml", z.namelist())
            xml = z.read("word/document.xml").decode("utf-8")
        self.assertIn("oMath", xml)
        self.assertEqual(xml.count("<m:oMath"), 2)
        self.assertIn("Algebra", xml)
        self.assertIn("Table 1. Symbols.", xml)
        self.assertIn("(4)", xml)
        self.assertEqual(report["equations"], 2)
        self.assertEqual(report["tables"], 1)

    def test_unsupported_equation_falls_back_to_text(self):
        model = sample_model()
        model["document"]["pages"][0]["blocks"][1]["mathir"] = {"schemaVersion": "1.0", "root": {"type": "teleport"}}
        data, report = build_docx(model)
        self.assertEqual(report["equation_fallbacks"], 1)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        self.assertEqual(xml.count("<m:oMath"), 1)


if __name__ == "__main__":
    unittest.main()
