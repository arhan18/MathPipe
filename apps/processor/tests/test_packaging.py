"""Packaging hygiene: our module names must never shadow stdlib or
third-party top-level packages (regressions: `math`, `docx`)."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestNoShadowing(unittest.TestCase):
    def test_stdlib_math_intact(self):
        import math

        self.assertTrue(hasattr(math, "log"))
        self.assertFalse(math.__file__.endswith(os.path.join("src", "mathengine", "__init__.py")))

    def test_python_docx_importable(self):
        from docx import Document

        self.assertTrue(callable(Document))

    def test_our_packages_importable(self):
        from src.mathengine import mathir
        from src.word import omml

        self.assertTrue(callable(mathir.wrap))
        self.assertTrue(callable(omml.render_omath))


if __name__ == "__main__":
    unittest.main()
