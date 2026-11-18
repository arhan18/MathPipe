"""Stage 2 — document classification: BORN_DIGITAL / SCANNED / HYBRID / UNKNOWN (§6).

Heuristic over native text coverage per page. Cheap and deterministic; the ML
layout stage refines per-block evidence later. MVP optimizes BORN_DIGITAL.
"""
from __future__ import annotations

from dataclasses import dataclass

import pdfplumber

#: A page with at least this many extractable chars counts as digital.
DIGITAL_CHAR_THRESHOLD = 40


@dataclass(frozen=True)
class PageSignal:
    page_number: int
    chars: int
    has_images: bool
    digital: bool


@dataclass(frozen=True)
class Classification:
    label: str  # BORN_DIGITAL | SCANNED | HYBRID | UNKNOWN
    pages: list[PageSignal]


def classify_pdf(path: str) -> Classification:
    signals: list[PageSignal] = []
    try:
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
                chars = len(text.strip())
                try:
                    has_images = bool(page.images)
                except Exception:
                    has_images = False
                signals.append(PageSignal(i, chars, has_images, chars >= DIGITAL_CHAR_THRESHOLD))
    except Exception:
        return Classification("UNKNOWN", [])

    if not signals:
        return Classification("UNKNOWN", [])
    digital = sum(1 for s in signals if s.digital)
    if digital == len(signals):
        label = "BORN_DIGITAL"
    elif digital == 0:
        label = "SCANNED"
    else:
        label = "HYBRID"
    return Classification(label, signals)
