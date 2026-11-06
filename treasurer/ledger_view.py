"""The General Ledger and the Receipts tab.

General Ledger: the club's own ledger format (its "Simple General Ledger" sheet): a big
title for the school year, Starting and Current balance cards, a dark header, tinted
columns, red income, filters, and a TOTAL BALANCE row. It can live in its own Google
Sheet, apart from the event books ("the big boss").

Receipts: one row per receipt with whether its payer has been paid back, so the
treasurer can flip between this, the photos and the expense report while checking.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from .models import cell_decimal as D
from .views import DARK, INK, MID, MUTED, RED, TINT, TINT2, VIEW_NOTE, View, group, income_sources, num

LEDGER_HEADER = ["DATE", "DESCRIPTION", "ASSETS", "LIABILITIES", "TOTAL ASSETS", "TOTAL LIABILITIES", "BALANCE"]
LEDGER_TOP = 5  # title rows and balance cards above the header
RECEIPTS_HEADER = ["Date", "Place", "Receipt", "Event", "Paid by", "Total", "Paid back", "Paid back on"]


def _us_date(d) -> str:
    return date.fromisoformat(str(d)[:10]).strftime("%m/%d/%Y")


def school_year(d) -> str:
    """2026-2027 for any date from August 2026 to July 2027."""
    d = date.fromisoformat(str(d)[:10])
    start = d.year if d.month >= 8 else d.year - 1
    return f"{start}-{start + 1}"


def starting_balance(events: list[dict]) -> Decimal:
    """What the club had before this year's first event: typed once per school year in the
    app, so the most recent event that has one carries it."""
    for e in sorted(events, key=lambda e: str(e["date"]), reverse=True):
        if str(e.get("start_balance", "")).strip() != "":
            return D(e["start_balance"])
    return Decimal("0")


def _entries(events: list[dict], tx: list[dict], reimb) -> list[tuple]:
    """(date, order, description, income, expense) by date; on one day, income comes first.
    A payback has no amount: it settles an expense already counted (see reimburse.py)."""
    names = {e["event_id"]: e["name"] for e in events}
    out = []
    for e in events:
        for src in income_sources(e):
            amt = D(e.get(src) or 0)
            if amt:
                out.append((str(e["date"]), 0, f"{src}: {e['name']}", amt, Decimal("0")))
    for event_id, receipts in group(tx).items():
        for rid, items in receipts.items():
            f = items[0]
            out.append((str(f["date"]), 1, f"{f['place']} (paid by {f['payer'] or 'no payer'}, {rid}): "
                        f"{names.get(event_id, event_id)}", Decimal("0"), D(f["receipt_posted"])))
    for r in reimb:
        out.append((str(r["date"]), 2, f"Paid back {r['payer']} ${D(r['amount']):.2f} via {r['method']} "
                    f"(settles expenses above): {names.get(str(r['event_id']), r['event_id'])}",
                    Decimal("0"), Decimal("0")))
    return sorted(out, key=lambda x: (x[0], x[1]))


def render_ledger(events: list[dict], tx: list[dict], reimb: list[dict] = ()) -> View:
    start = starting_balance(events)
    entries = _entries(events, tx, reimb)
    ta = sum((x[3] for x in entries), Decimal("0"))
    tl = sum((x[4] for x in entries), Decimal("0"))
    year = school_year(max((str(e["date"]) for e in events), default=date.today().isoformat()))
    rows = [[f"GENERAL LEDGER {year}", "", "", "", "", "STARTING BALANCE", ""],
            [VIEW_NOTE, "", "", "", "", num(start), ""],
            ["", "", "", "", "", "CURRENT BALANCE", ""],
            ["", "", "", "", "", num(start + ta - tl), ""], [], LEDGER_HEADER]
    run_a = run_l = Decimal("0")
    for d, _, desc, inc, exp in entries:
        run_a, run_l = run_a + inc, run_l + exp
        rows.append([_us_date(d), desc, num(inc) if inc else "", num(exp) if exp else "", num(run_a), num(run_l),
                     num(start + run_a - run_l)])
    last = len(rows)
    rows.append(["TOTAL BALANCE", "", "", "", num(ta), num(tl), num(start + ta - tl)])

    view = View(rows, freeze_rows=LEDGER_TOP + 1, widths=[84, 300, 80, 84, 92, 96, 92],
                heights={0: 40, LEDGER_TOP: 32, last: 26}, filter=(LEDGER_TOP, last, 0, 7))
    view.look(0, 1, 0, 5, merge=True, bold=True, size=20, color=MID, valign="middle")
    view.look(1, 2, 0, 5, merge=True, italic=True, size=8, color=MUTED)
    for r in (0, 2):  # the two balance cards
        view.look(r, r + 1, 5, 7, merge=True, fill=INK, color="FFFFFF", bold=True, size=9, align="center",
                  valign="middle")
        view.look(r + 1, r + 2, 5, 7, merge=True, fill=TINT, bold=True, size=12, align="center", money="plain")
        view.look(r, r + 2, 5, 7, border="box")
    for c in range(7):  # the club's header: dark slate, the asset columns a shade lighter
        view.look(LEDGER_TOP, LEDGER_TOP + 1, c, c + 1, fill=MID if c in (2, 4) else DARK)
        view.look(LEDGER_TOP + 1, last, c, c + 1, fill=TINT2 if c in (2, 4) else TINT)
    view.look(LEDGER_TOP, LEDGER_TOP + 1, 0, 7, color="FFFFFF", bold=True, size=9, valign="middle", wrap=True)
    view.look(LEDGER_TOP + 1, last, 0, 7, border="grid", valign="middle")
    view.look(LEDGER_TOP + 1, last, 1, 2, wrap=True)  # long descriptions wrap instead of hiding
    view.look(LEDGER_TOP + 1, last, 2, 7, money=True)
    view.look(LEDGER_TOP + 1, last, 2, 3, color=RED)
    view.look(LEDGER_TOP + 1, last, 6, 7, bold=True)
    for r in range(LEDGER_TOP + 1, last):
        if rows[r][6] < 0:
            view.look(r, r + 1, 6, 7, color=RED)
        if "paid by no payer" in rows[r][1]:
            view.look(r, r + 1, 1, 2, color=RED)
    view.look(last, last + 1, 0, 4, merge=True, fill=MID, color="FFFFFF", bold=True, align="right", valign="middle")
    view.look(last, last + 1, 4, 7, fill=INK, color="FFFFFF", bold=True, money="plain", valign="middle")
    view.look(LEDGER_TOP, last + 1, 0, 7, border="box")
    return view


def paid_back(tx: list[dict], reimb) -> dict[tuple[str, str], Decimal]:
    """(event_id, receipt_id) -> how much of that receipt its payer has been paid back.
    Paybacks are per payer and event, so they settle that payer's receipts oldest first."""
    pot: dict[tuple, Decimal] = defaultdict(Decimal)
    for r in reimb:
        pot[(str(r["event_id"]), str(r["payer"]))] += D(r["amount"])
    out = {}
    for event_id, receipts in group(tx).items():
        for rid, items in sorted(receipts.items(), key=lambda kv: (str(kv[1][0]["date"]), kv[0])):
            key = (str(event_id), str(items[0]["payer"]))
            share = min(pot[key], D(items[0]["receipt_posted"]))
            pot[key] -= share
            out[(str(event_id), rid)] = share
    return out


