"""The whole book as one Excel file: no Google account, no sharing.

Same tabs and the same look as the formatted Google Sheet (see sheet_format.py),
so a club can open it in Excel, or import it into its own Google Sheet with
File > Import, and nobody has to give Tallyable access to anything.
"""
from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from . import sheet_format as fmt

MONEY = '"$"#,##0.00'


def _hex(c: dict) -> str:
    return "".join(f"{round(c.get(k, 0) * 255):02X}" for k in ("red", "green", "blue"))


HEADER = PatternFill("solid", fgColor=_hex(fmt.HEADER_BG))
WHITE_BOLD = Font(bold=True, color=_hex(fmt.WHITE))
FILLS = {k: PatternFill("solid", fgColor=_hex(v)) for k, v in fmt.SECTION.items()}
TOTAL = PatternFill("solid", fgColor=_hex(fmt.TOTAL_BG))
NOTE = Font(italic=True, size=9, color=_hex(fmt.NOTE_FG))


def _paint(ws, r: int, c0: int, c1: int, fill=None, font=None) -> None:
    for c in range(c0, c1):
        cell = ws.cell(row=r + 1, column=c + 1)
        if fill:
            cell.fill = fill
        if font:
            cell.font = font


def _view(ws, grid: list[list]) -> None:
    """A report tab: the same rules as sheet_format.view_requests."""
    freeze = 1
    for r, row in enumerate(grid):
        for c, v in enumerate(row):
            cell = ws.cell(row=r + 1, column=c + 1, value=v if v != "" else None)
            if isinstance(v, float):
                cell.number_format = MONEY
        if r == 0:
            _paint(ws, 0, 0, 1, font=NOTE)
            continue
        for c, v in enumerate(row):
            if not isinstance(v, str) or not v:
                continue
            if v == "LOCATION" or (c == 0 and v in fmt.HEADER_LABELS):
                _paint(ws, r, c, c + 3 if v == "LOCATION" else len(row), HEADER, WHITE_BOLD)
                freeze = max(freeze, r + 1)
                if v != "LOCATION":
                    break
            elif v in fmt.SECTION:
                _paint(ws, r, c, c + 3, FILLS[v], Font(bold=True))
            elif v in fmt.TOTALS:
                _paint(ws, r, c, c + (2 if v == "TOTAL" else 3), TOTAL, Font(bold=True))
            elif r == 1:
                _paint(ws, r, c, c + 1, font=Font(bold=True, size=12))
    ws.freeze_panes = ws.cell(row=freeze + 1, column=1)
    _widths(ws, grid[1:])


def _tidy(ws, header: list[str], rows: list[dict], money: set[str]) -> None:
    ws.append(header)
    _paint(ws, 0, 0, len(header), HEADER, WHITE_BOLD)
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
        longest = max((len(f"{r[c]:,.2f}" if isinstance(r[c], float) else str(r[c])) for r in grid if c < len(r)),
                      default=0)
        ws.column_dimensions[get_column_letter(c + 1)].width = min(max(longest + 2, 8), 50)


def book_xlsx(views: dict[str, list[list]], transactions: list[dict], tx_fields: list[str]) -> bytes:
    """Report tabs first, then the line-item data. Returns the .xlsx file's bytes."""
    wb = Workbook()
    wb.remove(wb.active)
    for title, grid in views.items():
        ws = wb.create_sheet(title[:31])  # Excel's tab-name limit
        ws.sheet_properties.tabColor = _hex(fmt.REPORT_TAB)
        _view(ws, grid)
    ws = wb.create_sheet("Transactions")
    ws.sheet_properties.tabColor = _hex(fmt.DATA_TAB)
    _tidy(ws, tx_fields, transactions, fmt.TIDY_MONEY)
    out = BytesIO()
    wb.save(out)
    return out.getvalue()
