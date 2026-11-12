"""The Expense Report tab: one per event, in the club's columns (Prototype B).

Every receipt sits in its own box. Place and date, tax, tip, total and who paid are
per receipt, so they are merged down the receipt's item rows; receipts take turns
on a pale tint so neighbours don't blur. Above: the event and four summary cards.
Below: the grand total, then spending by category and who paid out of pocket.
"""
from __future__ import annotations

from collections import OrderedDict, defaultdict
from datetime import date
from decimal import Decimal

from .models import CENT
from .models import cell_decimal as D
from .views import DARK, INK, MUTED, RED, TINT, TINT2, VIEW_NOTE, View, is_returned, num

HEADER = ["Place", "Category", "Items", "Unit", "Price($)", "VAT (TAX)", "TIP", "Total", "Paid by"]
WIDTHS = [112, 72, 162, 38, 72, 72, 60, 78, 88]  # 754 px: a letter page, portrait
TOP = 8  # rows above the first receipt: note, title, event line, gap, cards (2), gap, header


def expense_tab_title(event: dict, events: list[dict]) -> str:
    """One tab per event. Sheets tab names must be unique (ignoring caps), so a name
    another event already has gets the date, and the event id if the date matches too."""
    name = str(event["name"])
    twins = [e for e in events if str(e["name"]).strip().lower() == name.strip().lower()
             and str(e["event_id"]) != str(event["event_id"])]
    when = date.fromisoformat(str(event["date"])[:10])
    if twins:
        name += f" ({when:%b} {when.day})"
    if any(str(e["date"])[:10] == when.isoformat() for e in twins):
        name += f" {str(event['event_id'])[-4:]}"
    return f"Expense Report: {name}"[:95]