def _payback_dates(reimb) -> dict[tuple, str]:
    last = {}
    for r in sorted(reimb, key=lambda r: str(r["date"])):
        last[(str(r["event_id"]), str(r["payer"]))] = _us_date(r["date"])
    return last


def render_receipts(events: list[dict], tx: list[dict], reimb: list[dict] = ()) -> View:
    """One row per receipt, newest event first, with its paid-back status."""
    names = {str(e["event_id"]): e["name"] for e in events}
    got, when = paid_back(tx, reimb), _payback_dates(reimb)
    rows = [[VIEW_NOTE], ["Receipts"], RECEIPTS_HEADER]
    status = []
    for event_id, receipts in group(tx).items():
        for rid, items in sorted(receipts.items(), key=lambda kv: (str(kv[1][0]["date"]), kv[0])):
            f = items[0]
            total, back = D(f["receipt_posted"]), got[(str(event_id), rid)]
            label = "No payer" if not f["payer"] else ("Yes" if back >= total else ("Part" if back else "Not yet"))
            on = when.get((str(event_id), str(f["payer"])), "") if back else ""
            rows.append([_us_date(f["date"]), f["place"], rid, names.get(str(event_id), str(event_id)),
                         f["payer"] or "No payer", num(total), label + (f" (${back:,.2f})" if label == "Part" else ""), on])
            status.append(label)
    last = len(rows)
    view = View(rows, freeze_rows=3, widths=[80, 130, 60, 160, 96, 80, 80, 92], heights={1: 34, 2: 26},
                filter=(2, last, 0, 8))
    view.look(0, 1, 0, 1, italic=True, size=9, color="73787F")
    view.look(1, 2, 0, 8, merge=True, bold=True, size=20, color=INK, valign="middle")
    view.look(2, 3, 0, 8, fill=DARK, color="FFFFFF", bold=True, valign="middle")
    for r, label in enumerate(status, start=3):
        if r % 2 == 0:
            view.look(r, r + 1, 0, 8, fill=TINT)
        colour = {"Yes": "1E7B4F", "No payer": RED, "Not yet": RED, "Part": "B26A00"}[label]
        view.look(r, r + 1, 6, 7, bold=True, color=colour)
    view.look(3, last, 5, 6, money=True)
    view.look(2, last, 0, 8, border="grid")
    view.look(2, last, 0, 8, border="box")
    return view
