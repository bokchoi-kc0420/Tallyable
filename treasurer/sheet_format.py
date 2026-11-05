"""Make the Google Sheet easy to read. Pure functions that build Sheets API
`batchUpdate` requests from the same grids the sink writes, so they are tested
without a network.

What a treasurer sees after a push:
- Report tabs first (Expense Report, Balance Sheets, Ledger), in teal. Data tabs
  the tool keeps (Transactions, Events, Reimbursements) last, in gray.
- Header rows bold on a dark band and frozen, so they stay put while scrolling.
- Money as $1,234.50. Section rows (ASSETS, LIABILITIES) tinted, totals bold.
- Columns sized to their contents; the "built by Tallyable" note in small gray italics.

Formatting is cosmetic: if a request fails, the push has already succeeded.
"""
from __future__ import annotations

MONEY = {"numberFormat": {"type": "CURRENCY", "pattern": "$#,##0.00"}}
HEADER_BG = {"red": 0.06, "green": 0.36, "blue": 0.34}       # dark teal
WHITE = {"red": 1, "green": 1, "blue": 1}
ASSET_BG = {"red": 0.88, "green": 0.96, "blue": 0.91}        # light green
LIAB_BG = {"red": 0.99, "green": 0.91, "blue": 0.89}         # light red
TOTAL_BG = {"red": 0.94, "green": 0.95, "blue": 0.96}        # light gray
NOTE_FG = {"red": 0.45, "green": 0.47, "blue": 0.5}
REPORT_TAB = {"red": 0.06, "green": 0.46, "blue": 0.43}
DATA_TAB = {"red": 0.6, "green": 0.62, "blue": 0.65}

HEADER_LABELS = {"DATE", "Place"}  # first cell of a full-width header row (Ledger, Expense Report)
SECTION = {"ASSETS": ASSET_BG, "LIABILITIES": LIAB_BG}
TOTALS = {"TOTAL ASSETS", "TOTAL LIABILITIES", "TOTAL BALANCE", "TOTAL"}
TIDY_MONEY = {"price", "amount", "receipt_tax", "receipt_tip", "receipt_total", "receipt_posted",
              "Zelle", "Venmo", "Cash", "National KSEA funding"}


def _range(sheet_id: int, r0: int, r1: int, c0: int, c1: int) -> dict:
    return {"sheetId": sheet_id, "startRowIndex": r0, "endRowIndex": r1, "startColumnIndex": c0, "endColumnIndex": c1}


def _paint(sheet_id: int, r0: int, r1: int, c0: int, c1: int, fmt: dict) -> dict:
    fields = ",".join(f"userEnteredFormat.{k}" for k in fmt)
    return {"repeatCell": {"range": _range(sheet_id, r0, r1, c0, c1), "cell": {"userEnteredFormat": fmt},
                           "fields": fields}}


def _freeze(sheet_id: int, rows: int) -> dict:
    return {"updateSheetProperties": {"properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": rows}},
                                      "fields": "gridProperties.frozenRowCount"}}


def _widths(sheet_id: int, grid: list[list], skip_rows: int = 0) -> list[dict]:
    """Size each column to its longest value (about 7 px a character), within limits."""
    cols = max((len(r) for r in grid), default=0)
    out = []
    for c in range(cols):
        longest = max((len(_text(r[c])) for r in grid[skip_rows:] if c < len(r)), default=0)
        px = min(max(longest * 7 + 24, 60), 360)
        out.append({"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": c, "endIndex": c + 1},
            "properties": {"pixelSize": px}, "fields": "pixelSize"}})
    return out


def _text(v) -> str:
    return f"{v:,.2f}" if isinstance(v, float) else str(v)


def _reset(sheet_id: int) -> dict:
    """Clear old formatting, since a view's rows move around between pushes."""
    return {"repeatCell": {"range": {"sheetId": sheet_id}, "cell": {"userEnteredFormat": {}},
                           "fields": "userEnteredFormat"}}


def view_requests(sheet_id: int, grid: list[list]) -> list[dict]:
    """Formatting for a rebuilt view (Balance Sheet, Ledger, Expense Report)."""
    reqs = [_reset(sheet_id)]
    if not grid:
        return reqs
    # The "built by Tallyable" note on row 1.
    reqs.append(_paint(sheet_id, 0, 1, 0, 1, {"textFormat": {"italic": True, "fontSize": 9, "foregroundColor": NOTE_FG}}))
    freeze = 1
    for r, row in enumerate(grid[1:], start=1):
        for c, v in enumerate(row):
            if not isinstance(v, str) or not v:
                continue
            if v == "LOCATION" or (c == 0 and v in HEADER_LABELS):
                # Column headers: one 3-column block on the balance sheet, the whole row elsewhere.
                end = c + 3 if v == "LOCATION" else len(row)
                reqs.append(_paint(sheet_id, r, r + 1, c, end, {
                    "backgroundColor": HEADER_BG, "textFormat": {"bold": True, "foregroundColor": WHITE}}))
                freeze = max(freeze, r + 1)
                if v != "LOCATION":
                    break  # the rest of this row is header text, not totals
            elif v in SECTION:
                reqs.append(_paint(sheet_id, r, r + 1, c, c + 3, {"backgroundColor": SECTION[v],
                                                                  "textFormat": {"bold": True}}))
            elif v in TOTALS:
                span = 2 if v == "TOTAL" else 3
                reqs.append(_paint(sheet_id, r, r + 1, c, c + span, {"backgroundColor": TOTAL_BG,
                                                                     "textFormat": {"bold": True}}))
            elif r == 1:  # event titles above the headers
                reqs.append(_paint(sheet_id, 1, 2, c, c + 3, {"textFormat": {"bold": True, "fontSize": 12}}))
    reqs += _money_runs(sheet_id, grid)
    reqs.append(_freeze(sheet_id, freeze))
    reqs += _widths(sheet_id, grid, skip_rows=1)
    return reqs


def _money_runs(sheet_id: int, grid: list[list]) -> list[dict]:
    """Currency format on each unbroken vertical run of number cells."""
    reqs = []
    width = max((len(r) for r in grid), default=0)
    for c in range(width):
        start = None
        for r in range(len(grid) + 1):
            is_money = r < len(grid) and c < len(grid[r]) and isinstance(grid[r][c], float)
            if is_money and start is None:
                start = r
            elif not is_money and start is not None:
                reqs.append(_paint(sheet_id, start, r, c, c + 1, MONEY))
                start = None
    return reqs


def tidy_requests(sheet_id: int, header: list[str], rows: int) -> list[dict]:
    """Formatting for a data tab the tool appends to (Transactions, Events, Reimbursements)."""
    reqs = [_paint(sheet_id, 0, 1, 0, len(header), {"backgroundColor": HEADER_BG,
                                                    "textFormat": {"bold": True, "foregroundColor": WHITE}}),
            _freeze(sheet_id, 1)]
    for c, name in enumerate(header):
        if name in TIDY_MONEY:
            reqs.append(_paint(sheet_id, 1, max(rows, 2), c, c + 1, MONEY))
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
