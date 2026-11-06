"""The report tabs, drawn in the club's own sheet format. Pure functions: tidy rows in,
a View out. No network, so the Sheets sink, the Excel download and the tests all draw
exactly the same thing.

A View is the grid of values plus its look: fills, fonts, borders, merges and money
format, as plain ranges. sheet_format.py turns the look into Google Sheets requests,
xlsx_export.py into Excel styles. Colors follow the club's sheets:
- Balance Sheet: one section per event, stacked: total cards, then assets (tan) on the
  left and one row per receipt (gray) on the right.
- The Expense Report (expense_view.py) and the General Ledger and Receipts tabs
  (ledger_view.py) use the same View and colors.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .models import cell_decimal as D

VIEW_NOTE = "Built by Tallyable from the Transactions, Events and Reimbursements tabs. Edits here are overwritten on the next push."
BASE_EVENT_FIELDS = ["event_id", "name", "date", "attendees", "start_balance"]
BALANCE = "Balance Sheet"

# Colors: tan and gray balance-sheet panels, a dark slate header
# and pale tinted columns. Red only marks what needs a look (no payer, a negative balance).
TAN, GRAY, BEIGE = "C9A57D", "BDBDBD", "FBF2E8"
SLATE, RED, NOTE_GRAY, LINE = "3D4451", "D93025", "73787F", "B7B7B7"
DARK, MID, INK, TINT, TINT2, MUTED = "333F4F", "595959", "222A35", "EAEEF4", "F2F2F2", "6B7280"


@dataclass
class View:
    """A report tab: values plus how they look. A look is a dict with `rows` and `cols`
    (half-open, zero-based) and any of: fill, color (hex), bold, italic, strike, size,
    align, valign ("middle"), wrap, money (True = accounting, "plain" = $1.00), border ("grid", "box" or "topbottom"), merge.
    `widths` are column widths in pixels, chosen so the tab fits a letter page
    (`landscape` for wide ones); without them columns are sized to their contents.
    `heights` are row heights in pixels; `filter` is the (r0, r1, c0, c1) to put filter
    buttons on."""
    grid: list[list]
    looks: list[dict] = field(default_factory=list)
    freeze_rows: int = 1
    freeze_cols: int = 0
    widths: list[int] = field(default_factory=list)
    heights: dict[int, int] = field(default_factory=dict)
    landscape: bool = False
    filter: tuple | None = None

    def look(self, r0: int, r1: int, c0: int, c1: int, **style) -> None:
        self.looks.append({"rows": (r0, r1), "cols": (c0, c1), **style})


def num(x: Decimal) -> float:
    """Decimal -> number for the sheet, so Sheets can sum it."""
    return float(x)


def income_sources(event: dict) -> list[str]:
    """The income columns of an Events row, in sheet order."""
    return [k for k in event if k not in BASE_EVENT_FIELDS]


def is_returned(row: dict) -> bool:
    """A Transactions row's `returned` cell, which comes back as TRUE/FALSE text or a bool."""
    return str(row["returned"]).upper() == "TRUE"


def group(tx: list[dict]) -> OrderedDict[str, OrderedDict[str, list[dict]]]:
    """event_id -> receipt_id -> line-item rows, in the order they were posted."""
    out: OrderedDict = OrderedDict()
    for row in tx:
        out.setdefault(row["event_id"], OrderedDict()).setdefault(row["receipt_id"], []).append(row)
    return out


def _note(view: View) -> None:
    view.look(0, 1, 0, 1, italic=True, size=9, color=NOTE_GRAY)


# ---------- Balance Sheet ----------

GREEN = "1E7B4F"
BALANCE_WIDTHS = [150, 92, 24, 190, 80, 70, 92]  # assets | gap | liabilities: fits a portrait page


