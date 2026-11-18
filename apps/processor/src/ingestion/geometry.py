"""Stage 3 — page geometry (§7): dimensions, rotation, text/figure presence."""
from __future__ import annotations

from dataclasses import dataclass

import pdfplumber


@dataclass(frozen=True)
class PageGeometry:
    page_number: int
    width: float
    height: float
    rotation: int
    has_text: bool
    image_count: int


def page_geometry(path: str) -> list[PageGeometry]:
    out: list[PageGeometry] = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            try:
                images = page.images
            except Exception:
                images = []
            try:
                words = page.extract_words() or []
            except Exception:
                words = []
            out.append(
                PageGeometry(
                    page_number=i,
                    width=float(page.width),
                    height=float(page.height),
                    rotation=int(getattr(page, "rotation", 0) or 0),
                    has_text=len(words) > 0,
                    image_count=len(images),
                )
            )
    return out
