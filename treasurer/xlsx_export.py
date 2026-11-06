"""The whole book as one Excel file: no Google account, no sharing.

Same tabs and the same look as the Google Sheet (both are drawn from the View looks in
views.py), so a club can open it in Excel, or import it into its own Google Sheet with
File > Import, and nobody has to give Tallyable access to anything.
"""
from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import sheet_format as fmt
from .views import LINE, SLATE, View

MONEY = fmt.ACCOUNTING
EDGE = Side(style="thin", color=LINE)


def _hex(c: dict) -> str:
    return "".join(f"{round(c.get(k, 0) * 255):02X}" for k in ("red", "green", "blue"))


def _style(ws, look: dict) -> None:
    (r0, r1), (c0, c1) = look["rows"], look["cols"]
    if r1 <= r0 or c1 <= c0:
        return
    for r in range(r0, r1):
        for c in range(c0, c1):
            cell = ws.cell(row=r + 1, column=c + 1)
            if "fill" in look:
                cell.fill = PatternFill("solid", fgColor=look["fill"])
            if any(k in look for k in ("bold", "italic", "size", "color")):
                f = cell.font
                cell.font = Font(bold=look.get("bold", f.bold), italic=look.get("italic", f.italic),
                                 size=look.get("size", f.size), color=look.get("color", f.color))
            if "align" in look:
                cell.alignment = Alignment(horizontal=look["align"], vertical="center")
            if look.get("money"):
                cell.number_format = MONEY
            if look.get("border") == "grid":
                cell.border = Border(left=EDGE, right=EDGE, top=EDGE, bottom=EDGE)
            elif look.get("border") == "topbottom":
                cell.border = Border(left=cell.border.left, right=cell.border.right, top=EDGE, bottom=EDGE)
    if look.get("merge") and (r1 - r0 > 1 or c1 - c0 > 1):
        ws.merge_cells(start_row=r0 + 1, start_column=c0 + 1, end_row=r1, end_column=c1)


def _view(ws, view: View) -> None:
    for r, row in enumerate(view.grid):
        for c, v in enumerate(row):
            ws.cell(row=r + 1, column=c + 1, value=v if v != "" else None)
    for look in view.looks:
        _style(ws, look)
    ws.freeze_panes = ws.cell(row=view.freeze_rows + 1, column=view.freeze_cols + 1)
    _widths(ws, view.grid[1:])


def _tidy(ws, header: list[str], rows: list[dict], money: set[str]) -> None:
    ws.append(header)
    _style(ws, {"rows": (0, 1), "cols": (0, len(header)), "fill": SLATE, "color": "FFFFFF", "bold": True})
    for rec in rows:
        ws.append([rec.get(h, "") for h in header])
    for c, h in enumerate(header):
        if h in money:
            for r in range(2, len(rows) + 2):
                ws.cell(row=r, column=c + 1).number_format = MONEY
    ws.freeze_panes = "A2"
    _widths(ws, [header, *[[rec.get(h, "") for h in header] for rec in rows]])


def _widths(ws, grid: list[list]) -> None:
    cols = max((len(r) for r in grid), default=0)
    for c in range(cols):
        longest = max((len(fmt._text(r[c])) for r in grid if c < len(r)), default=0)
        ws.column_dimensions[get_column_letter(c + 1)].width = min(max(longest * 1.15 + 3, 8), 60)


def book_xlsx(views: dict[str, View], transactions: list[dict], tx_fields: list[str]) -> bytes:
    """Report tabs first, then the line-item data. Returns the .xlsx file's bytes."""
    wb = Workbook()
    wb.remove(wb.active)
    for title, view in views.items():
        ws = wb.create_sheet(title[:31])  # Excel's tab-name limit
        ws.sheet_properties.tabColor = _hex(fmt.REPORT_TAB)
        _view(ws, view)
    ws = wb.create_sheet("Transactions")
    ws.sheet_properties.tabColor = _hex(fmt.DATA_TAB)
    _tidy(ws, tx_fields, transactions, fmt.TIDY_MONEY)
    out = BytesIO()
    wb.save(out)
    return out.getvalue()
