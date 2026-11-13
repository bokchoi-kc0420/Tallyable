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

import json
import os
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from . import sheet_format as fmt
from .expense_view import expense_tab_title, render_expense_report
from .ledger_view import render_ledger, render_receipts
from .models import Receipt, Status
from .post import TX_FIELDS, transaction_rows
from .reimburse import REIMB_FIELDS
from .views import (
    BALANCE,
    BASE_EVENT_FIELDS,
    View,
    group,
    num,
    render_balance_sheet,
)

# Where an event's money comes from. Each club sets its own list in the app; these are
# only the defaults. On the Events tab every column that isn't a base field is a source,
# so a new source simply becomes a new column.
DEFAULT_SOURCES = ["Cash"]  # a new event starts with Cash only; the treasurer adds the rest
EVENT_FIELDS = list(BASE_EVENT_FIELDS)  # header for a new sheet; each income source adds its own column
TX, EVENTS, LEDGER, REIMB, RECEIPTS = "Transactions", "Events", "General Ledger", "Reimbursements", "Receipts"


@dataclass(frozen=True)
class EventInfo:
    event_id: str
    name: str
    date: date
    attendees: int | None = None
    start_balance: Decimal | None = None  # what the club had at the start of the school year


def event_row(event: EventInfo, income: dict[str, Decimal]) -> dict:
    """An Events-tab row: the event's fields plus one column per income source."""
    return {"event_id": event.event_id, "name": event.name, "date": event.date.isoformat(),
            "attendees": event.attendees or "",
            "start_balance": "" if event.start_balance is None else num(event.start_balance),
            **{s: num(v) for s, v in income.items()}}


# ---------- the sink ----------

def bot_client(root: Path, key_info: dict | None = None):
    """A gspread client signed in as Tallyable's bot, or None when no key is set up."""
    import gspread
    from gspread.http_client import BackOffHTTPClient  # waits and retries when Google rate-limits us
    if key_info:
        return gspread.service_account_from_dict(dict(key_info), http_client=BackOffHTTPClient)
    key_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    if not key_file:
        return None
    path = Path(key_file) if Path(key_file).is_absolute() else root / key_file
    return gspread.service_account(filename=str(path), http_client=BackOffHTTPClient)


def bot_email(root: Path, key_info: dict | None = None) -> str | None:
    """The address a treasurer shares their sheet with."""
    from dotenv import load_dotenv
    load_dotenv(root / ".env")
    if key_info:
        return key_info.get("client_email")
    key_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    path = key_file and (Path(key_file) if Path(key_file).is_absolute() else root / key_file)
    try:
        return json.loads(path.read_text())["client_email"] if path else None
    except (OSError, ValueError, KeyError):
        return None


def sheet_id(link: str) -> str | None:
    """The id in a Google Sheets link (or an id pasted on its own); None if it isn't one."""
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]{20,})", link) or re.fullmatch(r"\s*([A-Za-z0-9_-]{20,})\s*", link)
    return m.group(1) if m else None


