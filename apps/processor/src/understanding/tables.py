"""Ruled-table reconstruction from PDF geometry.

Word-geometry detection (:mod:`.blocks`) can only align a table whose
columns repeat exactly; a table whose columns are irregular, or whose
header spans cells, can never align that way. This module rebuilds such
tables from the ruling lines the PDF actually draws (``page.rects`` /
``page.lines`` / curve edges) and reports the structure the DOCX builder
needs: cell text, merged spans, header rows and per-cell borders.

Pure functions over pdfplumber geometry: this module never opens a file,
never renders a page and never touches python-docx. The caller hands over a
pdfplumber page's rules and the page's words.

The contract mirrors the public shape of a cloud OCR table API: a table is
always segmented (never a paragraph of joined text), merged cells are
tagged, and a structure that cannot be trusted degrades to an image crop
(``parseStatus="fallback_image"``) instead of shipping a broken grid.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# T0 — ruling lines
# ---------------------------------------------------------------------------

#: A rect thinner than this (points) in one axis is a rule, not a box.
_THIN_RULE_PT = 2.0

#: A filled rectangle larger than this in BOTH axes is a shaded cell
#: (highlighted background), never a rule source.
_SHADED_CELL_PT = 6.0

#: Rules shorter than this (points) are fragments (tick marks, dashes,
#: hairline separators), never table borders.
_MIN_RULE_LEN_PT = 12.0

#: Snapping tolerance for rule positions (points): two rules this close are
#: the same rule drawn twice, or one rule split by a crossing.
_SNAP_PT = 2.0

#: A horizontal rule this close to a word's baseline underlines that word
#: (text decoration), it is not a table rule.
_UNDERLINE_TOL_PT = 2.5

#: Max distance between two rules of one table that are linked without a
#: crossing rule (a row whose cell text wraps over several lines).
_LINK_PITCH_PT = 60.0

#: A candidate region may not cover more than this share of the page.
_MAX_PAGE_SHARE = 0.60

#: ... unless it is a real multi-column grid (>= 3 columns, or >= 3
#: horizontal rules). Exam papers draw their question table across the
#: whole page (SQP p2 covers 77% of it, p9 is one tall row of three
#: columns) and a page frame is a 2-column box, which the 60% gate and
#: the column gate reject anyway.
_MAX_PAGE_SHARE_GRID = 0.98

#: A candidate must hold at least this many words to be a table.
_MIN_WORDS = 6

#: Column separator valleys for a partially ruled table (horizontal rules
#: only): an empty gap of at least this width separates two columns.
_MIN_COL_GAP_PT = 8.0

#: How many different row shapes a table may have before its structure is
#: no longer trusted: one merged shape (a banner or a section header) plus
#: the normal row shape. More than that is a mishmash of rules, not a
#: table, and the region ships as an image crop instead.
_MAX_ROW_SHAPES = 2

#: Caption binding: a caption line this close above/below the table.
_CAPTION_GAP_PT = 25.0

#: Caption label shapes ("Table 3", "Fig. 2", "Figure 4", "TABLE 1").
_CAPTION_RE = re.compile(r"^(?:Table|TABLE|Fig\.?|Figure\.?|FIG\.?)\s*\d*")


@dataclass(frozen=True)
class Rule:
    """One ruling line: ``orientation`` is ``"h"`` or ``"v"``.

    ``pos`` is the rule's position on the other axis (y for horizontal,
    x for vertical); ``start``/``end`` span the rule along its own axis.
    """

    orientation: str
    pos: float
    start: float
    end: float


@dataclass
class HLine:
    """A snapped horizontal rule."""

    y: float
    x0: float
    x1: float


@dataclass
class VLine:
    """A snapped vertical rule.

    ``spans`` holds the drawn segments: a vertical is often drawn as one
    segment per row band (with a hairline gap where a horizontal rule
    crosses it). The segments are kept apart — a vertical that is MISSING
    from one band must not be seen as crossing it.
    """

    x: float
    spans: list = field(default_factory=list)

    def covers(self, y0: float, y1: float, tol: float = _SNAP_PT) -> bool:
        for top, bottom in self.spans:
            if top <= y0 + tol and bottom >= y1 - tol:
                return True
        return False


@dataclass
class Cell:
    """One reconstructed cell (may span several grid columns)."""

    row: int
    col: int
    span: int
    words: list = field(default_factory=list)
    text: str = ""


@dataclass
class RuledTable:
    """A reconstructed table: rectangular grid + spans + header + borders."""

    rows: list = field(default_factory=list)        # list[list[str]]
    spans: list = field(default_factory=list)       # list[list[[c0, c1]]]
    cells: list = field(default_factory=list)       # list[list[Cell]]
    header_rows: list = field(default_factory=list)
    borders: list = field(default_factory=list)     # list[list[dict]]
    column_widths: list = field(default_factory=list)  # points, one per column
    bbox: tuple = (0.0, 0.0, 0.0, 0.0)
    parse_status: str = "ok"
    fallback_reason: str | None = None
    words: list = field(default_factory=list)       # consumed words

    @property
    def n_rows(self) -> int:
        return len(self.rows)

    @property
    def n_cols(self) -> int:
        return max((len(r) for r in self.rows), default=0)


# ---------------------------------------------------------------------------
# T0 — extract ruling lines from pdfplumber geometry
# ---------------------------------------------------------------------------

def _rect_rules(rect) -> list[Rule]:
    """Rules contributed by one pdfplumber rect."""
    try:
        x0 = float(rect["x0"])
        x1 = float(rect["x1"])
        top = float(rect["top"])
        bottom = float(rect["bottom"])
    except (KeyError, TypeError, ValueError):
        return []
    w = x1 - x0
    h = bottom - top
    if w <= 0 or h <= 0:
        return []
    out: list[Rule] = []
    if h <= _THIN_RULE_PT:
        if w >= _MIN_RULE_LEN_PT:
            out.append(Rule("h", (top + bottom) / 2.0, x0, x1))
        return out
    if w <= _THIN_RULE_PT:
        if h >= _MIN_RULE_LEN_PT:
            out.append(Rule("v", (x0 + x1) / 2.0, top, bottom))
        return out
    filled = bool(rect.get("fill"))
    if filled and w > _SHADED_CELL_PT and h > _SHADED_CELL_PT:
        # Shaded cell background: its edges are decoration, not table rules.
        return []
    # A box (outlined, or a small filled block): contribute its four sides
    # when they are long enough to be a border.
    if w >= _MIN_RULE_LEN_PT:
        out.append(Rule("h", top, x0, x1))
        out.append(Rule("h", bottom, x0, x1))
    if h >= _MIN_RULE_LEN_PT:
        out.append(Rule("v", x0, top, bottom))
        out.append(Rule("v", x1, top, bottom))
    return out


def _line_rules(obj) -> list[Rule]:
    """Rules contributed by a pdfplumber line / curve edge."""
    try:
        x0 = float(obj["x0"])
        x1 = float(obj["x1"])
        top = float(obj["top"])
        bottom = float(obj["bottom"])
    except (KeyError, TypeError, ValueError):
        return []
    horizontal = abs(bottom - top) <= _THIN_RULE_PT
    vertical = abs(x1 - x0) <= _THIN_RULE_PT
    if horizontal and (x1 - x0) >= _MIN_RULE_LEN_PT:
        return [Rule("h", (top + bottom) / 2.0, min(x0, x1), max(x0, x1))]
    if vertical and (bottom - top) >= _MIN_RULE_LEN_PT:
        return [Rule("v", (x0 + x1) / 2.0, min(top, bottom), max(top, bottom))]
    return []


def _is_underline(rule: Rule, words) -> bool:
    """True when a horizontal rule underlines a single word.

    A table rule spans several words; an underline sits inside ONE word's
    own x-span. Requiring the containment keeps table rules that happen to
    run close to a text baseline.
    """
    if rule.orientation != "h":
        return False
    for w in words:
        try:
            bottom = float(w.bottom)
            wx0 = float(w.x0)
            wx1 = float(w.x1)
        except (AttributeError, TypeError, ValueError):
            continue
        if abs(rule.pos - bottom) > _UNDERLINE_TOL_PT:
            continue
        if rule.pos < bottom - 1.0:
            continue
        if rule.start >= wx0 - 2.0 and rule.end <= wx1 + 2.0:
            return True
    return False


def _rule_in_box(rule: Rule, boxes) -> bool:
    """True when a rule belongs to an embedded graphic.

    A raster figure is usually framed by a stroked rectangle; those four
    sides are the picture's border, not table rules. Without this the frame
    splits the surrounding table into phantom columns.
    """
    for box in boxes or ():
        try:
            bx0, btop, bx1, bbottom = (float(v) for v in box)
        except (TypeError, ValueError):
            continue
        if rule.orientation == "h":
            inside = (
                rule.pos >= btop - 2.0
                and rule.pos <= bbottom + 2.0
                and rule.start >= bx0 - 2.0
                and rule.end <= bx1 + 2.0
            )
        else:
            inside = (
                rule.pos >= bx0 - 2.0
                and rule.pos <= bx1 + 2.0
                and rule.start >= btop - 2.0
                and rule.end <= bbottom + 2.0
            )
        if inside:
            return True
    return False


def extract_rules(page, words=None, image_boxes=None) -> list[Rule]:
    """Read the ruling lines of one pdfplumber page.

    ``page`` is a pdfplumber page object; ``words`` (optional) are the page's
    words, used to drop underlines (text decoration) from the rule set;
    ``image_boxes`` (optional) are embedded graphic regions whose border
    rules are not table rules.
    """
    words = list(words or [])
    rules: list[Rule] = []
    seen: set[tuple] = set()

    def _add(rule: Rule) -> None:
        key = (rule.orientation, round(rule.pos, 2), round(rule.start, 2), round(rule.end, 2))
        if key in seen:
            return
        seen.add(key)
        rules.append(rule)

    for rect in list(getattr(page, "rects", None) or []):
        for rule in _rect_rules(rect):
            _add(rule)
    for line in list(getattr(page, "lines", None) or []):
        for rule in _line_rules(line):
            _add(rule)
    for edge in list(getattr(page, "edges", None) or []):
        if str(edge.get("object_type", "")).lower() != "curve":
            continue
        for rule in _line_rules(edge):
            _add(rule)
    return [
        r
        for r in rules
        if not _is_underline(r, words) and not _rule_in_box(r, image_boxes)
    ]


# ---------------------------------------------------------------------------
# T0/T2 — snap rules into lines, group them into table candidates
# ---------------------------------------------------------------------------

def _cluster_h(rules: list[Rule]) -> list[HLine]:
    out: list[HLine] = []
    for rule in sorted(rules, key=lambda r: (r.pos, r.start)):
        if out and abs(rule.pos - out[-1].y) <= _SNAP_PT:
            cur = out[-1]
            out[-1] = HLine(y=cur.y, x0=min(cur.x0, rule.start), x1=max(cur.x1, rule.end))
        else:
            out.append(HLine(y=rule.pos, x0=rule.start, x1=rule.end))
    return out


def _cluster_v(rules: list[Rule]) -> list[VLine]:
    out: list[VLine] = []
    for rule in sorted(rules, key=lambda r: (r.pos, r.start)):
        if out and abs(rule.pos - out[-1].x) <= _SNAP_PT:
            out[-1].spans.append((rule.start, rule.end))
            continue
        out.append(VLine(x=rule.pos, spans=[(rule.start, rule.end)]))
    for line in out:
        line.spans.sort()
    return out


def _h_v_intersect(h: HLine, v: VLine) -> bool:
    for top, bottom in v.spans:
        if (
            h.y >= top - _SNAP_PT
            and h.y <= bottom + _SNAP_PT
            and v.x >= h.x0 - _SNAP_PT
            and v.x <= h.x1 + _SNAP_PT
        ):
            return True
    return False


def _components(h_lines: list[HLine], v_lines: list[VLine]):
    """Group rules into per-table components.

    Rules join when they cross, or when two parallel rules overlap and sit
    within one row pitch of each other (a tall row whose text wraps over
    several lines has no intermediate rule).
    """
    n = len(h_lines) + len(v_lines)
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, h in enumerate(h_lines):
        for j, v in enumerate(v_lines):
            if _h_v_intersect(h, v):
                union(i, len(h_lines) + j)
    for i, a in enumerate(h_lines):
        for j, b in enumerate(h_lines):
            if j <= i:
                continue
            overlap = min(a.x1, b.x1) - max(a.x0, b.x0)
            if overlap > 0 and abs(a.y - b.y) <= _LINK_PITCH_PT:
                union(i, j)
    for i, a in enumerate(v_lines):
        for j, b in enumerate(v_lines):
            if j <= i:
                continue
            overlap = any(
                min(at, bt) - max(ab, bb) > 0
                for at, ab in a.spans
                for bt, bb in b.spans
            )
            if overlap and abs(a.x - b.x) <= _LINK_PITCH_PT:
                union(len(h_lines) + i, len(h_lines) + j)

    groups: dict[int, tuple[list[HLine], list[VLine]]] = {}
    for i, h in enumerate(h_lines):
        groups.setdefault(find(i), ([], []))[0].append(h)
    for j, v in enumerate(v_lines):
        groups.setdefault(find(len(h_lines) + j), ([], []))[1].append(v)
    return list(groups.values())


# ---------------------------------------------------------------------------
# T2 — grid reconstruction
# ---------------------------------------------------------------------------

def _center(w) -> tuple[float, float]:
    return ((float(w.x0) + float(w.x1)) / 2.0, (float(w.top) + float(w.bottom)) / 2.0)


def _h_covers(h_lines: list[HLine], y: float, x0: float, x1: float) -> bool:
    for h in h_lines:
        if abs(h.y - y) > _SNAP_PT:
            continue
        if h.x0 <= x0 + _SNAP_PT and h.x1 >= x1 - _SNAP_PT:
            return True
    return False


def _v_covers(v_lines: list[VLine], x: float, y0: float, y1: float) -> bool:
    for v in v_lines:
        if abs(v.x - x) > _SNAP_PT:
            continue
        if v.covers(y0, y1):
            return True
    return False


#: Row band verdicts.
_BAND_OK = "ok"
_BAND_SKIP = "skip"
_BAND_INVALID = "invalid"


def _band_segments(
    y0: float, y1: float, xs: list[float], v_lines: list[VLine]
) -> tuple[str, list[list[int]]]:
    """Column spans of one row band.

    A band whose verticals cross it less often than the table has columns
    holds a SPANNING cell: the missing crossings are merged into one cell.
    A gap in the middle of the row (columns covered by no segment) means the
    row does not align with the table at all — the structure is invalid.
    """
    crossings = [v for v in v_lines if v.covers(y0, y1)]
    crossings.sort(key=lambda v: v.x)
    if len(crossings) < 2:
        return _BAND_SKIP, []
    segs: list[list[int]] = []
    for a, b in zip(crossings, crossings[1:]):
        ia = xs.index(a.x)
        ib = xs.index(b.x)
        if ib - 1 < ia:
            continue
        segs.append([ia, ib - 1])
    if not segs:
        return _BAND_SKIP, []
    # A row whose outer verticals do not cross it still owns the full
    # column range: extend the outermost segments to the table edges.
    if segs[0][0] > 0:
        segs[0][0] = 0
    if segs[-1][1] < len(xs) - 2:
        segs[-1][1] = len(xs) - 2
    covered: set[int] = set()
    for s, e in segs:
        covered.update(range(s, e + 1))
    if len(covered) != len(xs) - 1:
        return _BAND_INVALID, []
    return _BAND_OK, segs


def _assign_words(
    words: list,
    bands: list[tuple[float, float, list[list[int]]]],
    xs: list[float],
) -> list[list[list]]:
    """Bucket words into cells (T4): the cell whose rectangle holds the
    word CENTER owns the word."""
    cells: list[list[list]] = []
    for y0, y1, segs in bands:
        row_words = [w for w in words if y0 <= _center(w)[1] <= y1]
        buckets: list[list] = [[] for _ in segs]
        for w in row_words:
            cx = _center(w)[0]
            best = None
            best_d = None
            for i, (c0, c1) in enumerate(segs):
                xa, xb = xs[c0], xs[c1 + 1]
                if xa <= cx <= xb:
                    best = i
                    break
                d = min(abs(cx - xa), abs(cx - xb))
                if best_d is None or d < best_d:
                    best_d = d
                    best = i
            if best is None:
                continue
            buckets[best].append(w)
        cells.append(buckets)
    return cells


def _order_cell_words(words: list) -> list:
    """Reading order inside a cell: line by line, left to right.

    A cell may hold several text lines (a merged header, a question with
    its options). Sorting by x alone would interleave the lines into
    nonsense ("This section Select comprises ..."), so the words are grouped
    into lines first and each line is read left to right.
    """
    ordered = sorted(words, key=lambda w: (float(w.top), float(w.x0)))
    lines: list[list] = []
    anchors: list[float] = []
    for w in ordered:
        tol = max(3.0, 0.6 * float(getattr(w, "size", 0) or 10.0))
        placed = False
        for i, anchor in enumerate(anchors):
            if abs(float(w.top) - anchor) <= tol:
                lines[i].append(w)
                placed = True
                break
        if not placed:
            lines.append([w])
            anchors.append(float(w.top))
    out: list = []
    for line in lines:
        out.extend(sorted(line, key=lambda w: float(w.x0)))
    return out


def _cell_text(words: list, body_size: float = 12.0) -> str:
    """Cell text: the source's own lines, with math assembled like blocks.py.

    A cell may hold several text lines (a merged header, a question with
    its options). Plain prose lines are kept apart with a newline so the
    DOCX builder renders one paragraph per source line. A cell that holds
    stacked math (fractions, integral bounds, raised/lowered scripts) is
    run through the same line assembly as ordinary blocks, which rejoins
    those stacks into one line — a stacked fraction is meaningless once its
    numerator and denominator are separated by a newline.
    """
    # blocks imports this module at import time, so bind it late.
    from . import blocks
    from ..mathengine.normalize import despace_function_names

    ordered = _order_cell_words(words)
    lines: list[list] = []
    anchor = None
    for w in ordered:
        tol = max(3.0, 0.6 * float(getattr(w, "size", 0) or 10.0))
        if anchor is None or abs(float(w.top) - anchor) > tol:
            lines.append([])
            anchor = float(w.top)
        lines[-1].append(w)
    if not lines:
        return ""

    def plain(ls: list[list]) -> str:
        return "\n".join(" ".join(str(x.text) for x in ln) for ln in ls)

    try:
        assembled = blocks._substitute_unmapped_in_lines(lines) or lines
        assembled = blocks._attach_integral_limits(assembled) or assembled
        assembled = blocks._attach_inline_scripts(assembled, body_size) or assembled
        naive = " ".join(" ".join(str(x.text) for x in ln) for ln in assembled)
        joined = blocks._join_lines_with_fractions(assembled, body_size)
    except Exception:
        return plain(lines)
    if len(assembled) > 1 and joined != naive:
        # Stacked math spans lines: the joined, fraction-aware text wins.
        return blocks._sort_options_in_text(despace_function_names(joined))
    return "\n".join(
        despace_function_names(" ".join(str(x.text) for x in ln)) for ln in assembled
    )


# ---------------------------------------------------------------------------
# T6 — header rows
# ---------------------------------------------------------------------------

def _is_bold(word) -> bool:
    return "bold" in str(getattr(word, "fontname", "") or "").lower()


def detect_header_rows(cells_per_row: list[list[Cell]], body_size: float) -> list[int]:
    """Leading rows that repeat as the table header (T6).

    A header row is bold throughout, or set larger than the body text.
    Only a contiguous run of leading rows qualifies, and a table whose every
    row qualifies has no header at all.
    """
    if not cells_per_row:
        return []
    body_size = float(body_size or 0.0)

    def _row_is_header(row: list[Cell]) -> bool:
        filled = [c for c in row if c.words]
        if not filled:
            return False
        bold = all(any(_is_bold(w) for w in c.words) for c in filled)
        sizes = [float(w.size) for c in filled for w in c.words if float(getattr(w, "size", 0) or 0) > 0]
        bigger = bool(sizes) and max(sizes) > body_size + 1.0
        return bold or bigger

    if not _row_is_header(cells_per_row[0]):
        return []
    header = [0]
    for i in range(1, len(cells_per_row)):
        if not _row_is_header(cells_per_row[i]):
            break
        header.append(i)
    if len(header) == len(cells_per_row):
        return []
    return header


# ---------------------------------------------------------------------------
# T3 — column inference for partially ruled tables
# ---------------------------------------------------------------------------

def infer_column_bounds(words: list, x0: float, x1: float) -> list[float]:
    """Column boundaries from word x-centers (T3).

    Words are projected onto the x axis, the occupancy histogram is scanned
    for empty valleys of at least ``_MIN_COL_GAP_PT``, and each valley
    becomes a column separator.
    """
    if not words or x1 <= x0:
        return []
    bins: set[int] = set()
    for w in words:
        cx = _center(w)[0]
        if x0 <= cx <= x1:
            bins.add(int(cx))
    if not bins:
        return []
    ordered = sorted(bins)
    bounds = [x0]
    for a, b in zip(ordered, ordered[1:]):
        gap = b - a - 1
        if gap >= _MIN_COL_GAP_PT:
            bounds.append((a + b) / 2.0)
    bounds.append(x1)
    return bounds


def _separators_are_clean(words: list, bounds: list[float]) -> bool:
    """True when no word straddles a column separator."""
    for w in words:
        cx = _center(w)[0]
        for b in bounds[1:-1]:
            if float(w.x0) < b - 1.0 < float(w.x1):
                return False
            if abs(cx - b) < 0.5:
                return False
    return True


# ---------------------------------------------------------------------------
# T1/T2/T9 — detection
# ---------------------------------------------------------------------------

def _blank_grid(h_lines: list[HLine], v_lines: list[VLine]) -> bool:
    """True for a closed ruled grid with no text (an empty answer form)."""
    if len(h_lines) < 2 or len(v_lines) < 2:
        return False
    xs = sorted(v.x for v in v_lines)
    ys = sorted(h.y for h in h_lines)
    if not _h_covers(h_lines, ys[0], xs[0], xs[-1]):
        return False
    if not _h_covers(h_lines, ys[-1], xs[0], xs[-1]):
        return False
    return _v_covers(v_lines, xs[0], ys[0], ys[-1]) and all(
        _v_covers(v_lines, x, ys[0], ys[-1]) for x in xs
    )


def _build_table(
    h_lines: list[HLine],
    v_lines: list[VLine],
    words: list,
    page_width: float,
    page_height: float,
    body_size: float,
) -> RuledTable | None:
    if len(h_lines) < 2 or len(v_lines) < 2:
        return None
    bbox = (
        min(v.x for v in v_lines),
        min(h.y for h in h_lines),
        max(v.x for v in v_lines),
        max(h.y for h in h_lines),
    )
    area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    grid_like = len(v_lines) >= 4 or len(h_lines) >= 3
    limit = _MAX_PAGE_SHARE_GRID if grid_like else _MAX_PAGE_SHARE
    if area <= 0 or area > limit * float(page_width) * float(page_height):
        return None
    inside = [w for w in words if _inside(w, bbox)]
    blank = not inside and _blank_grid(h_lines, v_lines)
    if len(inside) < _MIN_WORDS and not blank:
        return None

    xs = sorted(v.x for v in v_lines)
    ys = sorted(h.y for h in h_lines)
    bands: list[tuple[float, float, list[list[int]]]] = []
    invalid = False
    for i in range(len(ys) - 1):
        y0, y1 = ys[i], ys[i + 1]
        if y1 - y0 < 1.0:
            continue
        verdict, segs = _band_segments(y0, y1, xs, v_lines)
        if verdict == _BAND_INVALID:
            invalid = True
            break
        if verdict != _BAND_OK:
            # No usable verticals in this band: keep the words (they stay
            # text) but do not treat the band as a row.
            continue
        bands.append((y0, y1, segs))
    if invalid or len({len(segs) for (_y0, _y1, segs) in bands}) > _MAX_ROW_SHAPES:
        # The rows do not agree on the table's shape: the structure cannot
        # be trusted. The caller ships the region as an image crop instead
        # of a broken grid.
        return RuledTable(
            rows=[],
            spans=[],
            cells=[],
            header_rows=[],
            borders=[],
            bbox=bbox,
            parse_status="fallback_image",
            fallback_reason="invalid_structure",
            words=list(inside),
        )
    if not bands:
        return None

    band_words = _assign_words(inside, bands, xs)
    # Words in a skipped band (no crossing verticals) join the nearest band
    # so no text is lost.
    _absorb_skipped(inside, bands, xs, band_words)

    rows: list[list[str]] = []
    spans: list[list[list[int]]] = []
    cells: list[list[Cell]] = []
    borders: list[list[dict]] = []
    for r, (y0, y1, segs) in enumerate(bands):
        row_text = [""] * (len(xs) - 1)
        row_spans: list[list[int]] = []
        row_cells: list[Cell] = []
        row_borders: list[dict] = []
        for i, (c0, c1) in enumerate(segs):
            words_in = band_words[r][i] if i < len(band_words[r]) else []
            text = _cell_text(words_in, body_size)
            row_text[c0] = text
            row_spans.append([c0, c1])
            row_cells.append(Cell(row=r, col=c0, span=c1 - c0 + 1, words=list(words_in), text=text))
            row_borders.append(
                {
                    "top": _h_covers(h_lines, y0, xs[c0], xs[c1 + 1]),
                    "bottom": _h_covers(h_lines, y1, xs[c0], xs[c1 + 1]),
                    "left": _v_covers(v_lines, xs[c0], y0, y1),
                    "right": _v_covers(v_lines, xs[c1 + 1], y0, y1),
                }
            )
        rows.append(row_text)
        spans.append(row_spans)
        cells.append(row_cells)
        borders.append(row_borders)

    consumed = [w for row in cells for c in row for w in c.words]
    return RuledTable(
        rows=rows,
        spans=spans,
        cells=cells,
        header_rows=detect_header_rows(cells, body_size),
        borders=borders,
        column_widths=[round(xs[c + 1] - xs[c], 1) for c in range(len(xs) - 1)],
        bbox=bbox,
        parse_status="ok",
        fallback_reason=None,
        words=consumed,
    )


def _inside(w, bbox) -> bool:
    cx, cy = _center(w)
    return bbox[0] <= cx <= bbox[2] and bbox[1] <= cy <= bbox[3]


def _absorb_skipped(
    inside: list,
    bands: list[tuple[float, float, list[list[int]]]],
    xs: list[float],
    band_words: list[list[list]],
) -> None:
    """Attach words of a skipped band to the nearest real band."""
    if not bands:
        return
    assigned = {id(w) for row in band_words for cell in row for w in cell}
    for w in inside:
        if id(w) in assigned:
            continue
        cy = _center(w)[1]
        best = None
        best_d = None
        for r, (y0, y1, _segs) in enumerate(bands):
            d = 0.0 if y0 <= cy <= y1 else min(abs(cy - y0), abs(cy - y1))
            if best_d is None or d < best_d:
                best_d = d
                best = r
        if best is None:
            continue
        cx = _center(w)[0]
        segs = bands[best][2]
        target = 0
        best_d = None
        for i, (c0, c1) in enumerate(segs):
            xa, xb = xs[c0], xs[c1 + 1]
            d = 0.0 if xa <= cx <= xb else min(abs(cx - xa), abs(cx - xb))
            if best_d is None or d < best_d:
                best_d = d
                target = i
        band_words[best][target].append(w)


def detect_ruled_tables(
    rules: list[Rule],
    words: list,
    page_width: float,
    page_height: float,
    body_size: float = 10.0,
) -> list[RuledTable]:
    """Rebuild every ruled table on a page.

    Returns the tables ordered top-to-bottom. A candidate whose rows cannot
    be tiled against the table's columns is reported with
    ``parse_status="fallback_image"`` so the caller can ship the region as
    an image crop instead of a broken grid.
    """
    if not rules or not words:
        return []
    h_lines = _cluster_h([r for r in rules if r.orientation == "h"])
    v_lines = _cluster_v([r for r in rules if r.orientation == "v"])
    if not h_lines:
        return []
    out: list[RuledTable] = []
    claimed: set[int] = set()
    for comp_h, comp_v in _components(h_lines, v_lines):
        if len(comp_v) < 2:
            # Partially ruled table (horizontal rules only) — T3 infers the
            # columns from the words themselves.
            part = _build_partial_table(comp_h, comp_v, words, page_width, page_height, body_size, claimed)
            if part is not None:
                out.append(part)
                claimed.update(id(w) for w in part.words)
            continue
        table = _build_table(comp_h, comp_v, words, page_width, page_height, body_size)
        if table is None:
            continue
        table.words = [w for w in table.words if id(w) not in claimed]
        claimed.update(id(w) for w in table.words)
        out.append(table)
    out.sort(key=lambda t: (t.bbox[1], t.bbox[0]))
    return out


def _build_partial_table(
    h_lines: list[HLine],
    v_lines: list[VLine],
    words: list,
    page_width: float,
    page_height: float,
    body_size: float,
    claimed: set[int],
) -> RuledTable | None:
    """T3 — a table with horizontal rules only: columns come from the words."""
    if len(h_lines) < 3:
        return None
    ys = sorted(h.y for h in h_lines)
    x0 = min(h.x0 for h in h_lines)
    x1 = max(h.x1 for h in h_lines)
    if x1 <= x0:
        return None
    area = (x1 - x0) * (ys[-1] - ys[0])
    if area <= 0 or area > _MAX_PAGE_SHARE * float(page_width) * float(page_height):
        return None
    inside = [
        w
        for w in words
        if id(w) not in claimed
        and x0 <= _center(w)[0] <= x1
        and ys[0] <= _center(w)[1] <= ys[-1]
    ]
    if len(inside) < _MIN_WORDS:
        return None
    bounds = infer_column_bounds(inside, x0, x1)
    if len(bounds) < 3:
        return None
    if not _separators_are_clean(inside, bounds):
        return None
    rows: list[list[str]] = []
    spans: list[list[list[int]]] = []
    cells: list[list[Cell]] = []
    borders: list[list[dict]] = []
    consumed: list = []
    for r in range(len(ys) - 1):
        y0, y1 = ys[r], ys[r + 1]
        row_words = [w for w in inside if y0 <= _center(w)[1] <= y1]
        if not row_words:
            continue
        row_text = [""] * (len(bounds) - 1)
        row_spans: list[list[int]] = []
        row_cells: list[Cell] = []
        row_borders: list[dict] = []
        for c in range(len(bounds) - 1):
            xa, xb = bounds[c], bounds[c + 1]
            cell_words = [w for w in row_words if xa <= _center(w)[0] <= xb]
            cell_words.sort(key=lambda w: float(w.x0))
            text = _cell_text(cell_words, body_size)
            row_text[c] = text
            row_spans.append([c, c])
            row_cells.append(Cell(row=len(rows), col=c, span=1, words=list(cell_words), text=text))
            row_borders.append(
                {
                    "top": _h_covers(h_lines, y0, xa, xb),
                    "bottom": _h_covers(h_lines, y1, xa, xb),
                    "left": False,
                    "right": False,
                }
            )
            consumed.extend(cell_words)
        rows.append(row_text)
        spans.append(row_spans)
        cells.append(row_cells)
        borders.append(row_borders)
    if len(rows) < 2:
        return None
    bbox = (x0, ys[0], x1, ys[-1])
    return RuledTable(
        rows=rows,
        spans=spans,
        cells=cells,
        header_rows=detect_header_rows(cells, body_size),
        borders=borders,
        bbox=bbox,
        parse_status="ok",
        fallback_reason=None,
        words=consumed,
    )


# ---------------------------------------------------------------------------
# T8 — caption binding
# ---------------------------------------------------------------------------

def _group_lines(words: list) -> list[list]:
    lines: list[list] = []
    for w in sorted(words, key=lambda w: (float(w.top), float(w.x0))):
        for line in lines:
            if abs(float(line[0].top) - float(w.top)) <= 3.0:
                line.append(w)
                break
        else:
            lines.append([w])
    return lines


def find_caption(words: list, bbox) -> tuple[str, str, list] | None:
    """Bind a caption line to a table (T8).

    A caption sits within ``_CAPTION_GAP_PT`` above or below the table, its
    text starts with a caption label ("Table 3", "Fig. 2") and its x-range
    overlaps the table's. Returns ``(text, side, words)`` with side
    ``"above"`` or ``"below"``.
    """
    if not words:
        return None
    x0, top, x1, bottom = bbox
    bands = (
        ("above", top - _CAPTION_GAP_PT, top, "bottom"),
        ("below", bottom, bottom + _CAPTION_GAP_PT, "top"),
    )
    for side, lo, hi, edge in bands:
        band = []
        for w in words:
            try:
                value = float(getattr(w, edge))
            except (AttributeError, TypeError, ValueError):
                continue
            if lo <= value <= hi:
                band.append(w)
        if not band:
            continue
        for line in _group_lines(band):
            ordered = sorted(line, key=lambda w: float(w.x0))
            text = " ".join(str(w.text) for w in ordered).strip()
            if not text or not _CAPTION_RE.match(text):
                continue
            lx0 = min(float(w.x0) for w in ordered)
            lx1 = max(float(w.x1) for w in ordered)
            if lx1 < x0 or lx0 > x1:
                continue
            return text, side, ordered
    return None
