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

from . import sheet_format as fmt
from .models import Receipt, Status
from .post import TX_FIELDS, transaction_rows
from .reimburse import REIMB_FIELDS

INCOME_SOURCES = ["Zelle", "Venmo", "Cash", "National KSEA funding"]
EVENT_FIELDS = ["event_id", "name", "date", *INCOME_SOURCES, "attendees"]
VIEW_NOTE = "Built by Tallyable from the Transactions, Events and Reimbursements tabs. Edits here are overwritten on the next push."

TX, EVENTS, BALANCE, LEDGER, REIMB = "Transactions", "Events", "Balance Sheet", "Ledger", "Reimbursements"


@dataclass(frozen=True)
class EventInfo:
    event_id: str
    name: str
    date: date
    attendees: int | None = None


def D(x) -> Decimal:
    """Sheet cell -> Decimal. Cells come back as int, float or str."""
    return Decimal(str(x).strip() or "0")


def num(x: Decimal) -> float:
    """Decimal -> number for the sheet, so Sheets can sum it."""
    return float(x)


# ---------- tidy rows -> rendered views (pure functions, no network) ----------

def _group(tx: list[dict]) -> OrderedDict[str, OrderedDict[str, list[dict]]]:
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


def event_block(event: dict, receipts: OrderedDict[str, list[dict]]) -> list[list]:
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


EXPENSE_HEADER = ["Place", "Category", "Items", "Unit", "Price($)", "VAT (TAX)", "TIP", "Total expenditure", "Notes"]


def expense_tab_title(event: dict) -> str:
    return f"Expense Report: {event['name']}"[:95]


def render_expense_report(event: dict, receipts: OrderedDict[str, list[dict]]) -> list[list]:
    """The club's per-event expense report. In the paper version tax, tip and total
    are merged cells spanning a receipt's item rows; here they sit on the receipt's
    first row and the rows below are left blank, which reads the same way.
    Notes holds the payer (as the club's sheet does) plus the receipt id and any return."""
    rows = [[VIEW_NOTE], [event["name"]], ["Date", str(event["date"])],
            ["Participants", event.get("attendees", "") or ""], [], EXPENSE_HEADER]
    total = Decimal("0")
    for rid, items in receipts.items():
        f = items[0]
        for n, i in enumerate(items):
            returned = str(i["returned"]).upper() == "TRUE"
            note = f"{f['payer'] or 'no payer'} ({rid})" if n == 0 else ""
            if returned:
                note = (note + "; " if note else "") + "returned, cost excluded"
            first = n == 0
            rows.append([f["place"] if first else "", i["category"], i["item"], i["unit"], num(D(i["price"])),
                         num(D(f["receipt_tax"])) if first else "", num(D(f["receipt_tip"])) if first else "",
                         num(D(f["receipt_posted"])) if first else "", note])
        total += D(f["receipt_posted"])
    rows += [[], ["", "", "", "", "", "", "TOTAL", num(total), ""]]
    return rows


def academic_quarter(d: str | date) -> str:
    """UC Davis runs on quarters: Fall (Sep-Dec), Winter (Jan-Mar), Spring (Apr-Jun),
    Summer (Jul-Aug). The club starts a new balance sheet each quarter."""
    d = date.fromisoformat(str(d)[:10])
    name = {9: "Fall", 10: "Fall", 11: "Fall", 12: "Fall", 1: "Winter", 2: "Winter", 3: "Winter",
            4: "Spring", 5: "Spring", 6: "Spring", 7: "Summer", 8: "Summer"}[d.month]
    return f"{name} {d.year}"


def quarter_tabs(events: list[dict], tx: list[dict]) -> dict[str, list[list]]:
    """One balance sheet per academic quarter, holding that quarter's events."""
    by_q: dict[str, list[dict]] = OrderedDict()
    for e in sorted(events, key=lambda e: str(e["date"])):
        by_q.setdefault(academic_quarter(e["date"]), []).append(e)
    out = {}
    for q, evs in by_q.items():
        ids = {str(e["event_id"]) for e in evs}
        out[f"{BALANCE}: {q}"] = render_balance_sheet(evs, [r for r in tx if str(r["event_id"]) in ids])
    return out


LEDGER_HEADER = ["DATE", "DESCRIPTION", "ASSETS", "LIABILITIES", "TOTAL ASSETS", "TOTAL LIABILITIES", "BALANCE"]


