"""Make the Google Sheet look like the club's own. Pure functions that turn a View's looks
(see views.py) into Sheets API `batchUpdate` requests, so they are tested without a network.

What a treasurer sees after a push:
- Report tabs first (Expense Report, Balance Sheets, Ledger), in teal. Data tabs
  the tool keeps (Transactions, Events, Reimbursements) last, in gray.
- The report tabs in the club's format: colors, merged cells, borders and accounting
  dollars as drawn in views.py. Header rows frozen, so they stay put while scrolling.
- Columns sized to their contents.

Formatting is cosmetic: if a request fails, the push has already succeeded.
"""
from __future__ import annotations

from .views import LINE, SLATE

# Accounting dollars, as the club's sheets show them: "$" at the left edge, the amount at the right.
ACCOUNTING = '_("$"* #,##0.00_);_("$"* \\(#,##0.00\\);_("$"* "-"??_);_(@_)'
MONEY = {"numberFormat": {"type": "CURRENCY", "pattern": ACCOUNTING}}
REPORT_TAB = {"red": 0.06, "green": 0.46, "blue": 0.43}
DATA_TAB = {"red": 0.6, "green": 0.62, "blue": 0.65}
TIDY_MONEY = {"price", "amount", "receipt_tax", "receipt_tip", "receipt_total", "receipt_posted"}


def rgb(hex_color: str) -> dict:
    """"C9A57D" -> the {"red", "green", "blue"} dict Sheets takes."""
    return {k: int(hex_color[n:n + 2], 16) / 255 for k, n in (("red", 0), ("green", 2), ("blue", 4))}


def _range(sheet_id: int, r0: int, r1: int, c0: int, c1: int) -> dict:
    return {"sheetId": sheet_id, "startRowIndex": r0, "endRowIndex": r1, "startColumnIndex": c0, "endColumnIndex": c1}


def _paint(sheet_id: int, rng: tuple, fmt: dict) -> dict:
    """Set only the fields `fmt` names, so a later look (say, red text) keeps an earlier fill."""
    fields = []
    for k, v in fmt.items():
        fields += [f"userEnteredFormat.{k}.{sub}" for sub in v] if k == "textFormat" else [f"userEnteredFormat.{k}"]
    return {"repeatCell": {"range": _range(sheet_id, *rng), "cell": {"userEnteredFormat": fmt},
                           "fields": ",".join(fields)}}


def _freeze(sheet_id: int, rows: int, cols: int = 0) -> dict:
    return {"updateSheetProperties": {"properties": {"sheetId": sheet_id, "gridProperties": {
        "frozenRowCount": rows, "frozenColumnCount": cols}},
        "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"}}


def _widths(sheet_id: int, grid: list[list], skip_rows: int = 0) -> list[dict]:
    """Size each column to its longest value (about 7 px a character), within limits."""
    cols = max((len(r) for r in grid), default=0)
    out = []
    for c in range(cols):
        longest = max((len(_text(r[c])) for r in grid[skip_rows:] if c < len(r)), default=0)
        px = min(max(longest * 7 + 30, 60), 360)
        out.append({"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": c, "endIndex": c + 1},
            "properties": {"pixelSize": px}, "fields": "pixelSize"}})
    return out


def _text(v) -> str:
    return f"${v:,.2f}" if isinstance(v, float) else str(v)


def cell_format(look: dict) -> dict:
    """A look's fill, font, alignment and number format as a Sheets userEnteredFormat."""
    out: dict = {}
    if "fill" in look:
        out["backgroundColor"] = rgb(look["fill"])
    text = {k: look[k] for k in ("bold", "italic") if k in look}
    if "size" in look:
        text["fontSize"] = look["size"]
    if "color" in look:
        text["foregroundColor"] = rgb(look["color"])
    if text:
        out["textFormat"] = text
    if "align" in look:
        out["horizontalAlignment"] = look["align"].upper()
    if look.get("money"):
        out |= MONEY
    return out


def _border(sheet_id: int, rng: tuple, kind: str) -> dict:
    line = {"style": "SOLID", "colorStyle": {"rgbColor": rgb(LINE)}}
    sides = ["top", "bottom"] if kind == "topbottom" else ["top", "bottom", "left", "right",
                                                           "innerHorizontal", "innerVertical"]
    return {"updateBorders": {"range": _range(sheet_id, *rng), **{s: line for s in sides}}}


def view_requests(sheet_id: int, view) -> list[dict]:
    """Formatting for a rebuilt report tab. Old formatting and merges are cleared first,
    since a view's rows move around between pushes."""
    reqs = [{"repeatCell": {"range": {"sheetId": sheet_id}, "cell": {"userEnteredFormat": {}},
                            "fields": "userEnteredFormat"}},
            {"unmergeCells": {"range": {"sheetId": sheet_id}}}]
    for look in view.looks:
        rng = (*look["rows"], *look["cols"])
        fmt = cell_format(look)
        if fmt:
            reqs.append(_paint(sheet_id, rng, fmt))
        if look.get("merge"):
            reqs.append({"mergeCells": {"range": _range(sheet_id, *rng), "mergeType": "MERGE_ALL"}})
        if "border" in look:
            reqs.append(_border(sheet_id, rng, look["border"]))
    reqs.append(_freeze(sheet_id, view.freeze_rows, view.freeze_cols))
    reqs += _widths(sheet_id, view.grid, skip_rows=1)  # the long note on row 1 doesn't set a width
    return reqs


def tidy_requests(sheet_id: int, header: list[str], rows: int, money: set[str] = frozenset()) -> list[dict]:
    """Formatting for a data tab the tool appends to (Transactions, Events, Reimbursements)."""
    reqs = [_paint(sheet_id, (0, 1, 0, len(header)), cell_format({"fill": SLATE, "color": "FFFFFF", "bold": True})),
            _freeze(sheet_id, 1)]
    for c, name in enumerate(header):
        if name in TIDY_MONEY or name in money:
            reqs.append(_paint(sheet_id, (1, max(rows, 2), c, c + 1), MONEY))
    reqs += _widths(sheet_id, [header, *[["x" * 12] * len(header)]])
    return reqs


def order_requests(tabs: list[tuple[int, str]], data_tabs: set[str]) -> list[dict]:
    """Report tabs first and teal, data tabs last and gray. `tabs` is (sheet_id, title)."""
    def rank(title: str) -> tuple:
        if title.startswith("Expense Report"):
            return (0, title)
        if title.startswith("Balance Sheet:"):
            return (1, title)
        if title == "Balance Sheet":
            return (2, title)
        if title == "Ledger":
            return (3, title)
        if title in data_tabs:
            return (5, title)
        return (4, title)  # anything the treasurer added stays in the middle
    reqs = []
    for index, (sid, title) in enumerate(sorted(tabs, key=lambda t: rank(t[1]))):
        props = {"sheetId": sid, "index": index}
        fields = "index"
        if rank(title)[0] != 4:
            props["tabColorStyle"] = {"rgbColor": DATA_TAB if title in data_tabs else REPORT_TAB}
            fields += ",tabColorStyle"
        reqs.append({"updateSheetProperties": {"properties": props, "fields": fields}})
    return reqs
