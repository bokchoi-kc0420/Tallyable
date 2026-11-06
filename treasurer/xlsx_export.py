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
from .views import INK, LINE, SLATE, View

MONEY = fmt.ACCOUNTING
EDGE = Side(style="thin", color=LINE)
BOX = Side(style="medium", color=INK)
PX_PER_CHAR = 7  # Excel column width is in characters, about 7 px each
FONT = "Arial"  # what Google Sheets uses, so both files look the same


def _hex(c: dict) -> str:
    return "".join(f"{round(c.get(k, 0) * 255):02X}" for k in ("red", "green", "blue"))


def _style(ws, look: dict) -> None:
    (r0, r1), (c0, c1) = look["rows"], look["cols"]
    if r1 <= r0 or c1 <= c0:
        return
    for r in range(r0, r1):
        for c in range(c0, c1):
            _style_cell(ws.cell(row=r + 1, column=c + 1), look, (r, c), (r0, r1, c0, c1))
    if look.get("merge") and (r1 - r0 > 1 or c1 - c0 > 1):
        ws.merge_cells(start_row=r0 + 1, start_column=c0 + 1, end_row=r1, end_column=c1)


def _style_cell(cell, look: dict, at: tuple, rng: tuple) -> None:
    if "fill" in look:
        cell.fill = PatternFill("solid", fgColor=look["fill"])
    if any(k in look for k in ("bold", "italic", "size", "color", "strike")):
        f = cell.font
        cell.font = Font(name=FONT, bold=look.get("bold", f.bold), italic=look.get("italic", f.italic),
                         strike=look.get("strike", f.strike), size=look.get("size", f.size), color=look.get("color", f.color))
    if any(k in look for k in ("align", "valign", "wrap")):
        a = cell.alignment
        cell.alignment = Alignment(horizontal=look.get("align", a.horizontal),
                                   vertical="center" if look.get("valign") else a.vertical,
                                   wrap_text=look.get("wrap", a.wrap_text))
    if look.get("money"):
        cell.number_format = fmt.DOLLARS if look["money"] == "plain" else MONEY
    _edge(cell, look.get("border"), at, rng)


def _edge(cell, kind, at: tuple, rng: tuple) -> None:
    (r, c), (r0, r1, c0, c1) = at, rng
    b = cell.border
    if kind == "grid":
        cell.border = Border(left=EDGE, right=EDGE, top=EDGE, bottom=EDGE)
    elif kind == "topbottom":
        cell.border = Border(left=b.left, right=b.right, top=EDGE, bottom=EDGE)
    elif kind == "box":
        cell.border = Border(left=BOX if c == c0 else b.left, right=BOX if c == c1 - 1 else b.right,
                             top=BOX if r == r0 else b.top, bottom=BOX if r == r1 - 1 else b.bottom)


def _view(ws, view: View) -> None:
    width = max((len(r) for r in view.grid), default=0)
    for r, row in enumerate(view.grid):
        for c in range(width):
            cell = ws.cell(row=r + 1, column=c + 1, value=row[c] if c < len(row) and row[c] != "" else None)
            cell.font = Font(name=FONT, size=10)
    for look in view.looks:
        _style(ws, look)
    ws.freeze_panes = ws.cell(row=view.freeze_rows + 1, column=view.freeze_cols + 1)
    if view.widths:
        for c, px in enumerate(view.widths):
            ws.column_dimensions[get_column_letter(c + 1)].width = px / PX_PER_CHAR
    else:
        _widths(ws, view.grid[1:])
    for r, px in view.heights.items():
        ws.row_dimensions[r + 1].height = px * 0.75  # Excel row height is in points
    if view.filter:
        r0, r1, c0, c1 = view.filter
        ws.auto_filter.ref = f"{get_column_letter(c0 + 1)}{r0 + 1}:{get_column_letter(c1)}{r1}"
    _print_setup(ws, view)


def _print_setup(ws, view: View) -> None:
    """Prints as it looks: no gridlines, one page wide, the frozen header repeated on every page."""
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape" if view.landscape else "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_LETTER
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = ws.page_margins.right = 0.5
    ws.print_options.horizontalCentered = True
    if view.freeze_rows > 1:
        ws.print_title_rows = f"{view.freeze_rows}:{view.freeze_rows}"
    ws.oddFooter.center.text = "&8Page &P of &N"


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
