"""The report tabs, drawn in the club's own sheet format. Pure functions: tidy rows in,
a View out. No network, so the Sheets sink, the Excel download and the tests all draw
exactly the same thing.

A View is the grid of values plus its look: fills, fonts, borders, merges and money
format, as plain ranges. sheet_format.py turns the look into Google Sheets requests,
xlsx_export.py into Excel styles. Colors follow the club's sheets:
- Balance Sheet: one label column, then a 4-column block per event (LOCATION, ITEMS (#),
  the event as the amount column, totals). Block headers alternate tan and gray.
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

# The club's colors: tan and gray balance-sheet blocks, the ledger's dark slate header
# and pale blue/gray tinted columns, red for income and for what needs a look.
TAN, GRAY, BEIGE, STRIPE = "C9A57D", "BDBDBD", "FBF2E8", "F3F3F3"
SLATE, SLATE_STRIPE, BLUE, RED, NOTE_GRAY, LINE = "3D4451", "E8ECF4", "CFE2F3", "D93025", "73787F", "B7B7B7"
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


def _item_label(i: dict, with_count: bool = True) -> str:
    """"pizza (2)" as the club's balance sheet writes it; a single item has no count.
    The expense report has its own Unit column, so it leaves the count out."""
    unit = int(D(i["unit"]))
    count = f" ({unit})" if with_count and unit != 1 else ""
    return f"{i['item']}{count}" + (" (returned)" if is_returned(i) else "")


def _note(view: View) -> None:
    view.look(0, 1, 0, 1, italic=True, size=9, color=NOTE_GRAY)


# ---------- Balance Sheet ----------

def _receipt_lines(items: list[dict]) -> list[list]:
    """Liability rows for one receipt: one per item, then VAT and tip, the receipt's total
    on its last row. The place goes on the first row and the date and payer under it.

    Returned items are listed with no amount (the club rule: list it, exclude the
    cost). The VAT row is whatever is left of the posted amount after items and tip,
    so it already excludes the returned items' share of tax and the block sums exactly.
    """
    first = items[0]
    kept = sum((D(i["amount"]) for i in items if not is_returned(i)), Decimal("0"))
    tip = D(first["receipt_tip"])
    vat = D(first["receipt_posted"]) - kept - tip
    lines = [["", _item_label(i), "" if is_returned(i) else num(D(i["amount"])), ""] for i in items]
    lines.append(["", "VAT", num(vat), ""])
    if tip:
        lines.append(["", "TIP", num(tip), ""])
    lines[0][0] = first["place"]
    lines[1][0] = f"{date.fromisoformat(str(first['date'])[:10]).strftime('%m/%d')} · {first['payer'] or 'no payer'}"
    lines[-1][3] = num(D(first["receipt_posted"]))
    return lines


def render_balance_sheet(events: list[dict], tx: list[dict]) -> View:
    """Label column A, then one 4-column block per event, ordered by event date: the
    event's name on a band, then LOCATION, ITEMS (#), AMOUNT, TOTAL. Every receipt is
    boxed. Prints landscape once there are two events side by side."""
    grouped = group(tx)
    blocks = []
    for e in sorted(events, key=lambda e: str(e["date"])):
        receipts = grouped.get(e["event_id"], OrderedDict())
        sources = income_sources(e)
        assets = [[src, "", num(D(e.get(src) or 0)), ""] for src in sources]
        total_in = sum((D(e.get(src) or 0) for src in sources), Decimal("0"))
        by_date = sorted(receipts.values(), key=lambda items: (str(items[0]["date"]), items[0]["receipt_id"]))
        per_receipt = [_receipt_lines(items) for items in by_date]  # same order as the Expense Report
        total_out = sum((D(items[0]["receipt_posted"]) for items in receipts.values()), Decimal("0"))
        blocks.append((f"{e['name']} ({e['date']})", assets, per_receipt, total_in, total_out))
    n_in = max((len(b[1]) for b in blocks), default=0)
    n_out = max((sum(len(r) for r in b[2]) for b in blocks), default=0)

    labels = (["", "", "ASSETS", *[""] * n_in, "TOTAL ASSETS", "LIABILITIES", *[""] * n_out,
               "TOTAL LIABILITIES", "TOTAL BALANCE"])
    grid = [[VIEW_NOTE], *[[label] for label in labels]]
    total_rows = sorted(r for r, label in enumerate(grid) if str(label[0]).startswith("TOTAL"))
    t_in, t_out, t_bal = total_rows
    view = View(grid, freeze_rows=3, freeze_cols=1, landscape=len(blocks) > 1,
                widths=[118, *[120, 190, 84, 84] * len(blocks)], heights={1: 28})
    last = len(grid)
    for k, (title, assets, per_receipt, total_in, total_out) in enumerate(blocks):
        c, tan = 1 + 4 * k, k % 2 == 0  # tan and gray blocks take turns, as on the club's sheet
        liabilities = [line for lines in per_receipt for line in lines]
        body = {1: [title, "", "", ""], 2: ["LOCATION", "ITEMS (#)", "AMOUNT", "TOTAL"],
                t_in: ["", "", "", num(total_in)], t_out: ["", "", "", num(total_out)],
                t_bal: ["", "", "", num(total_in - total_out)]}
        body |= {4 + n: line for n, line in enumerate(assets)}
        body |= {t_in + 2 + n: line for n, line in enumerate(liabilities)}
        for r, row in enumerate(grid):
            row.extend(body.get(r, ["", "", "", ""]) if r else [])
        view.look(3, last, c, c + 4, fill=BEIGE if tan else "F7F7F7")
        view.look(1, 2, c, c + 4, merge=True, fill=TAN if tan else GRAY, bold=True, size=11, align="center",
                  valign="middle", color=INK)
        view.look(2, 3, c, c + 4, fill=TAN if tan else GRAY, bold=True, size=9, color=INK)
        view.look(2, 3, c + 2, c + 4, align="center")
        view.look(3, last, c + 2, c + 4, money=True)
        view.look(4, 4 + len(assets), c, c + 4, border="grid")
        view.look(t_bal, t_bal + 1, c + 3, c + 4, color=RED if total_in < total_out else "1E7B4F")
        top = t_in + 2
        for lines in per_receipt:  # each receipt in its own box
            view.look(top, top + len(lines), c, c + 1, bold=True)
            view.look(top + 1, top + 2, c, c + 1, bold=False, size=8, color=MUTED if "no payer" not in lines[1][0] else RED)
            view.look(top, top + len(lines), c + 3, c + 4, bold=True)
            view.look(top, top + len(lines), c, c + 4, border="box")
            top += len(lines)
        for r, row in enumerate(liabilities, start=t_in + 2):
            if row[1] in ("VAT", "TIP"):
                view.look(r, r + 1, c + 1, c + 2, color=MUTED)
            if str(row[1]).endswith("(returned)"):
                view.look(r, r + 1, c + 1, c + 2, italic=True, color="9AA0A6")
        view.look(1, last, c, c + 4, border="box")
    width = 1 + 4 * len(blocks)
    _note(view)
    view.look(1, 3, 0, 1, fill=GRAY)
    for r in (3, t_in + 1):  # ASSETS, LIABILITIES
        view.look(r, r + 1, 0, 1, bold=True, italic=True, color=INK)
    for r in total_rows:
        view.look(r, r + 1, 0, width, fill="E4E8EE", bold=True, italic=True, border="topbottom")
    view.look(1, last, 0, 1, border="box")
    return view


# ---------- one balance sheet per school term ----------

QUARTERS = {9: "Fall", 10: "Fall", 11: "Fall", 12: "Fall", 1: "Winter", 2: "Winter", 3: "Winter",
            4: "Spring", 5: "Spring", 6: "Spring", 7: "Summer", 8: "Summer"}
SEMESTERS = {8: "Fall", 9: "Fall", 10: "Fall", 11: "Fall", 12: "Fall", 1: "Spring", 2: "Spring", 3: "Spring",
             4: "Spring", 5: "Spring", 6: "Summer", 7: "Summer"}
CALENDARS = {"semester": SEMESTERS, "quarter": QUARTERS}


def academic_term(d: str | date, calendar: str = "semester") -> str:
    """The school term a date falls in. Semesters: Fall (Aug-Dec), Spring (Jan-May), Summer
    (Jun-Jul). Quarters: Fall (Sep-Dec), Winter (Jan-Mar), Spring (Apr-Jun), Summer (Jul-Aug).
    The club starts a new balance sheet each term."""
    d = date.fromisoformat(str(d)[:10])
    return f"{CALENDARS.get(calendar, SEMESTERS)[d.month]} {d.year}"


def term_tabs(events: list[dict], tx: list[dict], calendar: str = "semester") -> dict[str, View]:
    """One balance sheet per school term, holding that term's events."""
    by_term: dict[str, list[dict]] = OrderedDict()
    for e in sorted(events, key=lambda e: str(e["date"])):
        by_term.setdefault(academic_term(e["date"], calendar), []).append(e)
    out = {}
    for term, evs in by_term.items():
        ids = {str(e["event_id"]) for e in evs}
        out[f"{BALANCE}: {term}"] = render_balance_sheet(evs, [r for r in tx if str(r["event_id"]) in ids])
    return out


def grid_to_csv(grid: list[list]) -> str:
    import csv
    import io
    buf = io.StringIO()
    csv.writer(buf).writerows(grid)
    return buf.getvalue()
