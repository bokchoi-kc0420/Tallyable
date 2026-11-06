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
from .views import (
    BALANCE,
    BASE_EVENT_FIELDS,
    View,
    expense_tab_title,
    group,
    num,
    render_balance_sheet,
    render_expense_report,
    render_ledger,
    term_tabs,
)

# Where an event's money comes from. Each club sets its own list in the app; these are
# only the defaults. On the Events tab every column that isn't a base field is a source,
# so a new source simply becomes a new column.
DEFAULT_SOURCES = ["Zelle", "Venmo", "Cash", "Grants and funding"]
EVENT_FIELDS = ["event_id", "name", "date", *DEFAULT_SOURCES, "attendees"]  # header for a new sheet
TX, EVENTS, LEDGER, REIMB = "Transactions", "Events", "Ledger", "Reimbursements"


@dataclass(frozen=True)
class EventInfo:
    event_id: str
    name: str
    date: date
    attendees: int | None = None
    calendar: str = "semester"  # "semester" or "quarter": how balance-sheet tabs are split


def event_row(event: EventInfo, income: dict[str, Decimal]) -> dict:
    """An Events-tab row: the event's fields plus one column per income source."""
    return {"event_id": event.event_id, "name": event.name, "date": event.date.isoformat(),
            "attendees": event.attendees or "", **{s: num(v) for s, v in income.items()}}


# ---------- the sink ----------

class GoogleSheetsSink:
    """Works with a gspread Spreadsheet, or anything with the same few methods
    (the tests pass an in-memory fake)."""

    def __init__(self, spreadsheet):
        self.book = spreadsheet
        self._pending: dict[str, list[dict]] = {}  # formatting requests, sent in one go by _apply_format

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
        for title, grid in term_tabs(events, tx, event.calendar).items():
            self._rewrite(title, grid)
        ev = next(e for e in events if str(e["event_id"]) == event.event_id)
        self._rewrite(expense_tab_title(ev), render_expense_report(ev, group(tx).get(event.event_id, OrderedDict())))
        reimb_ws = self._tab(REIMB, REIMB_FIELDS)
        reimb = reimb_ws.get_all_records()
        self._rewrite(LEDGER, render_ledger(events, tx, reimb))
        self._tidy_format(tx_ws, TX_FIELDS, len(tx) + 1)
        ev_ws = self._tab(EVENTS, EVENT_FIELDS)
        ev_header = [h for h in ev_ws.row_values(1) if h]
        self._tidy_format(ev_ws, ev_header, len(events) + 1, money=set(ev_header) - set(BASE_EVENT_FIELDS))
        self._tidy_format(reimb_ws, REIMB_FIELDS, len(reimb) + 1)
        self._apply_format()
        return [r.receipt_id for r in todo]

    def reimbursements(self) -> list[dict]:
        return self._records(REIMB, REIMB_FIELDS)

    def record_reimbursement(self, r) -> None:
        """Append to the Reimbursements tab and rebuild the Ledger view."""
        row = r.row()
        ws = self._tab(REIMB, REIMB_FIELDS)
        ws.append_rows([[float(row[f]) if f == "amount" else row[f] for f in REIMB_FIELDS]], value_input_option="RAW")
        reimb = ws.get_all_records()
        self._rewrite(LEDGER, render_ledger(self._records(EVENTS, EVENT_FIELDS), self._records(TX, TX_FIELDS), reimb))
        self._tidy_format(ws, REIMB_FIELDS, len(reimb) + 1)
        self._apply_format()

    def _upsert_event(self, event: EventInfo, income: dict[str, Decimal]) -> None:
        ws = self._tab(EVENTS, EVENT_FIELDS)
        header = [h for h in ws.row_values(1) if h] or list(EVENT_FIELDS)
        new = [s for s in income if s not in header]
        if new:  # a source this sheet hasn't seen: add it as a column
            header += new
            ws.update(values=[header], range_name="A1", value_input_option="RAW")
        values = event_row(event, income)
        row = [values.get(h, "" if h in BASE_EVENT_FIELDS else 0.0) for h in header]
        ids = [str(r["event_id"]) for r in ws.get_all_records()]
        if event.event_id in ids:
            n = ids.index(event.event_id) + 2  # +1 header, +1 one-based
            ws.update(values=[row], range_name=f"A{n}", value_input_option="RAW")
        else:
            ws.append_rows([row], value_input_option="RAW")

    def _rewrite(self, title: str, view: View) -> None:
        ws = self._tab(title)
        ws.clear()
        if view.grid:
            ws.update(values=view.grid, range_name="A1", value_input_option="RAW")
        self._pending.setdefault("views", []).extend(fmt.view_requests(ws.id, view))

    def _tidy_format(self, ws, header: list[str], rows: int, money: set[str] = frozenset()) -> None:
        self._pending.setdefault("tidy", []).extend(fmt.tidy_requests(ws.id, header, rows, money))

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
                reimb: list[dict] = ()) -> dict[str, View]:
    """Balance Sheet, Ledger and Expense Report for one event, built from the app's
    approved receipts, exactly as the Sheets sink would draw them. For downloads when
    Sheets isn't set up, and for the online demo."""
    ev = event_row(event, income)
    tx = local_transactions(receipts)
    mine = [x for x in reimb if str(x["event_id"]) == event.event_id]
    return {
        BALANCE: render_balance_sheet([ev], tx),
        LEDGER: render_ledger([ev], tx, mine),
        "Expense Report": render_expense_report(ev, group(tx).get(event.event_id, OrderedDict())),
    }


def local_transactions(receipts: list[Receipt]) -> list[dict]:
    """Transactions-tab rows for the app's approved receipts."""
    return [{f: _cell(f, row[f]) for f in TX_FIELDS} for r in receipts
            if r.counts for row in transaction_rows(r)]
