"""Stage 5 — block segmentation: words → lines → blocks (§7).

Deterministic baseline. ML layout models (Marker/Docling candidates) replace
or refine this stage after the benchmark; the output contract is unchanged.

Table recovery: consecutive word rows with aligned multi-column geometry
(frequency tables, bordered price lists) and bracket-delimited matrix rows
are emitted as ``kind="table"`` blocks carrying ``extra["table"] =
{"rows": [[cell, ...], ...]}``. The DocumentModel passes ``extra`` through
and the DOCX builder renders native ``w:tbl``. Ambiguous regions stay text:
a run must satisfy dimension gates (2-col runs need ≥3 rows, 2-row runs
need ≥3 columns), column-center alignment, and must not be an option/label
list. Cell content is joined verbatim — never invented.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

from ..mathengine.normalize import despace_function_names
from .tables import Cell, Rule, detect_header_rows, detect_ruled_tables, find_caption
from .text import PageText, Word, fraction_stack_protected, is_furniture_line


#: Vertical tolerance as a fraction of type size for grouping words into
#: one visual line. Anchored to the SMALLER of the two sizes: oversized
#: outlier glyphs (diagonal copy-stamps, marginalia) must not widen the
#: tolerance and bridge two distinct body rows into token salad.
_LINE_TOL = 0.6

#: Words this much larger than the page median type size, consisting of at
#: most _OUTLIER_MAX_CHARS characters, are page furniture (repeated
#: anti-copy watermarks, stamp codes) — not reading content. They are
#: excluded before line grouping so they cannot glue body rows together.
_OUTLIER_SIZE_FACTOR = 2.0
_OUTLIER_MAX_CHARS = 2

#: Vertical overlap tolerated when accumulating lines into a block, as a
#: fraction of the previous line's mean size. Sub/superscripts and tall
#: math glyphs slightly overlap the next line; only a larger overlap
#: starts a new block (previously ANY overlap split, shredding equations).
_BLOCK_OVERLAP_SLACK = 0.5


@dataclass
class Block:
    id: str
    kind: str  # paragraph | heading | equation | table
    page_number: int
    bbox: list[float]  # [x0, top, x1, bottom]
    text: str
    size: float
    bold: bool
    confidence: float
    reading_order: int = 0
    extra: dict = None  # type: ignore[assignment]  # recognizer payload (latex, mathir, number...) or {"table": {"rows": ...}}

    def __post_init__(self):
        if self.extra is None:
            self.extra = {}


def _same_line(a: Word, b: Word) -> bool:
    vgap = abs(((a.top + a.bottom) / 2) - ((b.top + b.bottom) / 2))
    return vgap <= min(max(a.size, 1.0), max(b.size, 1.0)) * _LINE_TOL


def _anchor(row: list[Word]) -> Word:
    """Row representative: the word at the median vertical center.

    Comparing a candidate against the row baseline (not the most recently
    appended word) stops chaining, where each merge walks the tolerance
    window down the page and glues unrelated rows via outlier glyphs.
    """
    return sorted(row, key=lambda w: (w.top + w.bottom) / 2)[len(row) // 2]


#: Words sharing x within this tolerance are a vertical stack (dy over dx),
#: not left-to-right prose: float noise alone must not decide their order.
_X_TIE_PT = 2.0

#: Minimum vertical separation for a tie-break swap (same-baseline jitter
#: never reorders).
_TOP_EPS = 0.5

#: Stacked differentials ("dy" over "dx"): the ONLY pair the tie-break may
#: reorder. A generic top-first rule corrupts postfix accents ("i ˆ" → "ˆ i"),
#: vector marks ("u r" → "r u") and same-baseline jitter ("S R" → "R S"):
#: those keep geometric x0 order. Differentials are two-character words
#: that are never superscript accents, and a vertical stack of them is
#: always a derivative fraction, so top-first (numerator first) is exact.
_DIFFERENTIAL_RE = re.compile(r"^d[xyztuvw]$")


def _order_row(row: list[Word]) -> list[Word]:
    """Left-to-right word order with a surgical tie-break for stacked
    differentials.

    Stacked "dy" (top) / "dx" (bottom) at near-identical x must serialize
    numerator-first: pure x0 sorting inverts them to "dx dy" whenever the
    denominator's x0 is fractionally smaller (observed: 0.06pt), flipping
    the derivative's meaning. Near-ties between differentials therefore
    defer to vertical position; every other pair keeps geometric x0 order.
    """
    ordered = sorted(row, key=lambda w: w.x0)
    for _ in range(len(ordered)):
        swapped = False
        for i in range(len(ordered) - 1):
            a, b = ordered[i], ordered[i + 1]
            if (
                abs(a.x0 - b.x0) <= _X_TIE_PT
                and a.top - b.top > _TOP_EPS
                and _DIFFERENTIAL_RE.match(a.text)
                and _DIFFERENTIAL_RE.match(b.text)
            ):
                ordered[i], ordered[i + 1] = b, a
                swapped = True
        if not swapped:
            break
    return ordered


def _median_size(words: list[Word]) -> float:
    sizes = sorted(w.size for w in words if w.size > 0)
    return statistics.median(sizes) if sizes else 10.0


def _group_lines(words: list[Word]) -> list[list[Word]]:
    med = _median_size(words)
    words = sorted(words, key=lambda w: (w.top, w.x0))
    rows: list[list[Word]] = []
    for w in words:
        if rows and _same_line(_anchor(rows[-1]), w):
            rows[-1].append(w)
        else:
            rows.append([w])
    # Split rows on wide horizontal gaps (column gutters): each x-contiguous
    # segment becomes its own line so columns never merge into one line.
    # The gap reference is capped at the page median size so one oversized
    # glyph cannot inflate the threshold and pin unrelated fields together.
    lines: list[list[Word]] = []
    for row in rows:
        row = _order_row(row)
        segment = [row[0]]
        for prev, cur in zip(row, row[1:]):
            gap = cur.x0 - prev.x1
            ref = min(max(prev.size, cur.size, 1), med) * 4.0
            if gap > max(ref, 40.0):
                lines.append(segment)
                segment = [cur]
            else:
                segment.append(cur)
        lines.append(segment)
    return lines


def _disjoint(a: list[Word], b: list[Word]) -> bool:
    """True when two lines share no horizontal span (side-by-side columns).

    On single-column pages the options region is two-column ((A)/(C) left,
    (B)/(D) right) while stems are full width, so no global gutter exists.
    For disjoint lines vertical overlap is column adjacency, not a block
    boundary: only a large downward drop splits. Overlapping lines keep the
    existing gap/overlap rule untouched.
    """
    return max(w.x1 for w in b) <= min(w.x0 for w in a) or min(
        w.x0 for w in b
    ) >= max(w.x1 for w in a)


def _column_split(lines: list[list[Word]], page_width: float) -> float | None:
    """X coordinate of the column gutter, or None for single-column text."""
    centers = sorted(((L[0].x0 + L[-1].x1) / 2) for L in lines if L)
    if len(centers) < 4:
        return None
    best_gap = 0.0
    split = 0.0
    for a, b in zip(centers, centers[1:]):
        if b - a > best_gap:
            best_gap = b - a
            split = (a + b) / 2
    if best_gap < page_width * 0.12:
        return None
    left = sum(1 for c in centers if c < split)
    if left < 2 or len(centers) - left < 2:
        return None
    crossing = sum(1 for L in lines if L and L[0].x0 < split - 10.0 and L[-1].x1 > split + 10.0)
    if crossing > len(lines) * 0.15:
        return None
    left_chars = sum(len(w.text) for L in lines if L and (L[0].x0 + L[-1].x1) / 2 < split for w in L)
    right_chars = sum(len(w.text) for L in lines if L and (L[0].x0 + L[-1].x1) / 2 >= split for w in L)
    total_chars = left_chars + right_chars
    if total_chars > 0 and min(left_chars, right_chars) < total_chars * 0.10:
        return None
    return split


# ---------------------------------------------------------------------------
# Table recovery (word-geometry only; no new dependencies).
# ---------------------------------------------------------------------------

#: Inter-word x-gap above which a new cell starts. Within-cell gaps
#: ("20 – 25", "Repairing cost (₹)") measure ≤4pt at 12pt type; between-cell
#: gaps in real tables measure ≥17pt; prose word gaps measure ≤5pt.
_CELL_GAP_PT = 10.0

#: Column-center alignment tolerance: stub column (labels vary in width)
#: vs data columns (numeric entries align within ~2pt).
_STUB_ALIGN_PT = 30.0
_DATA_ALIGN_PT = 15.0

#: Max vertical gap between consecutive rows of one table.
_ROW_GAP_PT = 40.0

#: A run of single-label-first-column rows is an option/question list, not
#: a table ("(a)", "21.", "(iii)" — but never bare "A"/"B" stubs).
_LABEL_RE = re.compile(r"^\(.*\)$|^[A-Za-z0-9]+[.):]$")

#: Option-led cell: "a) Singular matrix", "(A) sin", "A. real" — the row
#: belongs to an option list, not to a table. A bare letter ("A", "B") is
#: a data value and stays a value.
_OPTION_CELL_RE = re.compile(r"^\s*[\(\[]?[A-Da-d][\)\].:]")

#: Pure single-token matrix fences as emitted by pdfplumber.
_FENCE_LEFT = {"⎛", "⎜", "⎝", "[", "(", "⌈", "⌊"}
_FENCE_RIGHT = {"⎞", "⎟", "⎠", "]", ")", "⌉", "⌋"}
_FENCE_ANY = _FENCE_LEFT | _FENCE_RIGHT


def _row_group(words: list[Word]) -> list[list[Word]]:
    """Group words into rows by vertical overlap only (no x-gap splitting).

    Unlike :func:`_group_lines`, a row keeps all its columns together so
    tabular structure survives for detection.
    """
    ordered = sorted(words, key=lambda w: (w.top, w.x0))
    rows: list[list[Word]] = []
    for w in ordered:
        if rows and _same_line(_anchor(rows[-1]), w):
            rows[-1].append(w)
        else:
            rows.append([w])
    return [_order_row(r) for r in rows]


def _cell_threshold(row: list[Word]) -> float:
    """Per-row cell-split gap: scaled to the row's own spacing.

    Fixed thresholds fail both ways: p14's header packs data columns 7–9pt
    apart (a 10pt cut merges them and the table is missed), while sparse
    data rows ("A … ₹5000 … 20%") need a wide cut. Within-cell gaps
    ("20 – 25") stay ~3pt, so 1.8× the row median with a 6pt floor and a
    10pt ceiling separates cells without shredding prose.
    """
    if len(row) < 3:
        return _CELL_GAP_PT
    gaps = sorted(row[k + 1].x0 - row[k].x1 for k in range(len(row) - 1))
    median = gaps[len(gaps) // 2]
    return min(_CELL_GAP_PT, max(6.0, 1.8 * median))


def _split_cells(row: list[Word], gap: float | None = None) -> list[list[Word]]:
    if gap is None:
        gap = _cell_threshold(row)
    cells = [[row[0]]]
    for prev, cur in zip(row, row[1:]):
        if cur.x0 - prev.x1 > gap:
            cells.append([cur])
        else:
            cells[-1].append(cur)
    return cells


def _cell_text(cell: list[Word]) -> str:
    return " ".join(w.text for w in cell)


def _cell_center(cell: list[Word]) -> float:
    return (cell[0].x0 + cell[-1].x1) / 2


def _is_label_cell(text: str) -> bool:
    t = (text or "").strip()
    if _LABEL_RE.match(t):
        return True
    # An option-led cell ("a) ...", "(A) ...") makes the whole run an
    # option list, not a table.
    return bool(_OPTION_CELL_RE.match(t))


def _row_gap(a: list[Word], b: list[Word]) -> float:
    return b[0].top - max(w.bottom for w in a)


def _aligned(centers_a: list[float], centers_b: list[float]) -> bool:
    if len(centers_a) != len(centers_b) or len(centers_a) < 2:
        return False
    for j, (ca, cb) in enumerate(zip(centers_a, centers_b)):
        tol = _STUB_ALIGN_PT if j == 0 else _DATA_ALIGN_PT
        if abs(ca - cb) > tol:
            return False
    return True


def _grid_dimensions_ok(nrows: int, ncols: int, grid: list[list[str]]) -> bool:
    if ncols < 2 or nrows < 2:
        return False
    if ncols == 2 and nrows == 2:
        # A 2x2 block is a table only when every cell is numeric: an
        # (A)/(B)/(C)/(D) option grid aligns perfectly and is NOT a table.
        return all(_is_numeric_cell(c) for row in grid for c in row)
    if ncols == 2:
        return nrows >= 3
    return True


#: Column-center clustering tolerance for the borderless path: every cell
#: center of a run is clustered globally, so a row that splits one column
#: into two does not change the table's column count.
_COLUMN_CLUSTER_PT = 12.0

#: Inter-row gap inside a run: 1.8x the run's median row pitch (a fixed
#: 40pt cut splits tables whose rows are taller and merges tables whose
#: rows are shorter than the surrounding prose).
_RUN_GAP_FACTOR = 1.8

#: Floor for the adaptive inter-row gap.
_MIN_RUN_GAP_PT = 20.0


def _is_numeric_cell(text: str) -> bool:
    """True for a cell holding a plain number (no words, no option labels)."""
    t = (text or "").strip()
    if not t:
        return False
    return bool(re.fullmatch(r"[−–—-]?\d+(?:\.\d+)?%?", t))


def _run_gap_limit(rows: list[list[Word]], start: int, end: int) -> float:
    """Max gap between two rows of one run: 1.8x the run's median pitch.

    The fixed 40pt cut split tables whose rows are taller than the
    surrounding prose and merged tables whose rows are shorter; the run's
    own median row pitch adapts to both.
    """
    run = rows[start:end]
    pitches = sorted(
        float(b[0].top) - float(a[0].top) for a, b in zip(run, run[1:])
    )
    if not pitches:
        return _ROW_GAP_PT
    return max(_RUN_GAP_FACTOR * pitches[len(pitches) // 2], _MIN_RUN_GAP_PT)


def _grid_for_run(
    run: list[int], cell_list: list[list[list[Word]]], clusters: list[list[float]]
) -> list[list[str]]:
    """Rectangular grid for a run: one cell per global column."""
    ncol = len(clusters)
    centers = [(g[0] + g[-1]) / 2 for g in clusters]
    grid: list[list[str]] = []
    for k in run:
        cells = cell_list[k]
        if len(cells) == ncol:
            grid.append([_cell_text(c) for c in cells])
            continue
        buckets: list[list[Word]] = [[] for _ in range(ncol)]
        for cell in cells:
            cx = _cell_center(cell)
            best = min(range(ncol), key=lambda i: abs(centers[i] - cx))
            buckets[best].extend(cell)
        grid.append(
            [
                " ".join(w.text for w in sorted(b, key=lambda w: w.x0))
                for b in buckets
            ]
        )
    return grid


def _detect_grid_tables(
    rows: list[list[Word]],
) -> list[tuple[int, int, list[list[str]], list[int]]]:
    """Detect aligned-column runs. Returns (start, end, grid, header rows)."""
    n = len(rows)
    cell_list = [_split_cells(r) for r in rows]
    # Rows containing matrix fence tokens belong to the matrix path, not here.
    eligible = [
        len(c) >= 2 and not any(w.text in _FENCE_ANY for w in r)
        for r, c in zip(rows, cell_list)
    ]
    out: list[tuple[int, int, list[list[str]], list[int]]] = []
    i = 0
    while i < n:
        if not eligible[i]:
            i += 1
            continue
        centers = [_cell_center(c) for c in cell_list[i]]
        j = i + 1
        while (
            j < n
            and eligible[j]
            and _row_gap(rows[j - 1], rows[j]) <= _run_gap_limit(rows, i, j)
            and _aligned(centers, [_cell_center(c) for c in cell_list[j]])
        ):
            j += 1
        run = list(range(i, j))
        # Column count comes from ALL cell centers of the run, clustered
        # globally: a row that splits one column in two must not change the
        # table's shape.
        all_centers = sorted(
            _cell_center(c) for k in run for c in cell_list[k]
        )
        clusters = _cluster_1d(all_centers, _COLUMN_CLUSTER_PT) if all_centers else []
        ncol = len(clusters)
        grid = _grid_for_run(run, cell_list, clusters)
        first_cells = [_cell_text(cell_list[k][0]) for k in run]
        non_label = sum(1 for t in first_cells if not _is_label_cell(t))
        # An option grid ("(A) ... (B) ... (C) ... (D) ...") is not a table
        # wherever its labels sit: reject the whole run when any cell is
        # option-led.
        option_led = any(
            _is_label_cell(_cell_text(cell))
            for k in run
            for cell in cell_list[k]
        )
        # Option/question lists ((a)–(d) stacks, "21." stems) align like
        # tables: reject unless the run is led by non-labels. A long run
        # with several columns only needs one non-label row.
        label_ok = (
            not option_led
            and (non_label >= 2 or (non_label >= 1 and len(run) >= 3 and ncol >= 3))
        )
        # Real table rows are uniformly typeset. Consistency is checked PER
        # ROW: a bold header row must not disqualify the whole table.
        sizes_ok = all(
            max(w.size for w in rows[k]) - min(w.size for w in rows[k]) <= 2.0
            for k in run
        )
        if (
            _grid_dimensions_ok(len(run), ncol, grid)
            and label_ok
            and sizes_ok
        ):
            header = detect_header_rows(
                [
                    [Cell(row=0, col=j, span=1, words=list(cell)) for j, cell in enumerate(cell_list[k])]
                    for k in run
                ],
                _median_size([w for k in run for w in rows[k]]),
            )
            out.append((i, j - 1, grid, header))
            i = j
        else:
            i += 1
    return out


def _fence_words(row: list[Word]) -> tuple[list[Word], list[Word]]:
    left = [w for w in row if w.text in _FENCE_LEFT]
    right = [w for w in row if w.text in _FENCE_RIGHT]
    return left, right


def _inner_candidate(w: Word, left_edge: float, right_edge: float) -> bool:
    return (
        w.text not in _FENCE_ANY
        and w.x0 >= left_edge - 2.0
        and w.x1 <= right_edge + 2.0
        and (w.x1 - w.x0) <= 12.0
        and len(w.text) <= 3
    )


def _row_inner(row: list[Word], left_edge: float, right_edge: float) -> list[Word]:
    return [w for w in row if _inner_candidate(w, left_edge, right_edge)]


def _cluster_1d(values: list[float], gap: float) -> list[list[float]]:
    clusters = [[values[0]]]
    for v in values[1:]:
        if v - clusters[-1][-1] > gap:
            clusters.append([v])
        else:
            clusters[-1].append(v)
    return clusters


def _detect_matrix_tables(
    rows: list[list[Word]],
) -> list[tuple[int, int, list[list[str]], set[int]]]:
    """Detect bracket-matrix zones via fence columns.

    pdfplumber fragments one matrix row across sub-lines (inner numbers on
    one line, extensible "⎜ ⎟" pieces on neighbours), so per-row fence
    pairs never match. Instead: find consecutive rows carrying pure fence
    tokens at consistent left/right x-columns, then collect the small
    tokens strictly inside the fence range as grid entries grouped by
    y-row. Short outer labels ("A =") stay in the block text; grid cells
    stay pure. Returns (start, end, grid, data_rows).
    """
    n = len(rows)
    has_fence = [bool(_fence_words(r)[0] or _fence_words(r)[1]) for r in rows]
    out: list[tuple[int, int, list[list[str]], set[int]]] = []
    i = 0
    while i < n:
        if not has_fence[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and has_fence[j + 1] and _row_gap(rows[j], rows[j + 1]) <= _ROW_GAP_PT:
            j += 1
        span = list(range(i, j + 1))
        left_x = sorted((w.x0 + w.x1) / 2 for k in span for w in _fence_words(rows[k])[0])
        right_x = sorted((w.x0 + w.x1) / 2 for k in span for w in _fence_words(rows[k])[1])
        left_c = _cluster_1d(left_x, 8.0) if left_x else []
        right_c = _cluster_1d(right_x, 8.0) if right_x else []
        left_best = max(left_c, key=len) if left_c else []
        right_best = max(right_c, key=len) if right_c else []
        if len(left_best) >= 2 and len(right_best) >= 2 and max(left_best) < min(right_best):
            left_edge = (
                sum(w.x1 for k in span for w in _fence_words(rows[k])[0]) / len(left_x)
            )
            right_edge = (
                sum(w.x0 for k in span for w in _fence_words(rows[k])[1]) / len(right_x)
            )

            def _crossable(k: int) -> bool:
                # Fence rows, pure-inner rows (wobble-split numbers), or rows
                # with inner entries plus a short outer label ("A =").
                # Prose (many outside words) never crosses.
                row = rows[k]
                if _fence_words(row)[0] or _fence_words(row)[1]:
                    return True
                inner = _row_inner(row, left_edge, right_edge)
                return bool(inner) and len(row) - len(inner) <= 3

            # Grow into adjacent crossable rows (baseline wobble splits
            # numbers off their brackets); stop at prose (outside words).
            s, e = i, j
            while s - 1 >= 0 and _crossable(s - 1):
                if _row_gap(rows[s - 1], rows[s]) > _ROW_GAP_PT:
                    break
                s -= 1
            while e + 1 < n and _crossable(e + 1):
                if _row_gap(rows[e], rows[e + 1]) > _ROW_GAP_PT:
                    break
                e += 1
            zone = list(range(s, e + 1))
            inner_by_row = {k: _row_inner(rows[k], left_edge, right_edge) for k in zone}
            data = [k for k in zone if inner_by_row[k]]
            if len(data) >= 2:
                centers_all = sorted(
                    (w.x0 + w.x1) / 2 for k in data for w in inner_by_row[k]
                )
                clusters = _cluster_1d(centers_all, 8.0)
                bounds = [(min(g) + max(g)) / 2 for g in clusters]
                grid = []
                grid_rows = set()
                ok = len(bounds) >= 2
                if ok:
                    for k in data:
                        placed = [""] * len(bounds)
                        for w in inner_by_row[k]:
                            c = (w.x0 + w.x1) / 2
                            b = min(range(len(bounds)), key=lambda m: abs(bounds[m] - c))
                            if placed[b] or abs(bounds[b] - c) > 8.0:
                                ok = False
                                break
                            placed[b] = w.text
                        if not ok or any(p == "" for p in placed):
                            ok = False
                            break
                        grid.append(placed)
                        grid_rows.add(k)
                if ok:
                    out.append((s, e, grid, grid_rows))
                    i = e + 1
                    continue
        i = j + 1
    return out


def _table_block(
    page_number: int,
    index: int,
    rows: list[list[Word]],
    grid: list[list[str]],
    data_rows: set[int] | None = None,
    header_rows: list[int] | None = None,
) -> Block:
    flat = [w for r in rows for w in r]
    x0 = min(w.x0 for w in flat)
    top = min(w.top for w in flat)
    x1 = max(w.x1 for w in flat)
    bottom = max(w.bottom for w in flat)
    avg_size = sum(w.size for w in flat) / len(flat)
    if data_rows is None:
        text = " | ".join(" ".join(w.text for w in r) for r in rows)
    else:
        # Matrix rows may carry short outer labels ("A ="): keep every word
        # in the text so no content is lost, grid cells stay pure.
        text = " ".join(" ".join(w.text for w in r) for r in rows)
    table: dict = {"rows": grid}
    if header_rows:
        table["headerRows"] = list(header_rows)
    return Block(
        id=f"p{page_number}-t{index}",
        kind="table",
        page_number=page_number,
        bbox=[round(x0, 1), round(top, 1), round(x1, 1), round(bottom, 1)],
        text=text,
        size=round(avg_size, 1),
        bold=False,
        confidence=0.85,
        extra={"table": table},
    )


def _ruled_table_block(page_number: int, index: int, spec) -> Block:
    """Block for a table rebuilt from the PDF's own ruling lines.

    ``spec`` is a :class:`src.understanding.tables.RuledTable`: cell text,
    merged spans, header rows and per-cell borders. A structure that cannot
    be trusted is shipped as an image crop (``parseStatus``) instead of a
    broken grid.
    """
    flat = list(spec.words)
    if flat:
        x0 = min(w.x0 for w in flat)
        top = min(w.top for w in flat)
        x1 = max(w.x1 for w in flat)
        bottom = max(w.bottom for w in flat)
        avg_size = sum(w.size for w in flat) / len(flat)
    else:
        x0, top, x1, bottom = spec.bbox
        avg_size = 10.0
    text = " | ".join(" ".join(str(c) for c in row) for row in spec.rows)
    table: dict = {
        "rows": spec.rows,
        "spans": spec.spans,
        "headerRows": list(spec.header_rows),
        "borders": spec.borders,
        "columnWidths": list(spec.column_widths),
        "parseStatus": spec.parse_status,
    }
    if spec.fallback_reason:
        table["fallbackReason"] = spec.fallback_reason
    return Block(
        id=f"p{page_number}-t{index}",
        kind="table",
        page_number=page_number,
        bbox=[round(x0, 1), round(top, 1), round(x1, 1), round(bottom, 1)],
        text=text,
        size=round(avg_size, 1),
        bold=False,
        confidence=0.9,
        extra={"table": table},
    )


#: Line-sort bucket (decimals): same-baseline words whose tops differ only
#: by extraction float noise must order by x0, not by epsilon top.
#: Observed: "(B)" at 143.6319999 sorted before "(A)" at 143.6320000,
#: swapping Q11 options; same for Q13 "(D)" before "(C)".
#: Bucket is integer points: same-baseline rows differ by <1pt of float
#: noise (p1 "(C)" at 661.5 vs "(A)/(B)" at 661.7 swapped Q1 options),
#: while distinct body rows differ by ≥10pt, so integer bucketing keeps
#: rows distinct and orders ties by x0.
_LINE_SORT_ROUND = 0

#: Section headings start new logical units, reset question numbering and
#: are never merged into a question block (otherwise "Section -D" fuses
#: with "(1) E(X)=..." into one equation and the heading is lost in OMML).
_SECTION_LINE_RE = re.compile(
    r"^\s*(Section\s*-\s*[A-Za-z]?|Part\s*-?\s*[A-Za-z]?|SECTION\s+[A-Z])\b",
    re.IGNORECASE,
)
#: Sub-heads ("I. MCQ", "II. Very Short...", "Type-I]") behave like sections:
#: standalone, reset numbering, never merged into a question.
_ROMAN_HEAD_RE = re.compile(
    r"^\s*(?:[IVX]+\.\s|Type\s*-?\s*[IVX]+\b)",
    re.IGNORECASE,
)

#: Question labels: "12.", "Q. 12", "Q12.", "Q.1.", "Q2)", "23A",
#: "23 B", "26A.", "26B.", "(60)", "60)", "(1)", "1)", "6 )".
#: Bare letters ("(A)", "a)") are options, never questions (require digits).
#: The qn4 branch allows space before the delimiter ("6 )" in QueBank)
#: which otherwise merges Q5+Q6 into one mega-para. Trailing delimiter
#: branches require a word boundary (space/end) so equation fragments
#: ("1)𝑗̂" from "(2λ−1)𝑗̂", answer keys "1)C") never split a stem from
#: its options — each question's stem+options stays in one block.
_QUESTION_LINE_RE = re.compile(
    r"""^\s*(?:
      Q\.?\s*\(?(?P<qn1>\d{1,3})\s*(?P<ql1>[A-B])?[.\)]
    | Q\.?\s*\(?(?P<qn2>\d{1,3})(?=\s|$)
    | \(?(?P<qn3>\d{1,3})\)[.\)]?(?=\s|$)
    | \(?(?P<qn4>\d{1,3})\s*[.\)](?=\s|$)
    | (?P<qn5>\d{1,3})\s*(?P<ql5>[A-B])\.?(?=\s|$)
    )""",
    re.IGNORECASE | re.VERBOSE,
)

#: Chapter headings ("6. LINES AND PLANE") look like "6." questions but are
#: all-caps short titles. They are sections, not questions.
_CHAPTER_REST_RE = re.compile(r"^[A-Z0-9\s&,\-–—/()]+$")

#: Paren MCQ options for post-segmentation label sorting (A<B<C<D).
_OPTION_PAREN_RE = re.compile(r"\(([A-D])\)")
#: Lowercase letter options ("a) ... b) ...") — same guard, case-insensitive.
_OPTION_LETTER_RE = re.compile(r"(?<![A-Za-z0-9])([A-Da-d])[).](?=\s|$)")


def _line_text(line: list[Word]) -> str:
    return " ".join(w.text for w in line)


def _is_section_line(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if _SECTION_LINE_RE.match(t):
        return True
    if _ROMAN_HEAD_RE.match(t):
        return True
    return False


def _parse_question_start(text: str) -> tuple[int, str | None, bool] | None:
    """Parse a line-start question label -> (number, letter, has_Q) or None."""
    m = _QUESTION_LINE_RE.match(text)
    if not m:
        return None
    num: int | None = None
    for g in ("qn1", "qn2", "qn3", "qn4", "qn5"):
        v = m.group(g)
        if v is not None:
            try:
                num = int(v)
            except ValueError:
                return None
            break
    if num is None:
        return None
    letter = m.group("ql1") or m.group("ql5")
    letter = letter.upper() if letter else None
    stripped = text.lstrip()
    has_q = stripped[:1].upper() == "Q"
    # Chapter headings ("6. LINES AND PLANE"): all-caps short rest -> section.
    rest = text[m.end():].strip()
    if not has_q and letter is None and rest and len(rest) <= 60 and _CHAPTER_REST_RE.match(rest):
        return None
    return (num, letter, has_q)


def _is_new_question(
    parsed: tuple[int, str | None, bool] | None,
    current_num: int | None,
    current_letter: str | None,
    text: str = "",
) -> bool:
    """True when a line-start label opens a new question block.

    Strong labels (Q-prefix, letter suffix like "23A"/"26B.", or an
    explicit "./)" delimiter like "12.", "1)", "(60)", "6 )") always
    start a new block. This splits mega-paras (Q28+29+30, Q23+Q24,
    Q32-OR+Q33, QueBank 5)+6), 1)-4) stacks) and same-number duplicates
    (visually-impaired variants "30."/"30", "28A" after "28B") even when
    two-column extraction emits them out of numeric order. Bare numbers
    alone (marks-column "2", split number "22") stay monotonic so marks
    never shred into fake questions: bare-with-prose ("30 For ...")
    splits on >= (duplicates), bare-alone splits only on strict increase.
    """
    if parsed is None:
        return False
    num, letter, has_q = parsed
    if has_q:
        return True
    if current_num is None:
        return True
    if letter is not None:
        return True
    stripped = text.lstrip()
    if re.match(r"^\(?\d{1,3}\s*[.\)](?=\s|$)", stripped):
        return True
    mnum = re.match(r"^\s*\(?(\d{1,3})\)?\s*", text)
    rest = text[mnum.end():].strip() if mnum else ""
    if rest:
        return num >= current_num
    return num > current_num


def _sort_options_in_text(text: str) -> str:
    """Sort a contiguous option run by label (A<B<C<D), stem fixed first.

    Only fires on clean 2-4 label runs with unique labels (each once).
    Duplicate labels ("(A) Both (A) and (R)...") are prose references,
    never reordered. Denominators stay with their option chunk because each
    chunk runs until the next label.
    """
    for pat in (_OPTION_PAREN_RE, _OPTION_LETTER_RE):
        matches = list(pat.finditer(text))
        if not 2 <= len(matches) <= 4:
            continue
        letters = [mm.group(1).upper() for mm in matches]
        if set(letters) - set("ABCD"):
            continue
        if len(set(letters)) != len(letters):
            continue
        if letters == sorted(letters):
            continue
        # Require all matches in the same style run: no question labels
        # between first and last option (options belong to one question).
        prefix = text[: matches[0].start()]
        chunks = []
        for i, mm in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            chunks.append((mm.group(1).upper(), text[mm.start(): end]))
        chunks.sort(key=lambda c: c[0])
        return prefix + "".join(c[1] for c in chunks)
    return text


def _looks_like_math_fragment(text: str) -> bool:
    t = text.strip()
    if not t or len(t.split()) > 14:
        return False
    if re.match(r"^(?:[a-zA-Z]|[ivxIVX]{1,4})\)\s", t):
        return False
    return bool(
        re.search(r"[=∫∑∏√∞Δ∂∇±×÷≠≤≥≈≡∈∉∪∩^_⁄⎛⎜⎝⎞⎟⎠{}\[\]|]", t)
        or re.search(r"[+\-−–—]", t)
        or re.match(r"^[\d\sxXyYzZ.,/()]+$", t)
    )


def _regroup_question_blocks(
    page_number: int,
    blocks_lines: list[tuple[list[list[Word]], Block]],
    body_size: float,
) -> list[Block]:
    """Split mega-paras on question labels; merge stem+options per question.

    - Each question label starts a new question (monotonic numbers; "Q."-
      prefixed always new; section headings reset numbering so "(1)" after
      "Section -D" is new while "1)" inside Q13 is a "(2λ-1)" fragment).
    - Non-label lines (options continuations, "OR", equation fragments,
      denominators) attach to the current question, keeping stem+options in
      one block.
    - Leading orphans before the first question: math fragments prepend to
      the first question (label-first reordered); prose headers stay
      standalone.
    - Section headings are standalone and never merged.
    - Within each question, label-first reordering guarantees the question
      number is never emitted mid-equation, and option runs sort A<B<C<D.
    """
    # Fast path: pages with no sections/questions (two-column fixtures,
    # worksheets without numbering) keep geometric blocks untouched to
    # preserve column separation. Option runs still sort post-segmentation.
    has_structured = False
    for _lines, _b in blocks_lines:
        for _ln in _lines:
            _t = _line_text(_ln)
            if _is_section_line(_t) or _parse_question_start(_t) is not None:
                has_structured = True
                break
        if has_structured:
            break
    if not has_structured:
        out0: list[Block] = []
        for _lines, b in blocks_lines:
            b.text = _sort_options_in_text(b.text)
            out0.append(b)
        return sorted(out0, key=lambda b: (round(b.bbox[1], _LINE_SORT_ROUND), b.bbox[0]))
    ordered = sorted(blocks_lines, key=lambda bl: (round(bl[1].bbox[1], _LINE_SORT_ROUND), bl[1].bbox[0]))
    out: list[Block] = []
    current_lines: list[list[Word]] | None = None
    current_num: int | None = None
    current_letter: str | None = None
    pending_orphans: list[list[Word]] = []
    q_index = 0

    def _flush_current() -> None:
        nonlocal current_lines, current_num, current_letter, q_index
        if not current_lines:
            return
        # Label-first: leading math fragments (tall-equation tops sorted
        # before their label) move after the label so the number is never
        # mid-equation ("x x 2..." before "23.", "⎧..." before "24.").
        label_idx: int | None = None
        for i, ln in enumerate(current_lines):
            if _parse_question_start(_line_text(ln)) is not None:
                label_idx = i
                break
        use_lines = current_lines
        if label_idx is not None and label_idx > 0:
            use_lines = (
                [current_lines[label_idx]]
                + current_lines[:label_idx]
                + current_lines[label_idx + 1 :]
            )
        blk = _flush(page_number, 900 + q_index, use_lines, body_size)
        blk.id = f"p{page_number}-q{q_index}"
        blk.text = _sort_options_in_text(blk.text)
        out.append(blk)
        q_index += 1
        current_lines = None

    def _flush_orphans_standalone() -> None:
        nonlocal pending_orphans, q_index
        if not pending_orphans:
            return
        blk = _flush(page_number, 700 + q_index, pending_orphans, body_size)
        blk.id = f"p{page_number}-h{q_index}"
        out.append(blk)
        q_index += 1
        pending_orphans = []

    def _flush_orphan_groups(lines_list: list[list[Word]]) -> None:
        nonlocal q_index
        if not lines_list:
            return
        groups: list[list[list[Word]]] = [[lines_list[0]]]
        for ln in lines_list[1:]:
            prev_bot = max((w.bottom for w in groups[-1][-1]), default=0.0)
            cur_top = min((w.top for w in ln), default=0.0)
            if cur_top - prev_bot <= body_size * 1.0:
                groups[-1].append(ln)
            else:
                groups.append([ln])
        for grp in groups:
            blk = _flush(page_number, 700 + q_index, grp, body_size)
            blk.id = f"p{page_number}-h{q_index}"
            out.append(blk)
            q_index += 1

    for lines, _blk in ordered:
        # Split one initial block's lines on section/question starts so a
        # gap-merged mega-para (28+29+30, 23+24, 32-OR+33) separates.
        segments: list[tuple[str, list[list[Word]]]] = []
        cur_seg: list[list[Word]] = []
        cur_kind = "orphan"
        for ln in lines:
            t = _line_text(ln)
            if _is_section_line(t):
                if cur_seg:
                    segments.append((cur_kind, cur_seg))
                segments.append(("section", [ln]))
                cur_seg = []
                cur_kind = "orphan"
                continue
            parsed = _parse_question_start(t)
            if parsed is not None and _is_new_question(parsed, current_num, current_letter, t):
                if cur_seg:
                    segments.append((cur_kind, cur_seg))
                cur_seg = [ln]
                cur_kind = "question"
                # Reserve numbering now so later fragments on this page compare
                # against the latest question even before flushing.
                current_num, current_letter = parsed[0], parsed[1]
                # _is_new_question used provisional numbering; keep it.
                continue
            # Continuation (options, OR, fragments, denominators).
            if cur_kind == "question":
                cur_seg.append(ln)
            else:
                cur_seg.append(ln)
        if cur_seg:
            segments.append((cur_kind, cur_seg))

        for kind, seg in segments:
            if kind == "section":
                _flush_current()
                # Pending orphans before a section heading belong to the
                # preceding section, never across the heading to the next.
                _flush_orphan_groups(pending_orphans)
                pending_orphans = []
                # Section heading standalone; resets numbering.
                blk = _flush(page_number, 800 + q_index, seg, body_size)
                blk.id = f"p{page_number}-s{q_index}"
                if blk.kind != "heading":
                    blk.kind = "heading" if len(blk.text) < 160 else blk.kind
                out.append(blk)
                q_index += 1
                current_lines = None
                current_num = None
                current_letter = None
            elif kind == "question":
                # New question: flush previous, prepend pending math orphans.
                _flush_current()
                if pending_orphans:
                    q_top = min((w.top for w in seg[0]), default=0.0) if seg and seg[0] else 0.0
                    math_pre = [
                        o for o in pending_orphans
                        if _looks_like_math_fragment(_line_text(o))
                        and o
                        and 0.0 <= (q_top - max(w.bottom for w in o)) <= 45.0
                    ]
                    prose_pre = [o for o in pending_orphans if o not in math_pre]
                    _flush_orphan_groups(prose_pre)
                    current_lines = list(math_pre) + list(seg)
                    pending_orphans = []
                else:
                    current_lines = list(seg)
                # current_num already set provisionally above; re-derive from
                # the segment's label to stay exact.
                parsed0 = _parse_question_start(_line_text(seg[0]))
                if parsed0 is not None:
                    current_num, current_letter = parsed0[0], parsed0[1]
            else:  # orphan continuation
                if current_lines is not None:
                    # Guard against block-order inversion: a mega initial
                    # block (bbox top = min line) sorts before small early
                    # blocks, so an earlier-y orphan ("Time: 3 hours" at 95)
                    # would otherwise attach to a later question ("1.
                    # Identify" at 519) and drag its bbox/text across the
                    # page. Earlier-y orphans flush standalone instead.
                    try:
                        cur_top = min(w.top for ln in current_lines for w in ln)
                        seg_top = min(w.top for ln in seg for w in ln)
                    except ValueError:
                        cur_top = seg_top = 0.0
                    if seg_top + 5.0 < cur_top:
                        blk = _flush(page_number, 700 + q_index, seg, body_size)
                        blk.id = f"p{page_number}-h{q_index}"
                        out.append(blk)
                        q_index += 1
                    else:
                        current_lines.extend(seg)
                else:
                    pending_orphans.extend(seg)
    _flush_current()
    # Trailing orphans with no question (page of pure headers/answers):
    # keep as standalone, never dropped.
    if pending_orphans:
        # If orphans hold multiple questions missed by monotonic (answer keys
        # on one line), keep them together — splitting answer keys shreds.
        blk = _flush(page_number, 700 + q_index, pending_orphans, body_size)
        blk.id = f"p{page_number}-h{q_index}"
        out.append(blk)
    return sorted(out, key=lambda b: (round(b.bbox[1], _LINE_SORT_ROUND), b.bbox[0]))


# ---------------------------------------------------------------------------
# Piecewise (cases) braces: ⎧ ⎨ ⎩ stacks.
# ---------------------------------------------------------------------------
# A left brace set as Symbol pieces comes out as three one-glyph words at one
# x, with the case rows (set at the brace's own size) interleaved by y with
# the surrounding 12pt prose: the first case row lands ABOVE the question
# line (so it is appended to the previous question) and the middle/bottom
# pieces pair as a fake "(⎨5–x)/⎩" fraction. Collapse each stack plus its
# case rows into ONE word anchored at the middle piece: "{ r1 ; r2".

_BRACE_TOP = "⎧"
_BRACE_MID = frozenset({"⎨", "⎪"})
_BRACE_BOT = "⎩"


def _collapse_piecewise(words: list[Word]) -> list[Word]:
    tops = [w for w in words if (w.text or "").strip() == _BRACE_TOP]
    if not tops:
        return words
    consumed: set[int] = set()
    synthetic: list[Word] = []
    for top in tops:
        if id(top) in consumed or not top.size:
            continue
        pieces = [top]
        bottom = None
        for w in sorted(words, key=lambda w: w.top):
            if id(w) in consumed or w is top:
                continue
            t = (w.text or "").strip()
            if t not in _BRACE_MID and t != _BRACE_BOT:
                continue
            if abs(w.x0 - top.x0) > 1.5 or w.top < top.top:
                continue
            if w.top - pieces[-1].bottom > top.size * 0.6:
                break
            pieces.append(w)
            if t == _BRACE_BOT:
                bottom = w
                break
        if bottom is None or len(pieces) < 3:
            continue
        piece_ids = {id(p) for p in pieces}
        span_top = top.top - 2.0
        span_bot = bottom.bottom + 2.0
        row_words = [
            w for w in words
            if id(w) not in piece_ids and id(w) not in consumed
            and w.size and abs(w.size - top.size) <= 0.6
            and w.x0 >= top.x0 - 0.5
            and w.top >= span_top and w.bottom <= span_bot
        ]
        if not row_words:
            continue
        row_words.sort(key=lambda w: (w.top, w.x0))
        rows: list[list[Word]] = []
        for w in row_words:
            if rows and abs(w.top - rows[-1][0].top) <= 3.0:
                rows[-1].append(w)
            else:
                rows.append([w])
        text = "{ " + " ; ".join(
            " ".join(x.text for x in sorted(r, key=lambda w: w.x0)) for r in rows
        )
        mids = [p for p in pieces if p is not top and p is not bottom]
        anchor = mids[0] if mids else top
        synthetic.append(Word(
            text=text,
            x0=top.x0, top=anchor.top,
            x1=max(w.x1 for w in row_words), bottom=anchor.bottom,
            fontname=row_words[0].fontname, size=top.size,
        ))
        consumed.update(piece_ids)
        consumed.update(id(w) for w in row_words)
    if not synthetic:
        return words
    return [w for w in words if id(w) not in consumed] + synthetic


def segment_blocks(page: PageText, rules: list[Rule] | None = None) -> list[Block]:
    if not page.words:
        return []
    try:
        collapsed = _collapse_piecewise(page.words)
    except Exception:
        collapsed = page.words
    if collapsed is not page.words:
        page = PageText(page.page_number, page.width, page.height, collapsed)
    med_all = _median_size(page.words)
    # Drop oversized tiny glyphs (repeated watermark/stamp codes) before
    # grouping: they sit on body baselines and would otherwise pin
    # unrelated words into one row. Multi-character display type (real
    # headings) is always kept. A tiny oversized token that shares its
    # baseline with same-size neighbours ("30" beside "Sets" at 32pt,
    # ":" inside "Class : 12th" at 40pt) is heading content, not a stamp:
    # stamps sit alone among body-size words, headings sit among display
    # words. Only isolated outliers are dropped.
    def _isolated_outlier(w: Word) -> bool:
        if not (w.size > _OUTLIER_SIZE_FACTOR * med_all and len(w.text.strip()) <= _OUTLIER_MAX_CHARS):
            return False
        try:
            for o in page.words:
                if o is w:
                    continue
                if not o.size or o.size < 1.5 * med_all:
                    continue
                vgap = abs(((w.top + w.bottom) / 2) - ((o.top + o.bottom) / 2))
                if vgap > min(max(w.size, 1.0), max(o.size, 1.0)) * _LINE_TOL:
                    continue
                gap = min(abs(w.x0 - o.x1), abs(o.x0 - w.x1))
                # Overlapping spans (negative gap via min) count as adjacent.
                if gap <= 20.0:
                    return False
        except Exception:
            return True
        return True

    words = [w for w in page.words if not _isolated_outlier(w)]
    # Robust body size: median of ALL words (12pt on SQP p7). The unique-size
    # median collapses to 8.5pt on fraction-dense pages, making true 8.5pt
    # operands look full-size so stacked fractions never pair (Q33A/B).
    try:
        body_size = _median_size(words)
    except Exception:
        sizes = sorted({w.size for w in words if w.size > 0})
        body_size = sizes[len(sizes) // 2] if sizes else 10.0

    # Table recovery runs on y-grouped rows before the x-gap gutter split
    # (which would shred column structure into separate lines).
    rows = _row_group(page.words)
    consumed: set[int] = set()
    tables: list[Block] = []
    # Ruled tables first: the PDF's own ruling lines are the strongest
    # evidence there is. A bordered grid survives irregular columns and a
    # spanning header that word geometry can never align (SQP p1).
    if rules:
        for spec in detect_ruled_tables(
            rules, words, page.width, page.height, body_size
        ):
            block = _ruled_table_block(page.page_number, len(tables), spec)
            consumed.update(id(w) for w in spec.words)
            # Caption binding: a caption line above/below the table belongs
            # to the table, never to the body text.
            free = [w for w in words if id(w) not in consumed]
            caption = find_caption(free, spec.bbox)
            if caption is not None:
                text, side, cap_words = caption
                block.extra["table"]["caption"] = text
                block.extra["table"]["captionPosition"] = side
                consumed.update(id(w) for w in cap_words)
            tables.append(block)
    remaining_idx = [k for k in range(len(rows)) if not any(id(w) in consumed for w in rows[k])]
    rem_rows = [rows[k] for k in remaining_idx]
    for start, end, grid, data_rows in _detect_matrix_tables(rem_rows):
        run_rows = rem_rows[start : end + 1]
        tables.append(_table_block(page.page_number, len(tables), run_rows, grid, data_rows))
        consumed.update(id(w) for r in run_rows for w in r)
    remaining_idx = [k for k in range(len(rem_rows)) if not any(id(w) in consumed for w in rem_rows[k])]
    rem_rows2 = [rem_rows[k] for k in remaining_idx]
    for start, end, grid, header_rows in _detect_grid_tables(rem_rows2):
        run_rows = rem_rows2[start : end + 1]
        tables.append(
            _table_block(page.page_number, len(tables), run_rows, grid, None, header_rows)
        )
        consumed.update(id(w) for r in run_rows for w in r)

    words = [w for w in words if id(w) not in consumed]
    # Drop garbled running footers ("ContonueCooueen paueeeeeee", big2 59x)
    # and pure decorative C0 controls (Wingdings zero-width, Wingdings2 7x
    # separators) before grouping so they never form blocks (and never reach
    # the DOCX as U+FFFD). "OR" separators ("\x01R" -> "OR") survive for
    # _flush mapping; bottom-margin garble is furniture, mid-page separators
    # are vector scraps, both never content.
    try:
        _kept: list[Word] = []
        for w in words:
            try:
                _t = w.text or ""
            except Exception:
                _kept.append(w)
                continue
            if _t and all(ord(c) < 0x20 for c in _t.strip()):
                continue
            if ("Contonue" in _t or "paue" in _t) and w.top > page.height * 0.80:
                continue
            _kept.append(w)
        words = _kept
    except Exception:
        pass
    if not words:
        return sorted(tables, key=lambda b: (b.bbox[1], b.bbox[0]))
    lines = _group_lines(words)
    # Drop footer/folio lines that survived extraction (e.g. single-page
    # calls with no cross-page repetition signal): URL footers and lone
    # numeric folio pairs in the bottom margin band. Body math is never
    # numeric-only with long numbers, so it passes through untouched.
    # Stacked-fraction numerators/denominators ("1 1 1", "81 100 90")
    # mimic numeric folios but sit x-aligned within 20pt of their option
    # row — they are shielded here exactly as in extraction.
    try:
        _shielded = fraction_stack_protected(lines)
    except Exception:
        _shielded = set()
    lines = [
        ln for idx, ln in enumerate(lines)
        if idx in _shielded or not is_furniture_line(ln, page.height)
    ]
    if not lines:
        return sorted(tables, key=lambda b: (b.bbox[1], b.bbox[0]))
    gutter = _column_split(lines, page.width)

    def column_of(line: list[Word]) -> int:
        if gutter is None:
            return 0
        center = (line[0].x0 + line[-1].x1) / 2
        return 0 if center < gutter else 1

    # Process each column's lines independently (sorted top-to-bottom) so
    # interleaved y-positions across columns never merge into one block.
    by_column: dict[int, list[list[Word]]] = {}
    for line in lines:
        by_column.setdefault(column_of(line), []).append(line)

    blocks: list[Block] = []
    blocks_lines: list[tuple[list[list[Word]], Block]] = []
    for col in sorted(by_column):
        col_lines = sorted(by_column[col], key=lambda L: (round(L[0].top, _LINE_SORT_ROUND), L[0].x0))
        current: list[list[Word]] = []
        for line in col_lines:
            if current:
                prev_bottom = max(w.bottom for w in current[-1])
                gap = line[0].top - prev_bottom
                avg_size = sum(w.size for w in current[-1]) / len(current[-1])
                if _disjoint(current[-1], line):
                    if gap > avg_size * 1.6:
                        _b = _flush(page.page_number, len(blocks), current, body_size)
                        blocks.append(_b)
                        blocks_lines.append((list(current), _b))
                        current = []
                elif gap > avg_size * 1.6 or gap < -avg_size * _BLOCK_OVERLAP_SLACK:
                    _b = _flush(page.page_number, len(blocks), current, body_size)
                    blocks.append(_b)
                    blocks_lines.append((list(current), _b))
                    current = []
            current.append(line)
        if current:
            _b = _flush(page.page_number, len(blocks), current, body_size)
            blocks.append(_b)
            blocks_lines.append((list(current), _b))
    regrouped = _regroup_question_blocks(page.page_number, blocks_lines, body_size)
    if not tables:
        return regrouped
    return sorted(tables + regrouped, key=lambda b: (round(b.bbox[1], _LINE_SORT_ROUND), b.bbox[0]))


#: Denominator line: a lone integer or rooted integer (the fraction bar
#: leaves no text): "3", "√14".
_STACK_DEN_LINE_RE = re.compile(r"^(√\d+|\d+)$")
#: Numerator line: an optional option label plus a (possibly signed) integer
#: or rooted integer — "1", "−10", "− 10", "√3", "(B) 1", "(C) − 10", "(A) π".
#: The sign may be a separate word ("− 10"), so internal spacing is allowed.
#: Anything longer (stems, matrix rows, "dx 2") never participates.
_STACK_NUM_LINE_RE = re.compile(r"^(\([A-Za-z]\)\s*)?([−–—-]\s*)?(√\d+|\d+|π)$")
#: Standalone option label line between numerator and denominator: "(B)",
#: or a label carrying the fraction's sign ("(A) −" for options like −1/10).
_STACK_LABEL_RE = re.compile(r"^\([A-Za-z]\)$")
_STACK_SIGNED_LABEL_RE = re.compile(r"^(\([A-Za-z]\))\s*([−–—+])$")
#: The numerator word itself (last token of a numerator line).
_STACK_NUM_WORD_RE = re.compile(r"^(√\d+|[−–—-]?\d+|π)$")
#: Fractions occur in math context: the block must hold an option label or
#: a math operator, otherwise stacked bare numbers (vertical lists, stray
#: page furniture) are left alone.
_STACK_CONTEXT_RE = re.compile(r"\([A-Za-z]\)|[*/=^_+∫∑∏√∞≤≥≠±×÷]")


def _split_label_line(line: list[Word]) -> tuple[str | None, str]:
    """Split an option-label line into (label, sign).

    Returns (None, "") unless the line is a bare "(X)" or a label carrying
    the fraction's sign ("(A) −" for options like −1/10).
    """
    text = " ".join(w.text for w in line).strip()
    if len(line) == 1 and _STACK_LABEL_RE.match(text):
        return text, ""
    m = _STACK_SIGNED_LABEL_RE.match(text) if len(line) == 2 else None
    if m:
        return m.group(1), m.group(2)
    return None, ""


# ---------------------------------------------------------------------------
# Stacked-fraction pairing (generalized numerator/denominator attachment).
# ---------------------------------------------------------------------------
# Born-digital PDFs stack display fractions vertically with no "/" text:
# Q8/Q12 option grids ("π/4 − 1/2", "−1/10"), Q22 ("π/4", "x/2", "dy/dx"),
# Q23A ("(x−3)/(x−1)^3"), Q33B (trig fraction), maths2 contour fractions.
# This pass — like _attach_integral_limits — moves geometrically-identified
# denominator runs into their numerator's line as "num/den", consuming the
# originals so they cannot strand. Rules (honesty first):
# - BOTH runs small (< 90% of body size): full-size stacks are piecewise
#   cases (Q7 "x/x"), matrices or prose — never fractions.
# - Vertical adjacency (small drop) + horizontal center overlap.
# - Operand-shaped runs only: no relations (=<>≤≥), no labels, no debris
#   (hat-soup, fence litter), no prose words; single-letter num==den refused.
# - Integral bound slots (directly above/below ∫∑∏ within bound tolerance)
#   are limits, never fractions.
# - A detached option label carrying the sign ("(A) −" on its own short
#   line) re-attaches at the label's position, preserving row-major order.
#   Shared label bands (Q8's "(A) − (B) + …" row) are left alone: pairs emit
#   at their numerator columns and the operators stay in place.

#: Extra debris that must never pair as fraction operands (beyond
#: _LIMIT_DEBRIS): lone signs/operators and script markers.
_FRACTION_DEBRIS = frozenset({"", "+", "-", "*", "=", "^", "_", "/", "−", "–", "—"})

#: Function-name prefixes that make a long token mathematical ("log(1+x)",
#: "sinθ−2)cosθ"); anything else with a 3+ letter run is prose ("Evaluate").
_FRACTION_FUNCTION_RE = re.compile(r"^(sin|cos|tan|log|ln|sec|exp|dx|dy|dz|dθ|dt)")

#: Relation characters: a run holding one is a contour/equation, never a
#: fraction operand ("|z|=3", "x≤2").
_FRACTION_RELATION_RE = re.compile(r"[=<>≤≥≠≈≡∈∉∪∩→←⇒⇐⇔]")

#: Math evidence inside a long token (digits, operators, known symbols).
_FRACTION_MATH_RE = re.compile(r"[0-9∫∑∏√∞πθλμσφΔ∂∇^_(){}\[\]−–—+\-*/]")

#: A trailing smaller digit is a superscript ("(x−1) 3" → "(x−1)^{3}").
_FRACTION_SUP_RE = re.compile(r"^\d$")

#: Max bands to look down for a denominator (option grids interleave label
#: rows between numerators and denominators).
_FRACTION_MAX_GAP = 12

#: Max tokens per operand run ("(3", "sinθ−2)cosθ" pair; longer spans are
#: stems, not operands).
_FRACTION_RUN_TOKENS = 3

#: Max vertical drop (pt) from numerator bottom to denominator top. True
#: stacked fractions sit 4–6pt apart (8.5pt type); stem superscripts sit
#: 8pt+ above option numerators with no bar between. The old 1.6×size
#: window (13.6pt) admitted those fakes (Q12 "4/1", Q9 "2/(111)").
_FRACTION_DROP_MAX = 6.5


def _frac_word_eligible(w: Word, body_size: float) -> bool:
    """True when a word may belong to a stacked fraction operand run."""
    t = (w.text or "").strip()
    if not t or "/" in t:
        return False
    if t in _LIMIT_DEBRIS or t in _FRACTION_DEBRIS:
        return False
    if not (5.0 <= (w.size or 0.0) < body_size * 0.9):
        return False
    if t in _INTEGRAL_CHARS or _STACK_LABEL_RE.match(t):
        return False
    if _FRACTION_RELATION_RE.search(t):
        return False
    if len(re.sub(r"\s+", "", t)) > 14:
        return False
    # Long letter runs are prose unless they open with a function name or
    # carry math evidence ("sinθ−2)cosθ" vs "Evaluate").
    if re.search(r"[A-Za-z]{3,}", t) and not (
        _FRACTION_FUNCTION_RE.match(t) or _FRACTION_MATH_RE.search(t)
    ):
        return False
    return True


def _frac_cx(w: Word) -> float:
    return (w.x0 + w.x1) / 2


def _frac_cy(w: Word) -> float:
    return (w.top + w.bottom) / 2


def _frac_is_integral_bound(w: Word, ops: list[Word]) -> bool:
    """True when a word is an integral bound (limit), never a fraction operand.

    Same shape + geometry as _attach_integral_limits: single short token
    smaller than the operator and stacked directly above/below it. Such words
    (Q33A "1"/"0" around ∫) must not join fraction runs — otherwise the run
    absorbs the bound, shifts its center away from ∫ and escapes the slot
    veto, minting fakes like "(1log)/0".
    """
    try:
        t = (w.text or "").strip()
    except Exception:
        return False
    if not _is_limit_word(t):
        return False
    try:
        cx = (_frac_cx(w))
        cy = (_frac_cy(w))
    except Exception:
        return False
    for op in ops:
        try:
            if not op.size or not w.size:
                continue
            if not (w.size < op.size * 0.85 and w.size >= 5.0):
                continue
            if abs(_frac_cx(op) - cx) > max(10.0, op.size * 0.9):
                continue
            if abs(_frac_cy(op) - cy) <= op.size * 1.1:
                return True
        except Exception:
            continue
    return False


def _frac_in_integral_slot(
    pcx: float, ucy: float, vcy: float, ops: list[Word]
) -> bool:
    """True when a stacked pair sits in an ∫∑∏ bound slot (limits, not a
    fraction). Same tolerances as _attach_integral_limits so the two passes
    agree on what a bound looks like."""
    for op in ops:
        if not op.size:
            continue
        if abs(_frac_cx(op) - pcx) > max(10.0, op.size * 0.9):
            continue
        if abs(_frac_cy(op) - ucy) <= op.size * 1.1:
            return True
        if abs(_frac_cy(op) - vcy) <= op.size * 1.1:
            return True
    return False


def _frac_render_run(words: list[Word]) -> str:
    """Render an operand run: glue tokens, folding a smaller trailing digit
    into a superscript ("z 2" → "z^{2}", "(x−1) 3" → "(x−1)^{3}")."""
    parts: list[str] = []
    prev_size = 0.0
    for w in words:
        t = (w.text or "").strip()
        if (
            _FRACTION_SUP_RE.match(t)
            and parts
            and prev_size > 0
            and (w.size or 0.0) < prev_size * 0.85
            and not re.fullmatch(r"[−–—+]", parts[-1])
        ):
            parts.append("^{" + t + "}")
        else:
            if parts and re.fullmatch(r"[−–—+]", parts[-1]) :
                parts[-1] = parts[-1] + t
            else:
                parts.append(t)
        prev_size = w.size or 0.0
    return "".join(parts)


def _frac_wrap_operand(rendered: str, n_tokens: int) -> str:
    """Parenthesize multi-token or operator-bearing operands so "/" binds
    the whole run ("z+i" → "(z+i)"); already-grouped or atomic operands pass
    through. A stray leading "+" is dropped ("+4iz−4" → "(4iz−4)")."""
    t = rendered.strip()
    if t.startswith("+") and not t.startswith("++"):
        t = t[1:]
    if re.fullmatch(r"\(.*\)(\^\{[^}]*\})?", t, re.DOTALL):
        return t
    if n_tokens == 1 and not re.search(r"[+−–—]", t[1:]):
        return t
    return "(" + t + ")"


def _pair_stacked_fraction_runs(
    lines: list[list[Word]], body_size: float
) -> list[list[Word]]:
    """Pair stacked numerator/denominator runs into "num/den" words.

    Pure w.r.t. content (no words invented — the "/" is the fraction bar the
    PDF drew but left as untagged ink; paired words are consumed from their
    original lines). Returns rewritten lines; lines emptied by consumption
    are dropped.
    """
    n = len(lines)
    if n < 2:
        return lines
    # Robust body size: the unique-size median collapses to 8.5pt on pages
    # dense with fractions (SQP p7), making true 8.5pt operands look
    # full-size so nothing pairs. Median of all words stays at body (12pt).
    try:
        _flat_sizes = [w.size for _ln in lines for w in _ln if getattr(w, "size", 0) > 0]
        if _flat_sizes:
            _robust_body = statistics.median(_flat_sizes)
            if _robust_body > body_size:
                body_size = float(_robust_body)
    except Exception:
        pass
    line_text = [" ".join(w.text for w in line) for line in lines]
    has_context = bool(_STACK_CONTEXT_RE.search(" ".join(line_text)))
    if not has_context and not any(
        (m := _STACK_NUM_LINE_RE.match(t.strip())) is not None and m.group(2)
        for t in line_text
    ):
        return lines
    grid: list[list[Word | None]] = [[w for w in line] for line in lines]
    ops = [w for line in grid for w in line if w is not None and w.text in _INTEGRAL_CHARS]
    consumed: set[tuple[int, int]] = set()
    paired_num: set[tuple[int, int]] = set()
    replacements: dict[tuple[int, int], Word] = {}
    used_label_band: set[int] = set()

    def _cell(li: int, ai: int) -> Word | None:
        if (li, ai) in consumed:
            return None
        return grid[li][ai]

    def _has_vertical_partner(other: int, t: Word, size: float,
                              exclude: tuple[int, int], above: bool) -> bool:
        """True when token t pairs vertically with an eligible token on the
        other band (a neighbouring column's operand — run expansion must stop
        before absorbing it)."""
        for k, w in enumerate(grid[other]):
            if w is None or (other, k) in consumed or (other, k) == exclude:
                continue
            if not _frac_word_eligible(w, body_size):
                continue
            if re.fullmatch(r"[−–—+]", (w.text or "").strip()):
                continue
            if abs(_frac_cx(w) - _frac_cx(t)) > max(10.0, size):
                continue
            drop = t.top - w.bottom if above else w.top - t.bottom
            if -2.0 <= drop <= _FRACTION_DROP_MAX:
                return True
        return False

    def _expand(li: int, ai: int, other: int, partner: tuple[int, int]) -> tuple[int, int]:
        """Contiguous eligible run around anchor ai on band li.

        A unary sign glues to its operand ("−" + "1" → "−1"); a sign with
        an operand on both sides is binary and never absorbed. Expansion
        stops at a neighbour that pairs vertically itself (a new column).
        """
        above = other < li
        lo = hi = ai
        while hi + 1 < len(grid[li]) and hi + 1 - lo + 1 <= _FRACTION_RUN_TOKENS:
            if (li, hi + 1) in consumed or (li, hi + 1) in paired_num:
                break
            nxt = _cell(li, hi + 1)
            if nxt is None or not _frac_word_eligible(nxt, body_size):
                break
            if _frac_is_integral_bound(nxt, ops):
                break
            # Gap-only run grouping: tightly-spaced tokens (gap <=5pt)
            # belong to one operand ("(3"+"sinθ−2)cosθ" gap 3.2, "5−cos"+"2"
            # gap 0.2); widely spaced tokens are separate columns (Q22 14.5,
            # Q8 24, Q12 92, Q1 6.3) and must never merge — even orphans.
            try:
                _gap = nxt.x0 - (grid[li][hi].x1 if grid[li][hi] is not None else nxt.x0)
            except Exception:
                _gap = 0.0
            if _gap > 5.0:
                break
            hi += 1
        while lo - 1 >= 0 and hi - (lo - 1) + 1 <= _FRACTION_RUN_TOKENS:
            if (li, lo - 1) in consumed or (li, lo - 1) in paired_num:
                break
            prv = _cell(li, lo - 1)
            if prv is None:
                break
            if _frac_is_integral_bound(prv, ops):
                break
            pt = (prv.text or "").strip()
            if re.fullmatch(r"[−–—+]", pt):
                before = _cell(li, lo - 2) if lo - 2 >= 0 else None
                if before is not None and _frac_word_eligible(before, body_size):
                    break  # binary operator: "a − 1" stays split
                lo -= 1
                break  # unary sign absorbed; nothing left of it can join
            if not _frac_word_eligible(prv, body_size):
                break
            try:
                _gapL = (grid[li][lo].x0 if grid[li][lo] is not None else prv.x1) - prv.x1
            except Exception:
                _gapL = 0.0
            if _gapL > 5.0:
                break
            lo -= 1
        return lo, hi

    def _is_script_word(w: Word, line: list[Word | None], body: float) -> bool:
        """True for inverse-trig exponents ("cos −1", never a fraction).

        Only the exact token "−1"/"-1" hugging a function base is a script:
        fenced variables ("(x)" gap 0) and stacked numerators ("π/3" gap
        2.5) must still pair. Narrow so Q1 "−1" scripts never mint "3/−1"
        (drop 1.1) starving the true "x/3" (drop 4.6), while Q7 signed
        numerators ("−1/π" on pure-small rows) still pair.
        """
        try:
            t = (w.text or "").strip()
            if t not in ("−1", "-1"):
                return False
            if (w.size or 0.0) >= body * 0.9:
                return False
            for o in line:
                if o is None or o is w:
                    continue
                if (o.size or 0.0) < body * 0.9:
                    continue
                ot = (o.text or "").strip().lower()
                if ot not in ("cos", "sin", "tan", "sec", "3cos", "cos−1", "sin−1"):
                    # Any large neighbour within 2pt still marks a script
                    # ("cos −1" gap 0.4); isolated "−1" over "π" has no large
                    # neighbour that close.
                    gap = min(abs(w.x0 - o.x1), abs(o.x0 - w.x1))
                    if gap >= 2.0:
                        continue
                else:
                    gap = min(abs(w.x0 - o.x1), abs(o.x0 - w.x1))
                    if gap >= 10.0:
                        continue
                return True
        except Exception:
            return False
        return False

    # Collect every numerator's closest denominator, then pair closest
    # drops first (Q1 "x/3" drop 4.6 beats "3/x" drop 6.0 — top-first greedy
    # consumed "x" into the inverted fake and starved the true pair).
    _cands: list[tuple[float, float, int, int, int, int]] = []
    for li in range(n):
        for ai in range(len(grid[li])):
            if (li, ai) in consumed or (li, ai) in paired_num:
                continue
            u = _cell(li, ai)
            if u is None or not _frac_word_eligible(u, body_size):
                continue
            if _is_script_word(u, grid[li], body_size):
                continue
            if _frac_is_integral_bound(u, ops):
                continue
            if re.fullmatch(r"[−–—+]", (u.text or "").strip()):
                continue
            ucx, ucy, usize = _frac_cx(u), _frac_cy(u), u.size or 10.0
            best_j = -1
            best_b = -1
            best_key: tuple[float, float] | None = None
            for j in range(li + 1, min(n, li + 1 + _FRACTION_MAX_GAP)):
                for b in range(len(grid[j])):
                    v = _cell(j, b)
                    if v is None or not _frac_word_eligible(v, body_size):
                        continue
                    if _is_script_word(v, grid[j], body_size):
                        continue
                    if _frac_is_integral_bound(v, ops):
                        continue
                    if re.fullmatch(r"[−–—+]", (v.text or "").strip()):
                        continue
                    if abs(_frac_cx(v) - ucx) > max(10.0, usize):
                        continue
                    drop = v.top - u.bottom
                    if not (-2.0 <= drop <= _FRACTION_DROP_MAX):
                        continue
                    key = (abs(_frac_cx(v) - ucx), drop)
                    if best_key is None or key < best_key:
                        best_key = key
                        best_j, best_b = j, b
            if best_j < 0:
                continue
            assert best_key is not None
            _cands.append((best_key[1], best_key[0], li, ai, best_j, best_b))
    _cands.sort()
    for _drop, _dx, li, ai, best_j, best_b in _cands:
            if (li, ai) in consumed or (li, ai) in paired_num:
                continue
            u = _cell(li, ai)
            v = grid[best_j][best_b]
            if u is None or v is None:
                continue
            if (best_j, best_b) in consumed or (best_j, best_b) in paired_num:
                continue
            # Re-validate eligibility (consumed state may have changed).
            if not _frac_word_eligible(u, body_size) or not _frac_word_eligible(
                v, body_size
            ):
                continue
            if _is_script_word(u, grid[li], body_size) or _is_script_word(
                v, grid[best_j], body_size
            ):
                continue
            ucx, ucy = _frac_cx(u), _frac_cy(u)
            nlo, nhi = _expand(li, ai, best_j, (best_j, best_b))
            dlo, dhi = _expand(best_j, best_b, li, (li, ai))
            num_words = [w for k, w in enumerate(grid[li]) if nlo <= k <= nhi and w is not None and (li, k) not in consumed]
            den_words = [w for k, w in enumerate(grid[best_j]) if dlo <= k <= dhi and w is not None and (best_j, k) not in consumed]
            if not num_words or not den_words:
                continue
            num_raw = _frac_render_run(num_words)
            den_raw = _frac_render_run(den_words)
            if not num_raw or not den_raw:
                continue
            if len(num_raw) + len(den_raw) > 40:
                continue
            # Single-letter twins ("x" over "x") are piecewise stacks, not
            # fractions; other identical twins are equally suspect.
            if num_raw == den_raw and len(re.sub(r"\s+", "", num_raw)) <= 2:
                continue
            span0 = min(num_words[0].x0, den_words[0].x0)
            span1 = max(num_words[-1].x1, den_words[-1].x1)
            pcx = (span0 + span1) / 2
            if _frac_in_integral_slot(pcx, ucy, _frac_cy(v), ops):
                continue
            # Intrusion: between the bands, only labels/signs/small operands
            # may cross the pair's x-span; prose or relations veto the pair.
            clash = False
            for between in range(li + 1, best_j):
                if between in used_label_band:
                    continue
                for k, w in enumerate(grid[between]):
                    if w is None or (between, k) in consumed:
                        continue
                    if w.x1 <= span0 or w.x0 >= span1:
                        continue
                    wt = (w.text or "").strip()
                    if _frac_word_eligible(w, body_size):
                        continue
                    if _STACK_LABEL_RE.match(wt) or wt in (
                        "+", "-", "*", "−", "–", "—",
                        "(A)", "(B)", "(C)", "(D)",
                        # Interval fences surrounding option fractions
                        # ("(-∞,-1/4]": "]"/")" touch the fraction span by
                        # 0.03pt of float noise — they are the same option,
                        # not intruding prose).
                        "[", "]", "(", ")", "{", "}", "|", ",", ";",
                    ):
                        continue
                    clash = True
                    break
                if clash:
                    break
            if clash:
                continue
            num = _frac_wrap_operand(num_raw, len(num_words))
            den = _frac_wrap_operand(den_raw, len(den_words))
            joined = f"{num}/{den}"
            # Detached option label on its own short line ("(A) −" for
            # −1/10): line-wise labels carry unary signs, so re-attach the
            # pair at the label's position, preserving reading order.
            label_band: int | None = None
            label_text = ""
            label_sign = ""
            label_gap = float("inf")
            for lab_idx in range(max(0, li - 1), min(n, best_j + 1)):
                if lab_idx in used_label_band or lab_idx == li or lab_idx == best_j:
                    continue
                lab_cells = [(k, w) for k, w in enumerate(grid[lab_idx])
                             if w is not None and (lab_idx, k) not in consumed]
                if len(lab_cells) == 1:
                    (_, lab_w) = lab_cells[0]
                    assert lab_w is not None
                    if not _STACK_LABEL_RE.match((lab_w.text or "").strip()):
                        continue
                    sign = ""
                elif len(lab_cells) == 2:
                    mline = " ".join(w.text for _, w in lab_cells).strip()
                    if not _STACK_SIGNED_LABEL_RE.match(mline):
                        continue
                    lab_w = lab_cells[0][1]
                    assert lab_w is not None
                    sign = re.sub(r"\s+", "", lab_cells[1][1].text)  # type: ignore[index]
                else:
                    continue
                assert lab_w is not None
                if not (u.top - 4.0 <= lab_w.top <= v.top + 2.0):
                    continue
                last_x1 = lab_cells[-1][1].x1 if lab_cells[-1][1] is not None else lab_w.x1  # type: ignore[union-attr]
                gap = u.x0 - last_x1
                if gap < -1.0 or gap > 40.0:
                    continue
                if gap < label_gap:
                    label_band = lab_idx
                    label_text = (lab_w.text or "").strip()
                    label_sign = sign
                    label_gap = gap
            if label_band is not None:
                anchor = grid[label_band][0]
                assert anchor is not None
                prefix = f"{label_text} {label_sign}" if label_sign else label_text
                replacements[(label_band, 0)] = Word(
                    text=f"{prefix} {joined}",
                    x0=anchor.x0, top=anchor.top, x1=anchor.x1,
                    bottom=anchor.bottom, fontname=anchor.fontname, size=anchor.size,
                )
                used_label_band.add(label_band)
                for k in range(nlo, nhi + 1):
                    consumed.add((li, k))
                for k in range(dlo, dhi + 1):
                    consumed.add((best_j, k))
                for k in range(len(grid[label_band])):
                    if k != 0:
                        consumed.add((label_band, k))
            else:
                replacements[(li, nlo)] = Word(
                    text=joined, x0=u.x0, top=u.top, x1=u.x1,
                    bottom=u.bottom, fontname=u.fontname, size=u.size,
                )
                paired_num.add((li, nlo))
                for k in range(nlo, nhi + 1):
                    if k != nlo:
                        consumed.add((li, k))
                for k in range(dlo, dhi + 1):
                    consumed.add((best_j, k))
    for (li, ai), w in replacements.items():
        grid[li][ai] = w
    out: list[list[Word]] = []
    for li, line in enumerate(grid):
        kept = [w for ai, w in enumerate(line) if w is not None and (li, ai) not in consumed]
        if kept:
            out.append(kept)
    return out if out else lines


#: Bare integers that may form an inline stacked fraction pair ("3"+"2" for
#: 2/3): 1-3 digits, no sign, no root. Signed/rooted operands stay on the
#: cross-line path.
_INLINE_INT_RE = re.compile(r"^\d{1,3}$")


def _merge_inline_stacked_fractions(
    lines: list[list[Word]], body_size: float
) -> list[list[Word]]:
    """Join stacked fractions already glued into one line ("(a) 3 2" -> "(a) 2/3").

    Line grouping merges same-column stacked operands when their vertical
    centers fall within tolerance (big2 Q2: 10pt type, 5pt center gaps): the
    numerator, its option label and the denominator land in ONE x-ordered
    line, so the cross-line pairing below never fires and the values strand
    as unordered debris ("(a) 3 2", "(c) 6 5"). Adjacent bare-integer pairs
    sharing an x-column (centers within max(12pt, 1.2x size)) but stacked
    vertically (tops differ by >=3pt, drop within the fraction window) merge
    into "num/den" (upper word first — extraction x-order puts the fractionally
    left denominator first). Guarded to option-label lines so table rows,
    matrix debris and same-baseline lists ("(c) 14 (d) 8") never match: those
    pairs share a baseline (top diff <3pt) or lack labels.
    """
    size_floor = body_size * 0.7
    out: list[list[Word]] = []
    for line in lines:
        if len(line) < 3:
            out.append(line)
            continue
        text = " ".join(w.text for w in line)
        if "/" in text:
            out.append(line)
            continue
        if not (_OPTION_PAREN_RE.search(text) or _OPTION_LETTER_RE.search(text)):
            out.append(line)
            continue
        merged = list(line)
        k = 0
        while k < len(merged) - 1:
            a, b = merged[k], merged[k + 1]
            ta = (a.text or "").strip()
            tb = (b.text or "").strip()
            if (
                _STACK_LABEL_RE.match(ta)
                or _STACK_LABEL_RE.match(tb)
                or not _INLINE_INT_RE.match(ta)
                or not _INLINE_INT_RE.match(tb)
            ):
                k += 1
                continue
            if (a.size or 0.0) < size_floor or (b.size or 0.0) < size_floor:
                k += 1
                continue
            ref = max(a.size or 10.0, b.size or 10.0)
            if abs(_frac_cx(a) - _frac_cx(b)) > max(12.0, ref * 1.2):
                k += 1
                continue
            if abs(a.top - b.top) < 3.0:
                k += 1
                continue
            upper, lower = (a, b) if a.top <= b.top else (b, a)
            drop = lower.top - upper.bottom
            if not (-3.0 <= drop <= (upper.size or 10.0) * 1.5):
                k += 1
                continue
            joint = Word(
                text=f"{upper.text.strip()}/{lower.text.strip()}",
                x0=min(a.x0, b.x0), top=min(a.top, b.top),
                x1=max(a.x1, b.x1), bottom=max(a.bottom, b.bottom),
                fontname=upper.fontname, size=upper.size,
            )
            merged[k : k + 2] = [joint]
            k += 1
        out.append(merged)
    return out


def _join_lines_with_fractions(lines: list[list[Word]], body_size: float) -> str:
    """Rejoin vertically stacked fractions split across lines ("(B) 1" / "3").

    pdfplumber emits no "/" for the fraction bar, so without rejoining the
    numerator becomes a fake "(B) 1" equation and the denominator an orphaned
    "3" paragraph. Pairing is geometric, not positional: the denominator must
    sit x-aligned under the numerator with a small vertical drop, no other
    words may intrude between them in that x-span, and both glyphs must be
    near body size (script fragments like Q20's tiny "1"/"3" are excluded).
    A detached option label between them ("1" / "(B)" / "3", the label sits
    below its numerator) is re-attached as "(B) 1/3" at the label's position,
    preserving row-major reading order.

    Multi-token numerator/denominator runs (option grids, lettered operands,
    parenthesized groups) are paired first by _pair_stacked_fraction_runs;
    the single-token logic below handles whatever remains.
    """
    lines = _merge_inline_stacked_fractions(lines, body_size)
    lines = _pair_stacked_fraction_runs(lines, body_size)
    size_floor = body_size * 0.7
    n = len(lines)
    line_text = [" ".join(w.text for w in line) for line in lines]
    # Fractions occur in math context: without an option label or operator
    # nearby, stacked bare numbers are lists/furniture, not numerators.
    # Exception: a SIGNED numerator ("−1" over "2", a detached −1/2 whose
    # bar left no text) is self-evidently a fraction — bare list items
    # never carry a fraction sign, so geometry alone suffices.
    has_context = bool(_STACK_CONTEXT_RE.search(" ".join(line_text)))

    def _signed_numerator(t: str) -> bool:
        m = _STACK_NUM_LINE_RE.match(t.strip())
        return bool(m and m.group(2))

    if not has_context and not any(_signed_numerator(t) for t in line_text):
        return " ".join(line_text)
    removed = [False] * n
    replaced: dict[int, str] = {}
    used_label = set()

    def _near_math(a: int, b: int) -> bool:
        """True when an option label or math operator sits within a few
        lines of the candidate pair. Stranded folio digits ("9" over "13")
        must not borrow operators from distant body lines: unsigned
        numerators pair only on nearby math, never on block-global context.
        """
        lo = max(0, min(a, b) - 4)
        hi = min(n, max(a, b) + 5)
        return bool(_STACK_CONTEXT_RE.search(" ".join(line_text[lo:hi])))

    def word_num(line: list[Word]) -> Word | None:
        if not line:
            return None
        last = line[-1]
        if _STACK_NUM_WORD_RE.match(last.text.strip()) and last.size >= size_floor:
            return last
        return None

    def _prose_between(line: list[Word]) -> bool:
        """True for full prose lines (a question stem, not math debris).

        A fraction bar never spans a prose sentence: when a long lettered
        line sits between the candidate numerator and denominator, the two
        numbers belong to different rows (e.g. stranded folio digits above
        and below a stem), even if its words happen to dodge their narrow
        x-span and the overlap check misses. Short option/math fragments
        (other columns' numerators, labels) are not prose and never veto.
        """
        if len(line) < 8:
            return False
        return sum(1 for w in line if re.search(r"[A-Za-z]", w.text)) >= 3

    for den_idx in range(n):
        den_line = lines[den_idx]
        if removed[den_idx] or len(den_line) != 1:
            continue
        den = den_line[0]
        if not _STACK_DEN_LINE_RE.match(den.text.strip()) or den.size < size_floor:
            continue
        den_c = (den.x0 + den.x1) / 2
        # Nearest numerator above (interleaved other-column lines may sit
        # between, so scan upward past several lines, not just the neighbour:
        # four-column option rows separate numerators from denominators by
        # seven lines).
        for num_idx in range(den_idx - 1, max(-1, den_idx - 13), -1):
            if removed[num_idx]:
                continue
            num_line = lines[num_idx]
            m = _STACK_NUM_LINE_RE.match(" ".join(w.text for w in num_line).strip())
            if not m:
                continue
            if not m.group(2) and not _near_math(num_idx, den_idx):
                # No math nearby: only a signed numerator is unambiguous.
                continue
            num_word = word_num(num_line)
            if num_word is None:
                continue
            num_c = (num_word.x0 + num_word.x1) / 2
            if abs(num_c - den_c) > max(12.0, num_word.size * 1.2):
                continue
            drop = den.top - num_word.bottom
            if not (-3.0 <= drop <= num_word.size * 1.5):
                continue
            span0 = min(num_word.x0, den.x0)
            span1 = max(num_word.x1, den.x1)
            clash = False
            for between in range(num_idx + 1, den_idx):
                if removed[between]:
                    continue
                if _prose_between(lines[between]):
                    clash = True
                    break
                for w in lines[between]:
                    if w.x0 < span1 and w.x1 > span0:
                        clash = True
                        break
                if clash:
                    break
            if clash:
                continue
            num_text = re.sub(r"\s+", "", (m.group(2) or "") + m.group(3))
            label_text = m.group(1)
            if label_text:
                # Numerator line already carries its label: "…" → "… N/D".
                replaced[num_idx] = f"{label_text}{num_text}/{den.text.strip()}"
                removed[den_idx] = True
            else:
                # Find the detached label: single "(X)" line beside the
                # numerator, nearest on the left, vertically between. A label
                # carrying the fraction's sign ("(A) −" for −1/10) counts too.
                best = None
                for lab_idx, lab_line in enumerate(lines):
                    if removed[lab_idx] or lab_idx in used_label:
                        continue
                    lab_text, lab_sign = _split_label_line(lab_line)
                    if lab_text is None:
                        continue
                    if not (num_word.top - 4.0 <= lab_line[0].top <= den.top + 2.0):
                        continue
                    gap = num_word.x0 - lab_line[-1].x1
                    if gap < -1.0 or gap > 40.0:
                        continue
                    key = (gap, abs(lab_line[0].top - num_word.top))
                    if best is None or key < best[0]:
                        best = (key, lab_idx, lab_sign)
                if best is not None:
                    _, lab_idx, lab_sign = best
                    used_label.add(lab_idx)
                    sign = lab_sign or ""
                    replaced[lab_idx] = (
                        f"{lines[lab_idx][0].text.strip()} {sign}{num_text}/{den.text.strip()}"
                    )
                    removed[num_idx] = True
                    removed[den_idx] = True
                else:
                    replaced[num_idx] = f"{num_text}/{den.text.strip()}"
                    removed[den_idx] = True
            break

    out: list[str] = []
    for i, text in enumerate(line_text):
        if removed[i]:
            continue
        out.append(replaced.get(i, text))
    return " ".join(out)


# ---------------------------------------------------------------------------
# Integral limit attachment (minimal blocks.py support for n-ary OMML).
# ---------------------------------------------------------------------------
# Bounds extract as separate small words above/below the operator
# ("2" over ∫, "−4" under it) without _/^ scripts, so the recognizer never
# sees them and no <m:nary> is ever emitted (limits detach as trailing
# "4 2" or strand at para starts). This pass — and ONLY this pass — may
# touch lines here: it moves geometrically-identified bound words into the
# operator's line as braced scripts ("∫^{2}_{-4}"), consuming the originals
# so they cannot detach. Segmentation (line grouping, block splitting,
# table detection) is otherwise untouched — another agent owns it.

#: N-ary operators whose bounds stack above/below in born-digital PDFs.
_INTEGRAL_CHARS = frozenset({"∫", "∑", "∏"})

#: A bound is one short token: an optionally-signed integer or a single
#: variable/π ("2", "−4", "0", "1", "a", "b", "π"). Anything longer
#: ("(3", "5−𝑐𝑜𝑠", "b l", "^h", "1+x") is integrand, fraction debris or
#: bracket litter — never a bound. Internal spaces ("− 4") are allowed
#: because the sign may extract as a separate word gap.
_LIMIT_TOKEN_RE = re.compile(r"^[−–—-]?\s*(?:\d+|π|[a-zA-Z])$")

#: Debris tokens that must never attach as bounds even if positioned well.
_LIMIT_DEBRIS = frozenset({
    "", "^", "_", "h", "^h", "b", "l", "b l",
    "[", "]", "(", ")", "{", "}", "⎛", "⎜", "⎝", "⎞", "⎟", "⎠",
    "R", "S", "V", "W", "T", "X", ">H",
})


def _is_limit_word(text: str) -> bool:
    t = (text or "").strip()
    if not t or t in _LIMIT_DEBRIS:
        return False
    # "− 4" (sign detached by a space) still counts; "b l" (letter space
    # letter) does not match the single-token shape and is rejected.
    nospace = re.sub(r"\s+", "", t)
    if len(nospace) > 4:
        return False
    return bool(_LIMIT_TOKEN_RE.match(t))


def _attach_integral_limits(lines: list[list[Word]]) -> list[list[Word]]:
    """Move above/below bound words into their ∫ line as ^{}_{} scripts.

    Pure w.r.t. content (no words invented, none dropped — moved words are
    consumed from their original lines so trailing "4 2" / leading "2"
    debris cannot strand). Returns the (possibly) rewritten lines; empty
    lines left behind are dropped.
    """
    # Locate every n-ary operator word with its line/position.
    ops: list[tuple[int, int, Word]] = []
    for li, line in enumerate(lines):
        for wi, w in enumerate(line):
            if w.text in _INTEGRAL_CHARS:
                ops.append((li, wi, w))
    if not ops:
        return lines
    # Work on mutable copies so originals are consumed exactly once.
    grid: list[list[Word | None]] = [[w for w in line] for line in lines]
    consumed: set[tuple[int, int]] = set()

    for li, wi, op in ops:
        if (li, wi) in consumed:
            continue
        op_cx = (op.x0 + op.x1) / 2
        op_cy = (op.top + op.bottom) / 2
        x_tol = max(10.0, (op.size or 12.0) * 0.9)
        v_tol = (op.size or 12.0) * 1.1
        best_upper: tuple[float, int, int, Word] | None = None
        best_lower: tuple[float, int, int, Word] | None = None
        for ali, aline in enumerate(grid):
            for awi, cand in enumerate(aline):
                if cand is None or cand is op:
                    continue
                if (ali, awi) in consumed:
                    continue
                if not _is_limit_word(cand.text):
                    continue
                # Bounds are set smaller than the operator (8.5pt over
                # 12pt body, 6.4pt over 16.5pt display); full-size words
                # ("Evaluate", "|x+1|dx") are integrand, never bounds.
                if not cand.size or not op.size:
                    continue
                if not (cand.size < op.size * 0.85 and cand.size >= 5.0):
                    continue
                cx = (cand.x0 + cand.x1) / 2
                cy = (cand.top + cand.bottom) / 2
                if abs(cx - op_cx) > x_tol:
                    continue
                dy = cy - op_cy
                if dy < -1.5 and abs(dy) <= v_tol:
                    key = (abs(cx - op_cx), abs(dy))
                    if best_upper is None or key < (best_upper[0], 0):
                        best_upper = (abs(cx - op_cx) + abs(dy) * 0.1, ali, awi, cand)
                elif dy > 1.5 and abs(dy) <= v_tol:
                    key = (abs(cx - op_cx), abs(dy))
                    if best_lower is None or key < (best_lower[0], 0):
                        best_lower = (abs(cx - op_cx) + abs(dy) * 0.1, ali, awi, cand)
        if best_upper is None or best_lower is None:
            # Honest n-ary needs BOTH bounds; a single stacked number is
            # a sub/superscript at best and more often fraction debris —
            # leave it where it is rather than minting half a limit.
            continue
        _, uli, uwi, upper = best_upper
        _, lli, lwi, lower = best_lower
        # Do not double-attach when scripts are already inline ("∫_0^1").
        host = grid[li]
        neighbour_text = " ".join(
            (w.text if w is not None else "") for w in host[max(0, wi - 1): wi + 2]
        )
        if "^" in neighbour_text or "_" in neighbour_text:
            continue
        upper_txt = re.sub(r"\s+", "", upper.text)
        lower_txt = re.sub(r"\s+", "", lower.text)
        # Consume originals so they cannot also emit as trailing/leading text.
        consumed.add((uli, uwi))
        consumed.add((lli, lwi))
        grid[uli][uwi] = None
        grid[lli][lwi] = None
        script_upper = Word(
            text="^{" + upper_txt + "}",
            x0=op.x0, top=op.top, x1=op.x1, bottom=op.bottom,
            fontname=op.fontname, size=op.size,
        )
        script_lower = Word(
            text="_{" + lower_txt + "}",
            x0=op.x0, top=op.top, x1=op.x1, bottom=op.bottom,
            fontname=op.fontname, size=op.size,
        )
        # Insert immediately after the operator: "∫ ^{2} _{-4} integrand".
        insert_at = wi + 1
        # Account for earlier insertions on the same line shifting indices:
        # grid[li] may already hold scripts from a previous operator on
        # this line; find the operator's current index instead.
        try:
            cur = next(i for i, w in enumerate(grid[li]) if w is op)
            insert_at = cur + 1
        except StopIteration:
            continue
        grid[li][insert_at:insert_at] = [script_upper, script_lower]
    out: list[list[Word]] = []
    for line in grid:
        kept = [w for w in line if w is not None]
        if kept:
            out.append(kept)
    return out if out else lines


# ---------------------------------------------------------------------------
# Fallback emission: unmapped-glyph substitution (FFFD -> ASCII).
# ---------------------------------------------------------------------------
# Fonts without ToUnicode expose matrix brackets as Symbol PUA runs (quebank
# 104 chars: E6-E8/F6-F8 paren pieces, E9-EB/F9-FB square pieces) or as bare
# U+FFFD (ICSE 14 chars, CambriaMath), and as C0 controls (big2 500x U+0001:
# Wingdings bullets, Euclid "OR" split as "\x01R", footer garble). At the
# fallback emission point (here + word/omml.sanitize backstop) replace with
# best-effort ASCII (vertical-bar geometry -> "[ ]", fraction bars -> "/",
# middots -> "*"); U+FFFD survives only as a flagged last resort (model text
# still carries it, so verification.check_replacement_chars stays critical).
_PUA_LEFT_PAREN_CHARS = frozenset(chr(0xF000 + c) for c in (0xE6, 0xE7, 0xE8))
_PUA_RIGHT_PAREN_CHARS = frozenset(chr(0xF000 + c) for c in (0xF6, 0xF7, 0xF8))
_PUA_LEFT_SQUARE_CHARS = frozenset(chr(0xF000 + c) for c in (0xE9, 0xEA, 0xEB))
_PUA_RIGHT_SQUARE_CHARS = frozenset(chr(0xF000 + c) for c in (0xF9, 0xFA, 0xFB))
_PUA_BRACKET_ALL = (
    _PUA_LEFT_PAREN_CHARS | _PUA_RIGHT_PAREN_CHARS
    | _PUA_LEFT_SQUARE_CHARS | _PUA_RIGHT_SQUARE_CHARS
)


def _clean_single_word(w: Word) -> Word | None:
    """Map one Word's unmapped glyphs to ASCII; None drops decorative scrap.

    Pure helper, no line context (single-U+FFFD brackets need width/height +
    line alternation, handled in _substitute_unmapped_in_lines).
    """
    try:
        t = w.text or ""
    except Exception:
        return w
    if not t:
        return w
    # Euclid "OR" split as "\x01R" (big2 108x): U+0001 is the "O" with no
    # ToUnicode entry. Direct control-char check below maps it to "OR".
    if len(t) == 2 and ord(t[0]) < 0x20 and t[1] == "R":
        return Word(text="OR", x0=w.x0, top=w.top, x1=w.x1, bottom=w.bottom,
                    fontname=w.fontname, size=w.size)
    # Pure C0 controls (Wingdings zero-width, Wingdings2 7x separators):
    # decorative, never content -> drop (sanitize backstop strips any slip).
    if t.strip() and all(ord(c) < 0x20 for c in t.strip()):
        return None
    if t and all(ord(c) < 0x20 or c in (" ", "\t") for c in t):
        # Covers "\x01", "\x01"*7 with no letters.
        stripped = "".join(c for c in t if ord(c) >= 0x20)
        if not stripped.strip():
            return None
    # Garbled running footer ("ContonueCooueen paueeeeeee", bottom margin):
    # never content; segment_blocks drops it pre-grouping, this is backstop.
    if "Contonue" in t or "paue" in t:
        return None
    # Symbol PUA bracket runs (quebank): each Word is single-sided
    # ("\uf0e6\uf0e7\uf0e8" -> "("); collapse within-word run to one.
    if t.strip() and all(c in _PUA_BRACKET_ALL for c in t.strip()):
        chars = set(t.strip())
        if chars <= _PUA_LEFT_PAREN_CHARS:
            bracket = "("
        elif chars <= _PUA_RIGHT_PAREN_CHARS:
            bracket = ")"
        elif chars <= _PUA_LEFT_SQUARE_CHARS:
            bracket = "["
        elif chars <= _PUA_RIGHT_SQUARE_CHARS:
            bracket = "]"
        else:
            # Mixed sides (should not happen): keep first side, never FFFD.
            first = next(iter(t.strip()))
            if first in _PUA_LEFT_PAREN_CHARS:
                bracket = "("
            elif first in _PUA_RIGHT_PAREN_CHARS:
                bracket = ")"
            elif first in _PUA_LEFT_SQUARE_CHARS:
                bracket = "["
            else:
                bracket = "]"
        return Word(text=bracket, x0=w.x0, top=w.top, x1=w.x1, bottom=w.bottom,
                    fontname=w.fontname, size=w.size)
    # Mixed FFFD + letters ("\ufffdqqssss", ICSE p7/p13): strip the marker,
    # keep the letters (no FFFD). Pure single "\ufffd" stays for line-level
    # geometry below.
    if "\ufffd" in t and t.strip() != "\ufffd":
        kept = t.replace("\ufffd", "")
        if not kept.strip():
            return None
        return Word(text=kept, x0=w.x0, top=w.top, x1=w.x1, bottom=w.bottom,
                    fontname=w.fontname, size=w.size)
    return w


def _substitute_unmapped_in_lines(lines: list[list[Word]]) -> list[list[Word]]:
    """Replace unmapped glyphs using Word geometry + line context. Pure.

    - PUA brackets / controls / garble via _clean_single_word (drops Nones).
    - Single-U+FFFD: narrow-tall (w<7,h>9) -> bracket ("[" / "]" alternating
      left-to-right within the line, so "A = [ ] A = [ ]" pairs correctly);
      wide (w>=7, e.g. ICSE 9.2pt fraction bars) -> "/"; small -> "*" (middot).
    Empty lines drop; fully-empty input returns [] (caller emits empty block,
    never raises, so one bad footer never kills the page).
    """
    if not lines:
        return lines
    cleaned: list[list[Word]] = []
    for line in lines:
        kept: list[Word] = []
        for w in line:
            try:
                nw = _clean_single_word(w)
            except Exception:
                nw = w
            if nw is not None:
                kept.append(nw)
        if kept:
            cleaned.append(kept)
    if not cleaned:
        return []
    # Line-level single-FFFD geometry pass.
    out: list[list[Word]] = []
    for line in cleaned:
        # Indices of bare replacement chars in this line.
        idxs = [i for i, w in enumerate(line) if (w.text or "").strip() == "\ufffd"]
        if not idxs:
            out.append(line)
            continue
        # Narrow-tall brackets in x-order alternate "[" / "]".
        narrow = []
        for i in idxs:
            w = line[i]
            try:
                ww = (w.x1 - w.x0)
                hh = (w.bottom - w.top)
            except Exception:
                ww, hh = 5.0, 12.0
            if ww < 7.0 and hh > 9.0:
                narrow.append(i)
        # Assign alternation in x-order (line already x-ordered).
        bracket_pos = {idx: n for n, idx in enumerate(narrow)}
        newline = list(line)
        for i in idxs:
            w = line[i]
            try:
                ww = (w.x1 - w.x0)
                hh = (w.bottom - w.top)
            except Exception:
                ww, hh = 5.0, 12.0
            if ww < 7.0 and hh > 9.0:
                bracket = "[" if (bracket_pos.get(i, 0) % 2 == 0) else "]"
            elif ww >= 7.0 and hh > 9.0:
                bracket = "/"  # fraction bar (ICSE 9.2pt "sec" fractions)
            else:
                bracket = "*"  # middot / tiny scrap
            newline[i] = Word(text=bracket, x0=w.x0, top=w.top, x1=w.x1,
                              bottom=w.bottom, fontname=w.fontname, size=w.size)
        out.append(newline)
    return out if out else []


# ---------------------------------------------------------------------------
# Inline 2D scripts: superscripts / subscripts set on a shifted baseline.
# ---------------------------------------------------------------------------
# Born-digital PDFs set "x^2", "tan^-1 x", "(x-1)^3" as a smaller word on a
# raised/lowered baseline with no "^"/"_" glyph, so extraction yields
# "x 2" / "tan −1" and the math recognizer never sees a script. This pass
# folds geometrically-certain scripts into their base word ("x^{2}").
# Integral bounds, option labels and stacked-fraction operands are left to
# their own passes.

#: A script is one short token: optionally signed integer or one letter.
_SCRIPT_TOKEN_RE = re.compile(r"^[−–—+-]?(?:\d+|[a-zA-Z])$")

#: Math bases: one letter (after optional opening delimiters), a closing
#: delimiter, or a trailing function name ("tan", "𝑠𝑖𝑛", "𝑥tan").
_SCRIPT_BASE_LETTER_RE = re.compile(r"(?:^|[^A-Za-z])[A-Za-z]$")
_SCRIPT_BASE_CLOSE_RE = re.compile(r"[)\]]$")
_SCRIPT_BASE_FUNC_RE = re.compile(r"(?:sin|cos|tan|sec|csc|cot|log|ln)$")
_SCRIPT_OPTION_LABEL_RE = re.compile(r"^\([A-Da-d]\)$")


def _script_nfkc(text: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFKC", (text or "").strip())


def _is_script_base(text: str) -> bool:
    t = _script_nfkc(text)
    if not t or t in _INTEGRAL_CHARS or _SCRIPT_OPTION_LABEL_RE.match(t):
        return False
    if t.endswith("}"):  # already carries a script
        return False
    return bool(
        _SCRIPT_BASE_LETTER_RE.search(t)
        or _SCRIPT_BASE_CLOSE_RE.search(t)
        or _SCRIPT_BASE_FUNC_RE.search(t)
    )


def _attach_inline_scripts(
    lines: list[list[Word]], body_size: float
) -> list[list[Word]]:
    """Fold raised/lowered small tokens into their base word as ``^{}``/``_{}``.

    Pure w.r.t. content: a script word is consumed only when merged into the
    base, never dropped. Lines with nothing to fold are returned unchanged.
    """
    if not lines:
        return lines
    all_words = [w for line in lines for w in line]

    def _stacked_partner(w: Word, base: Word) -> bool:
        """True when w is vertically stacked with another numeric operand
        (a fraction numerator/denominator), not a script of ``base``."""
        cx = _frac_cx(w)
        reach = max(5.0, (w.size or 8.0) * 0.6)
        for o in all_words:
            if o is w or o is base:
                continue
            if not _STACK_NUM_WORD_RE.match((o.text or "").strip()):
                continue
            if not o.size or not (
                (w.size or 0.0) * 0.7 <= o.size <= (w.size or 0.0) * 1.25
            ):
                continue
            if abs(_frac_cx(o) - cx) > reach:
                continue
            gap = (o.top - w.bottom) if o.top >= w.top else (w.top - o.bottom)
            if -1.0 <= gap <= _FRACTION_DROP_MAX and abs(o.top - w.top) >= 3.0:
                return True
        return False

    def _multi_token_script(line: list[Word], idx: int, prev: Word) -> bool:
        """True when the script continues into a second small adjacent word
        ("e^{x ⁄y}"): attaching only the first token would split it."""
        if idx + 1 >= len(line):
            return False
        nxt = line[idx + 1]
        if not nxt.size or not prev.size:
            return False
        if (nxt.text or "").lstrip().startswith(("⁄", "/")):
            return True
        return nxt.size < prev.size * 0.85 and 0 <= nxt.x0 - line[idx].x1 <= 4.0

    changed = False
    out: list[list[Word]] = []
    for line in lines:
        new_line: list[Word] = []
        for wi, w in enumerate(line):
            prev = new_line[-1] if new_line else None
            t = (w.text or "").strip()
            if (
                prev is not None
                and prev.size
                and w.size
                and 5.0 <= w.size < prev.size * 0.85
                and _SCRIPT_TOKEN_RE.match(_script_nfkc(t))
                and _is_script_base(prev.text)
            ):
                gap = w.x0 - prev.x1
                kind = None
                if -1.5 <= gap <= max(4.0, prev.size * 0.45):
                    if w.top < prev.top - 1.0 and w.bottom < prev.bottom - 1.0:
                        kind = "^"
                    elif w.top > prev.top + 1.0 and w.bottom > prev.bottom + 0.5:
                        kind = "_"
                if kind and not _multi_token_script(line, wi, prev) and not _stacked_partner(w, prev):
                    new_line[-1] = Word(
                        text=f"{prev.text.strip()}{kind}{{{t}}}",
                        x0=prev.x0, top=prev.top,
                        x1=max(prev.x1, w.x1), bottom=prev.bottom,
                        fontname=prev.fontname, size=prev.size,
                    )
                    changed = True
                    continue
            new_line.append(w)
        out.append(new_line)
    return out if changed else lines


def _flush(page_number: int, index: int, lines: list[list[Word]], body_size: float) -> Block:
    try:
        lines = _substitute_unmapped_in_lines(lines)
    except Exception:
        pass
    if not lines or not any(lines):
        return Block(id=f"p{page_number}-b{index}", kind="paragraph",
                     page_number=page_number, bbox=[0, 0, 1, 1], text="",
                     size=round(body_size, 1), bold=False, confidence=0.99)
    lines = _attach_integral_limits(lines)
    try:
        lines = _attach_inline_scripts(lines, body_size)
    except Exception:
        pass
    words = [w for line in lines for w in line]
    if not words:
        return Block(id=f"p{page_number}-b{index}", kind="paragraph",
                     page_number=page_number, bbox=[0, 0, 1, 1], text="",
                     size=round(body_size, 1), bold=False, confidence=0.99)
    text = despace_function_names(_join_lines_with_fractions(lines, body_size))
    x0 = min(w.x0 for w in words)
    top = min(w.top for w in words)
    x1 = max(w.x1 for w in words)
    bottom = max(w.bottom for w in words)
    avg_size = sum(w.size for w in words) / len(words)
    bold = any("bold" in w.fontname.lower() for w in words)
    kind = "heading" if (avg_size >= body_size * 1.25 and len(text) < 160) else "paragraph"
    return Block(
        id=f"p{page_number}-b{index}",
        kind=kind,
        page_number=page_number,
        bbox=[round(x0, 1), round(top, 1), round(x1, 1), round(bottom, 1)],
        text=text,
        size=round(avg_size, 1),
        bold=bold,
        confidence=0.99 if kind == "paragraph" else 0.85,
    )
