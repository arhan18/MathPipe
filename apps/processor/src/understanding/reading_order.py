"""Stage 6 — reading order incl. two-column detection (§15.1 baseline).

Strategy: detect column candidates from inter-block gaps, assign blocks to
columns, order within columns top-to-bottom, resolve full-width spanning
blocks first. Geometric position and logical order stay separate fields.
"""
from __future__ import annotations

from .blocks import Block

#: Minimum share of the page's column-assigned words that the smaller
#: column must hold for two-column mode. Narrow margin-mark columns
#: ("(8 x 2)") beside a single-column body must not flip the whole page
#: into left-column-first ordering and push body blocks out of sequence.
_MIN_COLUMN_SHARE = 0.20


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _columns(blocks: list[Block], page_width: float) -> list[tuple[float, float]] | None:
    """Return column x-ranges, or None for single-column layout.

    Evidence: a wide gap between block horizontal centers PLUS real vertical
    overlap between a left and a right block (rules out stacked sections that
    merely have different indentations).
    """
    if len(blocks) < 2:
        return None
    centers = sorted((b.bbox[0] + b.bbox[2]) / 2 for b in blocks)
    best_gap = 0.0
    split = 0.0
    for a, b in zip(centers, centers[1:]):
        if b - a > best_gap:
            best_gap = b - a
            split = (a + b) / 2
    if best_gap < page_width * 0.12:
        return None
    left = [b for b in blocks if (b.bbox[0] + b.bbox[2]) / 2 < split]
    right = [b for b in blocks if (b.bbox[0] + b.bbox[2]) / 2 >= split]
    if not left or not right:
        return None
    heights = [(b.bbox[3] - b.bbox[1]) for b in left + right]
    min_height = min(heights) if heights else 0.0
    overlapped = any(
        _overlap(a.bbox[1], a.bbox[3], b.bbox[1], b.bbox[3]) >= max(min_height * 0.3, 20.0)
        for a in left
        for b in right
    )
    if not overlapped:
        return None
    left_words = sum(len(b.text.split()) for b in left)
    right_words = sum(len(b.text.split()) for b in right)
    total = left_words + right_words
    if total and min(left_words, right_words) < _MIN_COLUMN_SHARE * total:
        return None
    return [(0.0, split), (split, page_width)]


def order_blocks(blocks: list[Block], page_width: float) -> list[Block]:
    """Assign reading_order in place; returns blocks sorted in reading order."""
    if not blocks:
        return []
    cols = _columns(blocks, page_width)
    if cols is None:
        # Integer-point bucket: same-baseline blocks differing only by
        # extraction float noise (p1 "(C)" at 661.5 vs "(A)/(B)" at 661.7
        # swapped Q1 options; Q11 "(B)" before "(A)") order by x0, not by
        # epsilon top. Distinct body rows differ by >=10pt so integer
        # bucketing keeps them distinct.
        ordered = sorted(blocks, key=lambda b: (round(b.bbox[1]), b.bbox[0]))
    else:
        (c0, c1) = cols
        mid = (c0[1] + c1[0]) / 2
        spanning = [b for b in blocks if b.bbox[0] < mid - 20 and b.bbox[2] > mid + 20]
        rest = [b for b in blocks if b not in spanning]
        left = sorted([b for b in rest if (b.bbox[0] + b.bbox[2]) / 2 < mid], key=lambda b: (round(b.bbox[1]), b.bbox[0]))
        right = sorted([b for b in rest if (b.bbox[0] + b.bbox[2]) / 2 >= mid], key=lambda b: (round(b.bbox[1]), b.bbox[0]))
        # Deterministic rule: full-width spanning blocks (titles) first by y,
        # then left column top-to-bottom, then right column.
        ordered = sorted(spanning, key=lambda b: round(b.bbox[1])) + left + right
    for i, b in enumerate(ordered, start=1):
        b.reading_order = i
    return ordered