def render_expense_report(event: dict, receipts: OrderedDict[str, list[dict]]) -> View:
    ordered = sorted(receipts.items(), key=lambda kv: (str(kv[1][0]["date"]), kv[0]))
    total = sum((D(items[0]["receipt_posted"]) for _, items in ordered), Decimal("0"))
    people = int(D(event.get("attendees") or 0))
    when = date.fromisoformat(str(event["date"])[:10]).strftime("%m/%d/%Y")
    rows = [[VIEW_NOTE], ["Expense Report"], [f"{event['name']}  ·  {when}"], [],
            ["Participants", "", "Receipts", "", "Total spent", "", "", "Per person", ""],
            [people or "", "", len(ordered), "", num(total), "", "", num(total / people) if people else "", ""],
            [], HEADER]
    view = View(rows, freeze_rows=TOP, widths=WIDTHS, heights={1: 34, 5: 26, TOP - 1: 30})
    by_cat, by_payer = defaultdict(Decimal), defaultdict(Decimal)
    for n, (rid, items) in enumerate(ordered):
        f, top = items[0], len(rows)
        payer = f["payer"] or "No payer"
        own = defaultdict(Decimal)
        for i in items:
            rows.append(["", i["category"], i["item"] + (" (returned)" if is_returned(i) else ""),
                         int(D(i["unit"])), num(D(i["price"])), "", "", "", ""])
            if not is_returned(i):
                own[i["category"]] += D(i["amount"])
        extras = D(f["receipt_tax"]) + D(f["receipt_tip"])
        # Lines that don't add up to the total (approved with a note): the total is what was paid,
        # so all of it goes under the receipt's biggest category.
        if own and abs(sum(D(i["amount"]) for i in items) + extras - D(f["receipt_total"])) > CENT:
            own = {max(own, key=own.get): D(f["receipt_posted"]) - extras}
        for k, v in own.items():
            by_cat[k] += v
        rows[top][0] = f"{f['place']}\n{date.fromisoformat(str(f['date'])[:10]):%m/%d}"
        rows[top][5:9] = [num(D(f["receipt_tax"])), num(D(f["receipt_tip"])), num(D(f["receipt_posted"])),
                          f"{payer}\n{rid}"]
        by_payer[payer] += D(f["receipt_posted"])
        bottom = len(rows)
        if n % 2:
            view.look(top, bottom, 0, 9, fill=TINT)
        view.look(top, bottom, 0, 9, border="grid", valign="middle")
        for k, i in enumerate(items):
            if is_returned(i):
                view.look(top + k, top + k + 1, 1, 5, italic=True, color="9AA0A6", strike=True)
        for c in (0, 5, 6, 7, 8):
            view.look(top, bottom, c, c + 1, merge=bottom - top > 1, wrap=True)
        view.look(top, bottom, 0, 1, bold=True, align="center")
        view.look(top, bottom, 8, 9, align="center", **({"bold": True, "color": RED} if not f["payer"] else {}))
        view.look(top, bottom, 7, 8, bold=True)
        view.look(top, bottom, 0, 9, border="box")
        lines = -(-len(f["place"]) // 15) + 1  # the bold place wraps at about 15 letters, then its date line
        tall = -(-lines * 17 // (bottom - top))
        if tall > 21:  # taller rows, so a long place name (or a one-line receipt) isn't cut off
            view.heights.update(dict.fromkeys(range(top, bottom), tall))
    last = len(rows)
    rows.append(["Total expenses", "", "", "", "", "", "", num(total), ""])
    extras = _breakdowns(rows, by_cat, by_payer)

    view.look(0, 1, 0, 1, italic=True, size=9, color="73787F")
    view.look(1, 2, 0, 9, merge=True, bold=True, size=20, color=INK)
    view.look(2, 3, 0, 9, merge=True, size=11, color=MUTED)
    for c0, c1 in ((0, 2), (2, 4), (4, 7), (7, 9)):  # the four summary cards
        for r in (4, 5):
            view.look(r, r + 1, c0, c1, merge=True, align="center", valign="middle")
        view.look(4, 5, c0, c1, fill=INK, color="FFFFFF", bold=True, size=9)
        view.look(5, 6, c0, c1, fill=TINT, bold=True, size=13, color=INK)
        view.look(4, 6, c0, c1, border="box")
    view.look(5, 6, 4, 9, money="plain")
    view.look(TOP - 1, TOP, 0, 9, fill=DARK, color="FFFFFF", bold=True, align="center", valign="middle", wrap=True)
    view.look(TOP - 1, TOP, 0, 9, border="box")
    view.look(TOP, last + 1, 1, 2, color=MUTED)
    view.look(TOP, last + 1, 3, 4, align="center")
    view.look(TOP, last + 1, 4, 8, money=True)
    view.look(last, last + 1, 0, 7, merge=True, bold=True, align="right")
    view.look(last, last + 1, 0, 9, fill=TINT2, border="box", valign="middle")
    view.look(last, last + 1, 7, 8, bold=True, size=12, color=RED)
    view.heights[last] = 28
    for look in extras:
        view.looks.append(look)
    return view


def _breakdowns(rows: list[list], by_cat: dict, by_payer: dict) -> list[dict]:
    """Spent by category (left) and paid out of pocket (right), side by side under the total."""
    start = len(rows) + 1
    lines = max(len(by_cat), len(by_payer)) + 1
    rows.extend([[]] + [[""] * 9 for _ in range(lines)])
    looks = []
    for c, title, data in ((0, "By category (before tax)", by_cat), (7, "Paid out of pocket", by_payer)):
        rows[start][c] = title
        for k, (name, amount) in enumerate(sorted(data.items()), start=1):
            rows[start + k][c:c + 2] = [name, num(amount)]
        end = start + len(data) + 1
        looks += [{"rows": (start, start + 1), "cols": (c, c + 2), "merge": True, "fill": INK, "color": "FFFFFF",
                   "bold": True, "size": 9},
                  {"rows": (start + 1, end), "cols": (c + 1, c + 2), "money": True},
                  {"rows": (start, end), "cols": (c, c + 2), "border": "grid"},
                  {"rows": (start, end), "cols": (c, c + 2), "border": "box"}]
        if "No payer" in data:
            k = sorted(data).index("No payer") + 1
            looks.append({"rows": (start + k, start + k + 1), "cols": (c, c + 1), "bold": True, "color": RED})
    return looks