def render_ledger(events: list[dict], tx: list[dict], reimb: list[dict] = ()) -> list[list]:
    """One row per income source, receipt and reimbursement, by date, with running totals.

    Income is dated on the event day; each receipt on its own date. On the same
    day, income comes first. A reimbursement row has no asset or liability amount:
    it settles an expense that is already counted (see reimburse.py).
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
    for r in reimb:
        entries.append((str(r["date"]), 2, f"Paid back {r['payer']} ${D(r['amount']):.2f} via {r['method']} "
                        f"(settles expenses above): {names.get(str(r['event_id']), r['event_id'])}",
                        Decimal("0"), Decimal("0")))
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
    def from_env(cls, root: Path, key_info: dict | None = None) -> GoogleSheetsSink | None:
        """None if Sheets is not set up, so the app can fall back to CSV.

        Locally the key is a file named in .env. On Streamlit Cloud there is no file,
        so the app passes the key's contents from st.secrets as `key_info`."""
        from dotenv import load_dotenv
        load_dotenv(root / ".env")
        key_file, sheet_id = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE"), os.getenv("TALLYABLE_SHEET_ID")
        if not sheet_id or not (key_file or key_info):
            return None
        import gspread
        from gspread.http_client import BackOffHTTPClient  # waits and retries when Google rate-limits us
        if key_info:
            client = gspread.service_account_from_dict(dict(key_info), http_client=BackOffHTTPClient)
        else:
            path = Path(key_file) if Path(key_file).is_absolute() else root / key_file
            client = gspread.service_account(filename=str(path), http_client=BackOffHTTPClient)
        return cls(client.open_by_key(sheet_id))

    @property
    def label(self) -> str:
        return "Google Sheets"

    @property
    def url(self) -> str | None:
        return getattr(self.book, "url", None)

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
        for title, grid in quarter_tabs(events, tx).items():
            self._rewrite(title, grid)
        ev = next(e for e in events if str(e["event_id"]) == event.event_id)
        self._rewrite(expense_tab_title(ev), render_expense_report(ev, _group(tx).get(event.event_id, OrderedDict())))
        self._rewrite(LEDGER, render_ledger(events, tx, self.reimbursements()))
        self._tidy_format(tx_ws, TX_FIELDS, len(tx) + 1)
        self._tidy_format(self._tab(EVENTS, EVENT_FIELDS), EVENT_FIELDS, len(events) + 1)
        self._tidy_format(self._tab(REIMB, REIMB_FIELDS), REIMB_FIELDS, len(self.reimbursements()) + 1)
        self._apply_format()
        return [r.receipt_id for r in todo]

    def reimbursements(self) -> list[dict]:
        return self._records(REIMB, REIMB_FIELDS)

    def record_reimbursement(self, r) -> None:
        """Append to the Reimbursements tab and rebuild the Ledger view."""
        row = r.row()
        self._tab(REIMB, REIMB_FIELDS).append_rows(
            [[float(row[f]) if f == "amount" else row[f] for f in REIMB_FIELDS]], value_input_option="RAW")
        self._rewrite(LEDGER, render_ledger(self._records(EVENTS, EVENT_FIELDS),
                                            self._records(TX, TX_FIELDS), self.reimbursements()))
        self._tidy_format(self._tab(REIMB, REIMB_FIELDS), REIMB_FIELDS, len(self.reimbursements()) + 1)
        self._apply_format()

    def _upsert_event(self, event: EventInfo, income: dict[str, Decimal]) -> None:
        ws = self._tab(EVENTS, EVENT_FIELDS)
        row = [event.event_id, event.name, event.date.isoformat(),
               *[num(income.get(s, Decimal("0"))) for s in INCOME_SOURCES], event.attendees or ""]
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
        self._pending.setdefault("views", []).extend(fmt.view_requests(ws.id, grid))

    def _tidy_format(self, ws, header: list[str], rows: int) -> None:
        self._pending.setdefault("tidy", []).extend(fmt.tidy_requests(ws.id, header, rows))

    @property
    def _pending(self) -> dict[str, list[dict]]:
        if not hasattr(self, "_fmt"):
            self._fmt: dict[str, list[dict]] = {}
        return self._fmt

    def _apply_format(self) -> None:
        """Send the formatting in two batches, so a tab the treasurer turned into a
        Sheets table (which can refuse header formatting) doesn't stop the views
        from being formatted. Formatting is cosmetic: a failure never fails a push."""
        tabs = [(ws.id, ws.title) for ws in self.book.worksheets()]
        batches = [self._pending.pop("views", []) + fmt.order_requests(tabs, {TX, EVENTS, REIMB}),
                   self._pending.pop("tidy", [])]
        for requests in batches:
            if requests:
                try:
                    self.book.batch_update({"requests": requests})
                except Exception:  # cosmetic only
                    pass


MONEY_FIELDS = {"price", "amount", "receipt_tax", "receipt_tip", "receipt_total", "receipt_posted"}


def _cell(field: str, v):
    """Money and quantity go in as numbers so Sheets can sum them; the rest stays text."""
    if field in MONEY_FIELDS:
        return float(v)
    if field == "unit":
        return int(v)
    return v


# ---------- the same views without Google Sheets ----------

def local_views(receipts: list[Receipt], event: EventInfo, income: dict[str, Decimal],
                reimb: list[dict] = ()) -> dict[str, list[list]]:
    """Balance Sheet, Ledger and Expense Report for one event, built from the app's
    approved receipts, exactly as the Sheets sink would draw them. For downloads when
    Sheets isn't set up, and for the online demo."""
    ev = {"event_id": event.event_id, "name": event.name, "date": event.date.isoformat(),
          **{s: num(income.get(s, Decimal("0"))) for s in INCOME_SOURCES}, "attendees": event.attendees or ""}
    tx = [{f: _cell(f, row[f]) for f in TX_FIELDS} for r in receipts
          if r.status in (Status.APPROVED, Status.POSTED) for row in transaction_rows(r)]
    mine = [x for x in reimb if str(x["event_id"]) == event.event_id]
    return {
        BALANCE: render_balance_sheet([ev], tx),
        LEDGER: render_ledger([ev], tx, mine),
        "Expense Report": render_expense_report(ev, _group(tx).get(event.event_id, OrderedDict())),
    }


def grid_to_csv(grid: list[list]) -> str:
    import csv
    import io
    buf = io.StringIO()
    csv.writer(buf).writerows(grid)
    return buf.getvalue()