class GoogleSheetsSink:
    """Works with a gspread Spreadsheet, or anything with the same few methods
    (the tests pass an in-memory fake)."""

    def __init__(self, spreadsheet, ledger_book=None):
        self.book = spreadsheet
        self.ledger_book = ledger_book or spreadsheet  # the General Ledger can live in its own file
        self._pending: list[tuple] = []  # (book, tab title, formatting requests), sent by _apply_format
        self.format_errors: list[str] = []  # tabs whose formatting Sheets refused on the last push

    @classmethod
    def from_env(cls, root: Path, key_info: dict | None = None, linked: dict | None = None) -> GoogleSheetsSink | None:
        """None if Sheets is not set up, so the app can fall back to CSV.

        The sheets are the ones the treasurer linked in the app (`linked`: {"book": id,
        "ledger": id}), else the ids in .env. Locally the bot's key is a file named in .env;
        on Streamlit Cloud the app passes its contents from st.secrets as `key_info`."""
        from dotenv import load_dotenv
        load_dotenv(root / ".env")
        linked = linked or {}
        if linked.get("book"):  # a linked book never mixes with .env: no ledger link = ledger in the same book
            sheet_id, ledger_id = linked["book"], linked.get("ledger")
        else:
            sheet_id, ledger_id = os.getenv("TALLYABLE_SHEET_ID"), os.getenv("TALLYABLE_LEDGER_SHEET_ID")
        if not sheet_id:
            return None
        client = bot_client(root, key_info)
        if not client:
            return None
        return cls(client.open_by_key(sheet_id), client.open_by_key(ledger_id) if ledger_id else None)

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
        A receipt reopened after a push is no longer "posted": its old rows are taken out first,
        so a fixed receipt replaces the wrong one (and one left out leaves the books).
        Returns the receipt ids written."""
        tx_ws = self._tab(TX, TX_FIELDS)
        reopened = {(r.event_id, r.receipt_id) for r in receipts if r.status is not Status.POSTED}
        rows_now = [(str(r["event_id"]), str(r["receipt_id"])) for r in tx_ws.get_all_records()]
        for n in reversed([n for n, key in enumerate(rows_now) if key in reopened]):
            tx_ws.delete_rows(n + 2)  # +1 for the header, +1 because sheet rows count from 1
        done = set(rows_now) - reopened
        todo = [r for r in receipts if r.status is Status.APPROVED and (r.event_id, r.receipt_id) not in done]
        rows = [[_cell(f, row[f]) for f in TX_FIELDS] for r in todo for row in transaction_rows(r)]
        if rows:
            tx_ws.append_rows(rows, value_input_option="RAW")

        self._upsert_event(event, income)
        events = self._records(EVENTS, EVENT_FIELDS)
        tx = tx_ws.get_all_records()
        self._rewrite(BALANCE, render_balance_sheet(events, tx))
        for ws in self.book.worksheets():  # per-term tabs from older versions: one Balance Sheet holds it all
            if ws.title.startswith(f"{BALANCE}: "):
                self.book.del_worksheet(ws)
        ev = next(e for e in events if str(e["event_id"]) == event.event_id)
        self._rewrite(expense_tab_title(ev, events), render_expense_report(ev, group(tx).get(event.event_id, OrderedDict())))
        reimb_ws = self._tab(REIMB, REIMB_FIELDS)
        reimb = reimb_ws.get_all_records()
        self._rewrite(RECEIPTS, render_receipts(events, tx, reimb))
        self._rewrite(LEDGER, render_ledger(events, tx), self.ledger_book)
        self._tidy_format(tx_ws, TX_FIELDS, len(tx) + 1)
        ev_ws = self._tab(EVENTS, EVENT_FIELDS)
        ev_header = [h for h in ev_ws.row_values(1) if h]
        self._tidy_format(ev_ws, ev_header, len(events) + 1, money=set(ev_header) - set(BASE_EVENT_FIELDS))
        self._tidy_format(reimb_ws, REIMB_FIELDS, len(reimb) + 1)
        for book in {id(b): b for b in (self.book, self.ledger_book)}.values():
            _drop_blank_sheet1(book)  # once per push, not per tab or per payback: each check is a trip to Google
        self._apply_format()
        return [r.receipt_id for r in todo]

    def reimbursements(self) -> list[dict]:
        return self._records(REIMB, REIMB_FIELDS)

    def record_reimbursements(self, paybacks: list) -> None:
        """Append to the Reimbursements tab, and nothing else: redrawing the Receipts tab on every payback
        cost ~15 trips to Google, and a few paybacks in a minute hit its limit (a 40 second freeze).
        refresh_receipts catches the tab up when the event is finished; a push redraws it too."""
        rows = [r.row() for r in paybacks]
        ws = self._tab(REIMB, REIMB_FIELDS)
        ws.append_rows([[float(row[f]) if f == "amount" else row[f] for f in REIMB_FIELDS] for row in rows],
                       value_input_option="RAW")

    def undo_reimbursement(self, event_id: str) -> None:
        """Delete this event's most recent payback (a misclicked Mark paid)."""
        ws = self._tab(REIMB, REIMB_FIELDS)
        rows = ws.get_all_records()
        last = max((i for i, r in enumerate(rows) if str(r["event_id"]) == event_id), default=None)
        if last is None:
            return
        ws.delete_rows(last + 2)  # +1 for the header, +1 because sheet rows count from 1

    def refresh_receipts(self) -> None:
        """Redraw the Receipts tab so its Paid back column shows the paybacks. The ledger has no row
        for a payback: it settles an expense already counted there."""
        tabs = {w.title: w for w in self.book.worksheets()}  # one lookup for all three tabs: each is a trip to Google
        reimb, events, tx = (tabs[t].get_all_records() if t in tabs else [] for t in (REIMB, EVENTS, TX))
        self._rewrite(RECEIPTS, render_receipts(events, tx, reimb))
        if REIMB in tabs:
            self._tidy_format(tabs[REIMB], REIMB_FIELDS, len(reimb) + 1)
        self._apply_format()

    def _upsert_event(self, event: EventInfo, income: dict[str, Decimal]) -> None:
        ws = self._tab(EVENTS, EVENT_FIELDS)
        header = [h for h in ws.row_values(1) if h] or list(EVENT_FIELDS)
        values = event_row(event, income)
        new = [k for k in values if k not in header]
        if new:  # a source (or a field from a newer Tallyable) this sheet hasn't seen: add a column
            header += new
            ws.update(values=[header], range_name="A1", value_input_option="RAW")
        row = [values.get(h, "" if h in BASE_EVENT_FIELDS else 0.0) for h in header]
        ids = [str(r["event_id"]) for r in ws.get_all_records()]
        if event.event_id in ids:
            n = ids.index(event.event_id) + 2  # +1 header, +1 one-based
            ws.update(values=[row], range_name=f"A{n}", value_input_option="RAW")
        else:
            ws.append_rows([row], value_input_option="RAW")

    def _rewrite(self, title: str, view: View, book=None) -> None:
        """Draw a report tab from scratch. The old tab is deleted rather than cleared, so
        nothing left on it (a freeze line, a Sheets table, banding, merges, colors a
        treasurer or 'Convert to table' added) can clash with the new look. The new tab is
        added before the old one goes, because a spreadsheet can't lose its last tab."""
        import gspread
        book = book or self.book
        try:
            old = book.worksheet(title)
        except gspread.WorksheetNotFound:
            old = None
        cols = max((len(r) for r in view.grid), default=1)
        ws = book.add_worksheet(title=f"{title} (new)" if old else title, rows=len(view.grid) + 5, cols=cols)
        if old:
            book.del_worksheet(old)
            ws.update_title(title)
        if view.grid:
            ws.update(values=view.grid, range_name="A1", value_input_option="RAW")
        self._pending.append((book, title, fmt.view_requests(ws.id, view)))



    def _tidy_format(self, ws, header: list[str], rows: int, money: set[str] = frozenset()) -> None:
        self._pending.append((self.book, ws.title, fmt.tidy_requests(ws.id, header, rows, money)))

    def _apply_format(self) -> None:
        """One batch per tab: Sheets rejects a whole batch over one bad request, so one tab
        can't leave every other tab unformatted. Formatting is cosmetic: a failure is
        reported, never fatal. Then each book's tab order, with the data tabs hidden."""
        for book in {id(b): b for b, _, _ in self._pending}.values():
            tabs = [(ws.id, ws.title) for ws in book.worksheets()]
            self._pending.append((book, "tab order", fmt.order_requests(tabs, {TX, EVENTS, REIMB})))
        self.format_errors = []
        for book, title, requests in self._pending:
            try:
                book.batch_update({"requests": requests})
            except Exception as e:
                self.format_errors.append(f"{title}: {e}")
        self._pending = []


def _drop_blank_sheet1(book) -> None:
    """A new Google Sheet comes with an empty "Sheet1"; once Tallyable has drawn a tab, it goes."""
    tabs = book.worksheets()
    for ws in tabs:
        if ws.title == "Sheet1" and len(tabs) > 1 and not ws.get_all_values():
            book.del_worksheet(ws)


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
    """Expense Report, Balance Sheet, Receipts and General Ledger for one event, built from the app's
    approved receipts, exactly as the Sheets sink would draw them. For downloads when
    Sheets isn't set up, and for the online demo."""
    ev = event_row(event, income)
    tx = local_transactions(receipts)
    mine = [x for x in reimb if str(x["event_id"]) == event.event_id]
    return {
        "Expense Report": render_expense_report(ev, group(tx).get(event.event_id, OrderedDict())),
        BALANCE: render_balance_sheet([ev], tx),
        RECEIPTS: render_receipts([ev], tx, mine),
        LEDGER: render_ledger([ev], tx),
    }


def local_transactions(receipts: list[Receipt]) -> list[dict]:
    """Transactions-tab rows for the app's approved receipts."""
    return [{f: _cell(f, row[f]) for f in TX_FIELDS} for r in receipts
            if r.counts for row in transaction_rows(r)]