def _event_section(e: dict, receipts: list[list[dict]], top: int, view: View) -> list[list]:
    """One event: its name, three total cards, then assets on the left and one row per
    receipt on the right. Item detail lives on the Expense Report; the receipt number ties a
    row to its photo and its Receipts-tab row."""
    sources = income_sources(e)
    t_in = sum((D(e.get(s) or 0) for s in sources), Decimal("0"))
    t_out = sum((D(items[0]["receipt_posted"]) for items in receipts), Decimal("0"))
    n = max(len(sources), len(receipts), 1)
    rows = [[f"{e['name']} ({e['date']})", *[""] * 6],
            ["TOTAL ASSETS", "", "TOTAL LIABILITIES", "", "", "BALANCE", ""],
            [num(t_in), "", num(t_out), "", "", num(t_in - t_out), ""],
            ["ASSETS", "", "", "LIABILITIES", "Date", "Receipt", "Total"],
            *[["", "", "", "", "", "", ""] for _ in range(n)],
            ["Total", num(t_in), "", "Total", "", "", num(t_out)], []]
    body, end = top + 4, top + 4 + n
    for k, s in enumerate(sources):
        rows[4 + k][:2] = [s, num(D(e.get(s) or 0))]
    for k, items in enumerate(receipts):
        f = items[0]
        when = date.fromisoformat(str(f["date"])[:10]).strftime("%m/%d")
        rows[4 + k][3:] = [f["place"], when, f["receipt_id"], num(D(f["receipt_posted"]))]

    view.look(top, top + 1, 0, 7, merge=True, bold=True, size=13, color=INK, valign="middle")
    for c0, c1, head, fill in ((0, 2, TAN, BEIGE), (2, 5, GRAY, BEIGE), (5, 7, INK, TINT)):  # the cards
        view.look(top + 1, top + 2, c0, c1, merge=True, fill=head, color="FFFFFF" if head == INK else INK,
                  bold=True, size=9, align="center")
        view.look(top + 2, top + 3, c0, c1, merge=True, fill=fill, bold=True, size=16, align="center",
                  money="plain", border="box")
    view.look(top + 2, top + 3, 5, 7, color=RED if t_in < t_out else GREEN)
    view.look(top + 3, top + 4, 0, 2, fill=TAN, bold=True, color=INK)
    view.look(top + 3, top + 4, 3, 7, fill=GRAY, bold=True, color=INK, size=9)
    view.look(top + 3, top + 4, 3, 4, size=10)
    view.look(body, end, 0, 2, fill=BEIGE)
    view.look(body, end, 3, 7, fill="F7F7F7")
    view.look(body, body + len(sources), 0, 2, border="grid")
    view.look(body, body + len(receipts), 3, 7, border="grid")
    view.look(body, body + len(receipts), 3, 4, bold=True)
    view.look(body, body + len(receipts), 4, 6, color=MUTED, align="center")
    view.look(body, end + 1, 1, 2, money=True)
    view.look(body, end + 1, 6, 7, money=True)
    for c0, c1 in ((0, 2), (3, 7)):
        view.look(end, end + 1, c0, c1, bold=True, fill="E4E8EE", border="topbottom")
        view.look(top + 3, end + 1, c0, c1, border="box")
    return rows


def render_balance_sheet(events: list[dict], tx: list[dict]) -> View:
    """A title, then one section per event, by date, one under the other: assets on the
    left, liabilities on the right."""
    grouped = group(tx)
    grid = [[VIEW_NOTE], ["Balance Sheet"], []]
    view = View(grid, freeze_rows=2, widths=BALANCE_WIDTHS, heights={1: 36})
    for e in sorted(events, key=lambda e: str(e["date"])):
        receipts = sorted(grouped.get(e["event_id"], OrderedDict()).values(),
                          key=lambda items: (str(items[0]["date"]), items[0]["receipt_id"]))
        grid.extend(_event_section(e, receipts, len(grid), view))
    _note(view)
    view.look(1, 2, 0, 3, merge=True, bold=True, size=20, color=INK, valign="middle")
    return view


def grid_to_csv(grid: list[list]) -> str:
    import csv
    import io
    buf = io.StringIO()
    csv.writer(buf).writerows(grid)
    return buf.getvalue()
