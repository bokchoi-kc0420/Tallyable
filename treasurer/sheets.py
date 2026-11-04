"""Google Sheets sink: the spreadsheet is the system of record.

Four tabs:
- Transactions: tidy, one row per approved line item. Append-only. A receipt id
  already there is skipped, so clicking Push twice never double-counts.
- Events: tidy, one row per event with its income by source. Upserted on push.
- Balance Sheet: rebuilt from the two tidy tabs on every push, in the club's
  sideways layout (one 3-column block per event).
- Ledger: rebuilt the same way: one row per income source or receipt, with
  running totals.

The tidy tabs are what the tool trusts. The rendered tabs are views: edit the
tidy tabs (or re-push), never the views, because the views are overwritten.

Setup: docs/google_sheets_setup.md. Needs in .env:
    GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json
    TALLYABLE_SHEET_ID=<the long id in the sheet's URL>
"""
from __future__ import annotations

import os
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from .models import Receipt, Status
from .post import TX_FIELDS, transaction_rows

INCOME_SOURCES = ["Zelle", "Venmo", "Cash", "National KSEA funding"]
EVENT_FIELDS = ["event_id", "name", "date", *INCOME_SOURCES]
VIEW_NOTE = "Built by Tallyable from the Transactions and Events tabs. Edits here are overwritten on the next push."

TX, EVENTS, BALANCE, LEDGER = "Transactions", "Events", "Balance Sheet", "Ledger"


@dataclass(frozen=True)
class EventInfo:
    event_id: str
    name: str
    date: date


def D(x) -> Decimal:
    """Sheet cell -> Decimal. Cells come back as int, float or str."""
    return Decimal(str(x).strip() or "0")


def num(x: Decimal) -> float:
    """Decimal -> number for the sheet, so Sheets can sum it."""
    return float(x)


# ---------- tidy rows -> rendered views (pure functions, no network) ----------

def _group(tx: list[dict]) -> "OrderedDict[str, OrderedDict[str, list[dict]]]":
    """event_id -> receipt_id -> line-item rows, in the order they were posted."""
    out: OrderedDict = OrderedDict()
    for row in tx:
        out.setdefault(row["event_id"], OrderedDict()).setdefault(row["receipt_id"], []).append(row)
    return out


def _receipt_lines(items: list[dict]) -> list[list]:
    """Liability rows for one receipt: one per item, then VAT and tip.

    Returned items are listed with no amount (the club rule: list it, exclude the
    cost). The VAT row is whatever is left of the posted amount after items and tip,
    so it already excludes the returned items' share of tax and the block sums exactly.
    """
    first = items[0]
    place = first["place"]
    kept = sum((D(i["amount"]) for i in items if str(i["returned"]).upper() != "TRUE"), Decimal("0"))
    tip = D(first["receipt_tip"])
    vat = D(first["receipt_posted"]) - kept - tip
    lines = []
    for i in items:
        returned = str(i["returned"]).upper() == "TRUE"
        label = f"{i['item']} x{i['unit']}" + (" (returned)" if returned else "")
        lines.append([place, label, "" if returned else num(D(i["amount"]))])
    lines.append([place, "VAT", num(vat)])
    if tip:
        lines.append([place, "TIP", num(tip)])
    return lines


def event_block(event: dict, receipts: "OrderedDict[str, list[dict]]") -> list[list]:
    """One event's 3-column block of the balance sheet."""
    assets = [[src, "", num(D(event.get(src, 0)))] for src in INCOME_SOURCES]
    total_assets = sum((D(event.get(src, 0)) for src in INCOME_SOURCES), Decimal("0"))
    liabilities = [line for items in receipts.values() for line in _receipt_lines(items)]
    total_liabilities = sum((D(items[0]["receipt_posted"]) for items in receipts.values()), Decimal("0"))
    return [
        [f"{event['name']} ({event['date']})", "", ""],
        ["LOCATION", "ITEMS (#)", "AMOUNT"],
        ["ASSETS", "", ""],
        *assets,
        ["TOTAL ASSETS", "", num(total_assets)],
        ["LIABILITIES", "", ""],
        *liabilities,
        ["TOTAL LIABILITIES", "", num(total_liabilities)],
        ["TOTAL BALANCE", "", num(total_assets - total_liabilities)],
    ]


def render_balance_sheet(events: list[dict], tx: list[dict]) -> list[list]:
    """Blocks side by side, one blank column between them, ordered by event date."""
    grouped = _group(tx)
    blocks = [event_block(e, grouped.get(e["event_id"], OrderedDict()))
              for e in sorted(events, key=lambda e: str(e["date"]))]
    height = max((len(b) for b in blocks), default=0)
    grid = [[VIEW_NOTE]]
    for r in range(height):
        row: list = []
        for n, b in enumerate(blocks):
            if n:
                row.append("")
            row.extend(b[r] if r < len(b) else ["", "", ""])
        grid.append(row)
    return grid


