"""The report tabs, drawn in the club's own sheet format. Pure functions: tidy rows in,
a View out. No network, so the Sheets sink, the Excel download and the tests all draw
exactly the same thing.

A View is the grid of values plus its look: fills, fonts, borders, merges and money
format, as plain ranges. sheet_format.py turns the look into Google Sheets requests,
xlsx_export.py into Excel styles. Colors follow the club's sheets:
- Balance Sheet: one label column, then a 4-column block per event (LOCATION, ITEMS (#),
  the event as the amount column, totals). Block headers alternate tan and gray.
- Ledger: dark header band, striped rows, income in red, accounting dollars.
- Expense Report: big title, light-blue labels and header, one receipt per merged block,
  total in bold red.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .models import cell_decimal as D

VIEW_NOTE = "Built by Tallyable from the Transactions, Events and Reimbursements tabs. Edits here are overwritten on the next push."
BASE_EVENT_FIELDS = ["event_id", "name", "date", "attendees"]
BALANCE = "Balance Sheet"
LEDGER_HEADER = ["DATE", "DESCRIPTION", "ASSETS", "LIABILITIES", "TOTAL ASSETS", "TOTAL LIABILITIES", "BALANCE"]
EXPENSE_HEADER = ["Place", "Category", "Items", "Unit", "Price($)", "VAT (TAX)", "TIP", "Total expenditure", "Notes"]

# The club's colors.
TAN, GRAY, BEIGE, STRIPE = "C9A57D", "BDBDBD", "FBF2E8", "F3F3F3"
SLATE, SLATE_STRIPE, BLUE, RED, NOTE_GRAY, LINE = "3D4451", "E8ECF4", "CFE2F3", "D93025", "73787F", "B7B7B7"


@dataclass
class View:
    """A report tab: values plus how they look. A look is a dict with `rows` and `cols`
    (half-open, zero-based) and any of: fill, color (hex), bold, italic, size, align,
    money, border ("grid" or "topbottom"), merge."""
    grid: list[list]
    looks: list[dict] = field(default_factory=list)
    freeze_rows: int = 1
    freeze_cols: int = 0

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
    """Liability rows for one receipt: one per item, then VAT and tip. The place is
    written on the receipt's first row only, as the club does.

    Returned items are listed with no amount (the club rule: list it, exclude the
    cost). The VAT row is whatever is left of the posted amount after items and tip,
    so it already excludes the returned items' share of tax and the block sums exactly.
    """
    first = items[0]
    kept = sum((D(i["amount"]) for i in items if not is_returned(i)), Decimal("0"))
    tip = D(first["receipt_tip"])
    vat = D(first["receipt_posted"]) - kept - tip
    lines = [["", _item_label(i), "" if is_returned(i) else num(D(i["amount"]))] for i in items]
    lines.append(["", "VAT", num(vat)])
    if tip:
        lines.append(["", "TIP", num(tip)])
    lines[0][0] = first["place"]
    return lines


def render_balance_sheet(events: list[dict], tx: list[dict]) -> View:
    """Label column A, then one 4-column block per event, ordered by event date."""
    grouped = group(tx)
    blocks = []
    for e in sorted(events, key=lambda e: str(e["date"])):
        receipts = grouped.get(e["event_id"], OrderedDict())
        sources = income_sources(e)
        assets = [[src, "", num(D(e.get(src) or 0))] for src in sources]
        total_in = sum((D(e.get(src) or 0) for src in sources), Decimal("0"))
        liabilities = [line for items in receipts.values() for line in _receipt_lines(items)]
        total_out = sum((D(items[0]["receipt_posted"]) for items in receipts.values()), Decimal("0"))
        blocks.append((f"{e['name']} ({e['date']})", assets, liabilities, total_in, total_out))
    n_in = max((len(b[1]) for b in blocks), default=0)
    n_out = max((len(b[2]) for b in blocks), default=0)

    labels = (["", "ASSETS", *[""] * n_in, "TOTAL ASSETS", "LIABILITIES", *[""] * n_out,
               "TOTAL LIABILITIES", "TOTAL BALANCE"])
    grid = [[VIEW_NOTE], *[[label] for label in labels]]
    total_rows = {r for r, label in enumerate(grid) if str(label[0]).startswith("TOTAL")}
    t_in, t_out, t_bal = sorted(total_rows)
    for title, assets, liabilities, total_in, total_out in blocks:
        body = {1: ["LOCATION", "ITEMS (#)", title, ""], t_in: ["", "", "", num(total_in)],
                t_out: ["", "", "", num(total_out)], t_bal: ["", "", "", num(total_in - total_out)]}
        body |= {3 + n: [*line, ""] for n, line in enumerate(assets)}
        body |= {t_in + 2 + n: [*line, ""] for n, line in enumerate(liabilities)}
        for r, row in enumerate(grid):
            row.extend(body.get(r, ["", "", "", ""]) if r else [])

    view = View(grid, freeze_rows=2, freeze_cols=1)
    _note(view)
    width, last = 1 + 4 * len(blocks), len(grid)
    for r in range(3, last, 2):
        view.look(r, r + 1, 0, width, fill=STRIPE)
    for k in range(len(blocks)):
        c = 1 + 4 * k
        tan = k % 2 == 0  # tan and gray blocks take turns, as on the club's sheet
        if tan:
            view.look(2, last, c, c + 4, fill=BEIGE)
        view.look(1, 2, c, c + 4, fill=TAN if tan else GRAY, bold=True)
        view.look(2, last, c + 2, c + 4, money=True)
    view.look(1, 2, 0, 1, fill=GRAY)
    for r in (2, t_in + 1):  # ASSETS, LIABILITIES
        view.look(r, r + 1, 0, 1, bold=True, italic=True)
    for r in total_rows:
        view.look(r, r + 1, 0, width, bold=True, italic=True, border="topbottom")
    return view


# ---------- Ledger ----------

def _us_date(d) -> str:
    return date.fromisoformat(str(d)[:10]).strftime("%m/%d/%Y")


def render_ledger(events: list[dict], tx: list[dict], reimb: list[dict] = ()) -> View:
    """One row per income source, receipt and reimbursement, by date, with running totals.

    Income is dated on the event day; each receipt on its own date. On the same
    day, income comes first. A reimbursement row has no asset or liability amount:
    it settles an expense that is already counted (see reimburse.py).
    """
    names = {e["event_id"]: e["name"] for e in events}
    entries = []  # (date, order, description, income, expense)
    for e in events:
        for src in income_sources(e):
            amt = D(e.get(src) or 0)
            if amt:
                entries.append((str(e["date"]), 0, f"{src}: {e['name']}", amt, Decimal("0")))
    for event_id, receipts in group(tx).items():
        for rid, items in receipts.items():
            f = items[0]
            entries.append((str(f["date"]), 1, f"{f['place']} ({rid}, paid by {f['payer'] or '?'}): "
                            f"{names.get(event_id, event_id)}", Decimal("0"), D(f["receipt_posted"])))
    for r in reimb:
        entries.append((str(r["date"]), 2, f"Paid back {r['payer']} ${D(r['amount']):.2f} via {r['method']} "
                        f"(settles expenses above): {names.get(str(r['event_id']), r['event_id'])}",
                        Decimal("0"), Decimal("0")))
    entries.sort(key=lambda x: (x[0], x[1]))
    rows, ta, tl = [[VIEW_NOTE], LEDGER_HEADER], Decimal("0"), Decimal("0")
    for d, _, desc, inc, exp in entries:
        ta += inc
        tl += exp
        rows.append([_us_date(d), desc, num(inc) if inc else "", num(exp) if exp else "", num(ta), num(tl),
                     num(ta - tl)])

    view = View(rows, freeze_rows=2)
    _note(view)
    width, last = len(LEDGER_HEADER), len(rows)
    view.look(1, 2, 0, width, fill=SLATE, color="FFFFFF", bold=True)
    for r in range(2, last, 2):
        view.look(r, r + 1, 0, width, fill=SLATE_STRIPE)
    view.look(2, last, 2, 3, color=RED)
    view.look(2, last, 2, width, money=True)
    view.look(1, last, 0, width, border="grid")
    return view


# ---------- Expense Report ----------

def expense_tab_title(event: dict) -> str:
    return f"Expense Report: {event['name']}"[:95]


def render_expense_report(event: dict, receipts: OrderedDict[str, list[dict]]) -> View:
    """The club's per-event expense report. Tax, tip, total and payer are per receipt, so
    they sit in cells merged down the receipt's item rows, like the club's sheet.
    Notes holds the payer (as the club's sheet does) plus the receipt id."""
    rows = [[VIEW_NOTE], ["Expense Report"],
            ["Event title", event["name"], "", "", "", "", "date", _us_date(event["date"]), ""],
            ["Participants", event.get("attendees", "") or "", "", "", "", "", "location", "", ""],
            EXPENSE_HEADER]
    view = View(rows, freeze_rows=5)
    total = Decimal("0")
    for rid, items in receipts.items():
        f, top = items[0], len(rows)
        for n, i in enumerate(items):
            first = n == 0
            rows.append([f["place"] if first else "", i["category"], _item_label(i, False), int(D(i["unit"])),
                         num(D(i["price"])), num(D(f["receipt_tax"])) if first else "",
                         num(D(f["receipt_tip"])) if first else "", num(D(f["receipt_posted"])) if first else "",
                         f"{f['payer'] or 'no payer'} ({rid})" if first else ""])
        if len(items) > 1:
            for c in (0, 5, 6, 7, 8):
                view.look(top, len(rows), c, c + 1, merge=True)
        total += D(f["receipt_posted"])
    rows.append(["Total expenses", "", "", "", "", "", "", num(total), ""])

    _note(view)
    last = len(rows)
    view.look(1, 2, 0, 9, merge=True, bold=True, size=20)
    for r in (2, 3):
        view.look(r, r + 1, 1, 6, merge=True, align="center")
        view.look(r, r + 1, 7, 9, merge=True, align="center")
        for c in (0, 6):
            view.look(r, r + 1, c, c + 1, fill=BLUE, bold=True, align="center")
    view.look(4, 5, 0, 9, fill=BLUE, bold=True, align="center")
    view.look(5, last - 1, 0, 1, align="center")
    view.look(5, last - 1, 8, 9, align="center")
    view.look(5, last, 4, 8, money=True)
    view.look(last - 1, last, 0, 9, fill=BLUE)
    view.look(last - 1, last, 0, 1, bold=True, align="center")
    view.look(last - 1, last, 7, 8, bold=True, size=14, color=RED)
    view.look(2, last, 0, 9, border="grid")
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