LEDGER_HEADER = ["DATE", "DESCRIPTION", "ASSETS", "LIABILITIES", "TOTAL ASSETS", "TOTAL LIABILITIES", "BALANCE"]


def render_ledger(events: list[dict], tx: list[dict]) -> list[list]:
    """One row per income source and per receipt, by date, with running totals.

    Income is dated on the event day; each receipt on its own date. On the same
    day, income comes first.
    """
    names = {e["event_id"]: e["name"] for e in events}
    entries = []  # (date, order, description, income, expense)
    for e in events:
        for src in INCOME_SOURCES:
            amt = D(e.get(src, 0))
            if amt:
                entries.append((str(e["date"]), 0, f"{src}: {e['name']}", amt, Decimal("0")))
    for event_id, receipts in _group(tx).items():
        for rid, items in receipts.items():
            f = items[0]
            entries.append((str(f["date"]), 1, f"{f['place']} ({rid}, paid by {f['payer'] or '?'}): "
                            f"{names.get(event_id, event_id)}", Decimal("0"), D(f["receipt_posted"])))
    entries.sort(key=lambda x: (x[0], x[1]))
    rows, ta, tl = [[VIEW_NOTE], LEDGER_HEADER], Decimal("0"), Decimal("0")
    for d, _, desc, inc, exp in entries:
        ta += inc
        tl += exp
        rows.append([d, desc, num(inc) if inc else "", num(exp) if exp else "", num(ta), num(tl), num(ta - tl)])
    return rows


# ---------- the sink ----------

class GoogleSheetsSink:
    """Works with a gspread Spreadsheet, or anything with the same few methods
    (the tests pass an in-memory fake)."""

    def __init__(self, spreadsheet):
        self.book = spreadsheet

    @classmethod
    def from_env(cls, root: Path) -> "GoogleSheetsSink | None":
        """None if Sheets is not set up, so the app can fall back to CSV."""
        from dotenv import load_dotenv
        load_dotenv(root / ".env")
        key_file, sheet_id = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE"), os.getenv("TALLYABLE_SHEET_ID")
        if not (key_file and sheet_id):
            return None
        import gspread
        path = Path(key_file) if Path(key_file).is_absolute() else root / key_file
        return cls(gspread.service_account(filename=str(path)).open_by_key(sheet_id))

    @property
    def label(self) -> str:
        return "Google Sheets"

    def _tab(self, title: str, header: list[str] | None = None):
        import gspread
        try:
            ws = self.book.worksheet(title)
        except gspread.WorksheetNotFound:
            ws = self.book.add_worksheet(title=title, rows=200, cols=max(26, len(header or [])))
            if header:
                ws.append_rows([header], value_input_option="RAW")
        return ws

    def _records(self, title: str, header: list[str]) -> list[dict]:
        return self._tab(title, header).get_all_records()

    def post(self, receipts: list[Receipt], event: EventInfo, income: dict[str, Decimal]) -> list[str]:
        """Append approved, not-yet-posted receipts; upsert the event; rebuild the views.
        Returns the receipt ids written."""
        tx_ws = self._tab(TX, TX_FIELDS)
        done = {(str(r["event_id"]), str(r["receipt_id"])) for r in tx_ws.get_all_records()}
        todo = [r for r in receipts if r.status is Status.APPROVED and (r.event_id, r.receipt_id) not in done]
        rows = [[_cell(f, row[f]) for f in TX_FIELDS] for r in todo for row in transaction_rows(r)]
        if rows:
            tx_ws.append_rows(rows, value_input_option="RAW")

        self._upsert_event(event, income)
        events = self._records(EVENTS, EVENT_FIELDS)
        tx = tx_ws.get_all_records()
        self._rewrite(BALANCE, render_balance_sheet(events, tx))
        self._rewrite(LEDGER, render_ledger(events, tx))
        return [r.receipt_id for r in todo]

    def _upsert_event(self, event: EventInfo, income: dict[str, Decimal]) -> None:
        ws = self._tab(EVENTS, EVENT_FIELDS)
        row = [event.event_id, event.name, event.date.isoformat(),
               *[num(income.get(s, Decimal("0"))) for s in INCOME_SOURCES]]
        ids = [str(r["event_id"]) for r in ws.get_all_records()]
        if event.event_id in ids:
            n = ids.index(event.event_id) + 2  # +1 header, +1 one-based
            ws.update(values=[row], range_name=f"A{n}", value_input_option="RAW")
        else:
            ws.append_rows([row], value_input_option="RAW")

    def _rewrite(self, title: str, grid: list[list]) -> None:
        ws = self._tab(title)
        ws.clear()
        if grid:
            ws.update(values=grid, range_name="A1", value_input_option="RAW")


MONEY_FIELDS = {"price", "amount", "receipt_tax", "receipt_tip", "receipt_total", "receipt_posted"}


def _cell(field: str, v):
    """Money and quantity go in as numbers so Sheets can sum them; the rest stays text."""
    if field in MONEY_FIELDS:
        return float(v)
    if field == "unit":
        return int(v)
    return v
