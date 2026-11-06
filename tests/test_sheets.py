"""GoogleSheetsSink against an in-memory fake spreadsheet. No network."""
from datetime import date
from decimal import Decimal
from pathlib import Path

import gspread
import pytest

from treasurer.loader import load_answer_key
from treasurer.models import Status
from treasurer.sheets import BALANCE, EVENTS, LEDGER, TX, EventInfo, GoogleSheetsSink

KEY = Path(__file__).parent.parent / "fake_event" / "answer_key.csv"
EVENT = EventInfo("EVT-FAKE-01", "Fall Mentor Mixer (FAKE)", date(2026, 11, 14))
INCOME = {"Zelle": Decimal("300.00"), "Venmo": Decimal("250.00"), "Cash": Decimal("40.00"),
          "Grants and funding": Decimal("50.00")}


class FakeWorksheet:
    """Mimics the gspread calls the sink uses, including get_all_records numericising."""

    def __init__(self, title="", sheet_id=0, rows=1000, cols=26):
        self.cells: list[list] = []
        self.title, self.id, self.rows, self.cols = title, sheet_id, rows, cols

    def update_title(self, title):
        self.title = title

    def append_rows(self, rows, value_input_option=None):
        self.cells.extend([list(r) for r in rows])

    def update(self, values, range_name, value_input_option=None):
        start = int(range_name[1:]) - 1
        while len(self.cells) < start + len(values):
            self.cells.append([])
        for n, row in enumerate(values):
            self.cells[start + n] = list(row)

    def clear(self):
        self.cells = []

    def delete_rows(self, n):
        del self.cells[n - 1]

    def row_values(self, n):
        return list(self.cells[n - 1]) if len(self.cells) >= n else []

    def get_all_records(self):
        if not self.cells:
            return []
        head = self.cells[0]
        return [dict(zip(head, [*r, *[""] * (len(head) - len(r))], strict=False)) for r in self.cells[1:]]


class FakeBook:
    """An in-memory spreadsheet. batch_update checks requests the way Google does for the
    mistakes that have bitten us: a merge crossing the freeze line, a range off the tab."""

    def __init__(self):
        self.sheets: list[FakeWorksheet] = []
        self.requests: list[dict] = []

    @property
    def tabs(self) -> dict[str, FakeWorksheet]:
        return {ws.title: ws for ws in self.sheets}

    def worksheets(self):
        return list(self.sheets)

    def batch_update(self, body):
        check_requests(self, body["requests"])
        self.requests.extend(body["requests"])

    def worksheet(self, title):
        if title not in self.tabs:
            raise gspread.WorksheetNotFound(title)
        return self.tabs[title]

    def add_worksheet(self, title, rows, cols):
        self.sheets.append(FakeWorksheet(title, max((w.id for w in self.sheets), default=0) + 1, rows, cols))
        return self.sheets[-1]

    def del_worksheet(self, ws):
        assert len(self.sheets) > 1, "a spreadsheet can't lose its last tab"
        self.sheets.remove(ws)


def check_requests(book, requests):
    by_id = {ws.id: ws for ws in book.tabs.values()}
    merges: dict[int, list] = {}
    for req in requests:
        (kind, body), = req.items()
        rng = body.get("range", {})
        ws = by_id.get(rng.get("sheetId", body.get("properties", {}).get("sheetId")))
        if ws and "endRowIndex" in rng:
            assert rng["endRowIndex"] <= ws.rows and rng["endColumnIndex"] <= ws.cols, f"{kind} off the tab {ws.title}"
            assert rng["endRowIndex"] > rng["startRowIndex"] and rng["endColumnIndex"] > rng["startColumnIndex"]
        if kind == "mergeCells":
            m = (rng["startRowIndex"], rng["endRowIndex"], rng["startColumnIndex"], rng["endColumnIndex"])
            assert (m[1] - m[0]) * (m[3] - m[2]) > 1, "one-cell merge"
            for o in merges.get(ws.id, []):
                assert not (m[0] < o[1] and o[0] < m[1] and m[2] < o[3] and o[2] < m[3]), "overlapping merges"
            merges.setdefault(ws.id, []).append(m)
        grid = body.get("properties", {}).get("gridProperties", {})
        if kind == "updateSheetProperties" and "frozenRowCount" in grid:
            fr, fc = grid["frozenRowCount"], grid["frozenColumnCount"]
            for m in merges.get(ws.id, []):
                assert not m[0] < fr < m[1], f"merge crosses the frozen rows on {ws.title}"
                assert not m[2] < fc < m[3], f"merge crosses the frozen columns on {ws.title}"


@pytest.fixture
def approved():
    """What a correct review approves: all but the R11 duplicate, R06's total fixed."""
    out = []
    for r in load_answer_key(KEY):
        if r.receipt_id == "R11":
            continue
        if r.receipt_id == "R06":
            r = r.model_copy(update={"total": r.computed_total})
        out.append(r.model_copy(update={"status": Status.APPROVED}))
    return out


def col(grid, label, offset=4):
    """A total on a labelled row, in the first event block (label column, then LOCATION,
    ITEMS, amount, total)."""
    for row in grid:
        if row and row[0] == label:
            return Decimal(str(row[offset]))
    raise KeyError(label)


def test_push_writes_tidy_tabs_and_is_idempotent(approved):
    book = FakeBook()
    sink = GoogleSheetsSink(book)
    written = sink.post(approved, EVENT, INCOME)
    assert len(written) == len(approved)
    n_rows = len(book.tabs[TX].cells)
    assert n_rows == 1 + sum(len(r.items) for r in approved)
    assert sink.post(approved, EVENT, INCOME) == []          # second click writes nothing
    assert len(book.tabs[TX].cells) == n_rows
    assert len(book.tabs[EVENTS].cells) == 2                  # event upserted, not duplicated


def test_balance_sheet_matches_expected_total(approved):
    book = FakeBook()
    GoogleSheetsSink(book).post(approved, EVENT, INCOME)
    grid = book.tabs[BALANCE].cells
    assert grid[1][1:4] == ["LOCATION", "ITEMS (#)", "Fall Mentor Mixer (FAKE) (2026-11-14)"]
    assert col(grid, "TOTAL ASSETS") == Decimal("640.00")
    assert col(grid, "TOTAL LIABILITIES") == Decimal("571.75")  # the week-1 expected total
    assert col(grid, "TOTAL BALANCE") == Decimal("68.25")
    # The liability lines alone add up to the total, so returned items' cost and tax are excluded.
    start = next(i for i, r in enumerate(grid) if r[0] == "LIABILITIES") + 1
    end = next(i for i, r in enumerate(grid) if r[0] == "TOTAL LIABILITIES")
    lines = sum(Decimal(str(r[3])) for r in grid[start:end] if r[3] != "")
    assert lines.quantize(Decimal("0.01")) == Decimal("571.75")
    assert any("(returned)" in str(r[2]) and r[3] == "" for r in grid[start:end])


def test_second_event_goes_sideways_and_ledger_runs(approved):
    book = FakeBook()
    sink = GoogleSheetsSink(book)
    sink.post(approved[:2], EVENT, INCOME)
    later = EventInfo("EVT-FAKE-02", "Winter Social (FAKE)", date(2026, 12, 5))
    other = approved[2].model_copy(update={"event_id": "EVT-FAKE-02", "date": date(2026, 12, 4)})
    sink.post([other], later, {"Cash": Decimal("20.00")})
    grid = book.tabs[BALANCE].cells
    assert grid[1][7] == "Winter Social (FAKE) (2026-12-05)"  # block 2 is the next 4 columns

    ledger = book.tabs[LEDGER].cells
    assert ledger[1][0] == "DATE"
    body = ledger[2:]
    assert [r[0] for r in body] == sorted(r[0] for r in body)
    total_in = sum(INCOME.values()) + Decimal("20.00")
    total_out = sum(r.posted_amount for r in approved[:3])
    assert Decimal(str(body[-1][4])) == total_in
    assert Decimal(str(body[-1][6])).quantize(Decimal("0.01")) == total_in - total_out


def test_from_env_returns_none_without_setup(tmp_path):
    assert GoogleSheetsSink.from_env(tmp_path) is None


def test_reimbursement_lands_in_ledger_without_moving_balance(approved):
    from treasurer.reimburse import Reimbursement, totals_by_payer
    book = FakeBook()
    sink = GoogleSheetsSink(book)
    sink.post(approved, EVENT, INCOME)
    before = book.tabs[LEDGER].cells[-1][6]
    sink.record_reimbursement(Reimbursement(EVENT.event_id, "Member A", date(2026, 11, 20), Decimal("31.07"), "Zelle"))
    last = book.tabs[LEDGER].cells[-1]
    assert last[1].startswith("Paid back Member A $31.07 via Zelle") and last[2] == last[3] == ""
    assert last[6] == before                                   # balance unchanged
    assert totals_by_payer(sink.reimbursements(), EVENT.event_id) == {"Member A": Decimal("31.07")}
    sink.undo_reimbursement(EVENT.event_id)                    # a misclicked Mark paid
    assert sink.reimbursements() == []
    assert not any("Paid back" in str(c) for row in book.tabs[LEDGER].cells for c in row)


def test_expense_report_tab_in_club_format(approved):
    from treasurer.expense_view import HEADER, TOP
    book = FakeBook()
    ev = EventInfo(EVENT.event_id, EVENT.name, EVENT.date, attendees=45)
    GoogleSheetsSink(book).post(approved, ev, INCOME)
    grid = book.tabs["Expense Report: Fall Mentor Mixer (FAKE)"].cells
    assert grid[1] == ["Expense Report"] and grid[TOP - 1] == HEADER
    assert grid[5][0] == 45 and grid[5][2] == len(approved) and grid[5][4] == 571.75  # the summary cards
    first = grid[TOP]  # receipts in date order: R15, the print shop, came first
    assert first[0] == "Print Shop\n11/10" and first[8] == "Member D\nR15"
    total = next(r for r in grid if r and r[0] == "Total expenses")
    assert Decimal(str(total[7])) == Decimal("571.75")
    assert any(str(r[2]).endswith("(returned)") for r in grid if len(r) > 2)
    assert any(str(r[8]).startswith("No payer") for r in grid if len(r) > 8)  # R07 has no payer
    flat = [c for r in grid for c in r]
    assert "By category (before tax)" in flat and "Paid out of pocket" in flat


def test_local_views_match_what_sheets_would_draw(approved):
    from treasurer.sheets import local_views
    from treasurer.views import grid_to_csv
    ev = EventInfo(EVENT.event_id, EVENT.name, EVENT.date, attendees=45)
    views = local_views(approved, ev, INCOME)
    book = FakeBook()
    GoogleSheetsSink(book).post(approved, ev, INCOME)
    assert views[BALANCE].grid == book.tabs[BALANCE].cells
    assert views[LEDGER].grid == book.tabs[LEDGER].cells
    assert "571.75" in grid_to_csv(views["Expense Report"].grid)


def test_academic_quarters():
    from treasurer.views import academic_term
    assert academic_term("2026-11-14", "quarter") == "Fall 2026"
    assert academic_term(date(2027, 1, 9), "quarter") == "Winter 2027"
    assert academic_term("2027-04-01", "quarter") == "Spring 2027"
    assert academic_term("2027-07-04", "quarter") == "Summer 2027"


def test_each_quarter_gets_its_own_balance_sheet(approved):
    book = FakeBook()
    sink = GoogleSheetsSink(book)
    sink.post(approved[:2], EVENT, INCOME)
    winter = EventInfo("EVT-FAKE-03", "New Year Social (FAKE)", date(2027, 1, 20), calendar="quarter")
    other = approved[2].model_copy(update={"event_id": "EVT-FAKE-03", "date": date(2027, 1, 19)})
    sink.post([other], winter, {"Cash": Decimal("20.00")})
    fall, win = book.tabs["Balance Sheet: Fall 2026"].cells, book.tabs["Balance Sheet: Winter 2027"].cells
    assert fall[1][3].startswith("Fall Mentor Mixer") and len(fall[1]) == 5
    assert win[1][3].startswith("New Year Social") and len(win[1]) == 5
    assert len(book.tabs[BALANCE].cells[1]) == 9   # the all-events tab still has both, side by side


def test_push_formats_the_sheet_for_reading(approved):
    from treasurer import sheet_format as fmt
    from treasurer import views
    book = FakeBook()
    sink = GoogleSheetsSink(book)
    sink.post(approved[:2], EVENT, INCOME)
    sink.post([approved[2].model_copy(update={"event_id": "E2"})], EventInfo("E2", "Second", date(2026, 11, 20)), {})
    reqs = book.requests
    painted = [r["repeatCell"] for r in reqs if "repeatCell" in r]
    # money in accounting dollars, and the club's colors: tan and gray balance-sheet headers,
    # the ledger's and the expense report's dark header bands
    assert any(p["cell"]["userEnteredFormat"] == fmt.MONEY for p in painted)
    fills = {tuple(p["cell"]["userEnteredFormat"]["backgroundColor"].values()) for p in painted
             if "backgroundColor" in p["cell"]["userEnteredFormat"]}
    for color in (views.TAN, views.GRAY, views.SLATE, views.DARK):
        assert tuple(fmt.rgb(color).values()) in fills
    assert any("mergeCells" in r for r in reqs)  # an expense-report receipt spans its item rows
    # report tabs come first, data tabs last
    order = {r["updateSheetProperties"]["properties"]["sheetId"]: r["updateSheetProperties"]["properties"]["index"]
             for r in reqs if "index" in r.get("updateSheetProperties", {}).get("properties", {})}
    title = {ws.id: t for t, ws in book.tabs.items()}  # tabs are rebuilt each push: only today's ids count
    tabs = [title[sid] for sid, _ in sorted(order.items(), key=lambda x: x[1]) if sid in title]
    assert tabs[0].startswith("Expense Report") and tabs[-3:] == sorted(["Events", "Reimbursements", "Transactions"])
    hidden = {title[r["updateSheetProperties"]["properties"]["sheetId"]] for r in reqs
              if r.get("updateSheetProperties", {}).get("properties", {}).get("hidden")
              and r["updateSheetProperties"]["properties"]["sheetId"] in title}
    assert hidden == {"Events", "Reimbursements", "Transactions"}  # raw data stays out of the way and out of print
    assert any(r.get("updateSheetProperties", {}).get("properties", {}).get("gridProperties", {}).get("hideGridlines")
               for r in reqs)  # the screen shows what prints


def test_a_tab_the_treasurer_reshaped_is_rebuilt_not_patched(approved):
    """Tonight's bug: a freeze at row 6 (from 'Convert to table') made Google refuse the
    expense report's merges. The sink now replaces the tab, so old state can't clash."""
    book = FakeBook()
    sink = GoogleSheetsSink(book)
    sink.post(approved, EVENT, INCOME)
    tab = next(t for t in book.tabs if t.startswith("Expense Report"))
    old = book.tabs[tab]
    sink.post(approved, EVENT, INCOME)
    assert book.tabs[tab] is not old and sink.format_errors == []
    assert not any(t.endswith("(new)") for t in book.tabs)


def test_one_tab_refusing_its_format_does_not_stop_the_others(approved):
    book = FakeBook()
    sent = []

    def refuse_transactions(body):  # say the treasurer made Transactions into a Sheets table
        tx_id = book.tabs["Transactions"].id
        if any(v.get("range", {}).get("sheetId") == tx_id for r in body["requests"] for v in r.values()):
            raise RuntimeError("table headers can't be formatted")
        check_requests(book, body["requests"])
        sent.extend(body["requests"])
    book.batch_update = refuse_transactions
    sink = GoogleSheetsSink(book)
    assert sink.post(approved, EVENT, INCOME)  # receipts still written
    assert [e.split(":")[0] for e in sink.format_errors] == ["Transactions"]  # reported, not hidden
    assert any("mergeCells" in r for r in sent)  # the report tabs still got their look
    merges = [r["mergeCells"]["range"] for r in sent if "mergeCells" in r]
    assert all((m["endRowIndex"] - m["startRowIndex"]) * (m["endColumnIndex"] - m["startColumnIndex"]) > 1
               for m in merges)  # Sheets refuses a one-cell merge (R15 has a single item)


def test_view_formatting_rules():
    from treasurer import sheet_format as fmt
    from treasurer.views import View
    view = View([["note"], ["DATE", "AMOUNT"], ["11/14/2026", 10.0]], freeze_rows=2)
    view.look(1, 2, 0, 2, fill="3D4451", bold=True)
    view.look(2, 3, 1, 2, money=True, color="D93025")
    view.look(1, 3, 0, 2, border="grid")
    reqs = fmt.view_requests(7, view)
    freeze = [r for r in reqs if "gridProperties" in r.get("updateSheetProperties", {}).get("properties", {})]
    assert freeze[0]["updateSheetProperties"]["properties"]["gridProperties"]["frozenRowCount"] == 2
    red = next(r["repeatCell"] for r in reqs if r.get("repeatCell", {}).get("range", {}).get("startRowIndex") == 2)
    assert red["cell"]["userEnteredFormat"]["numberFormat"] == fmt.MONEY["numberFormat"]
    # only the fields a look sets are written, so red text keeps the row's stripe
    assert red["fields"] == "userEnteredFormat.textFormat.foregroundColor,userEnteredFormat.numberFormat"
    assert any("updateBorders" in r for r in reqs)


def test_any_club_can_name_its_own_income_sources(approved):
    book = FakeBook()
    sink = GoogleSheetsSink(book)
    sink.post(approved, EVENT, {"Ticket sales": Decimal("120.00"), "Sponsor": Decimal("80.00")})
    header = book.tabs["Events"].cells[0]
    assert "Ticket sales" in header and "Sponsor" in header
    flat = [c for row in book.tabs["Balance Sheet"].cells for c in row]
    assert "Ticket sales" in flat and 200.0 in flat  # TOTAL ASSETS
    ledger = [row[1] for row in book.tabs["Ledger"].cells[2:]]
    assert any(d.startswith("Ticket sales:") for d in ledger)


def test_whole_book_exports_to_one_formatted_excel_file(approved):
    from io import BytesIO

    from openpyxl import load_workbook

    from treasurer.post import TX_FIELDS
    from treasurer.sheets import local_transactions, local_views
    from treasurer.xlsx_export import MONEY, book_xlsx
    data = book_xlsx(local_views(approved, EVENT, INCOME), local_transactions(approved), TX_FIELDS)
    wb = load_workbook(BytesIO(data))
    assert wb.sheetnames == ["Balance Sheet", "Ledger", "Expense Report", "Transactions"]
    bs = wb["Balance Sheet"]
    total = next(r for r in bs.iter_rows() if r[0].value == "TOTAL LIABILITIES")
    assert total[0].font.bold and total[4].number_format == MONEY
    assert bs.freeze_panes == "B3"  # the note, the headers and the label column stay visible
    tx = wb["Transactions"]
    assert tx.max_row == 1 + sum(len(r.items) for r in approved)


def test_formatted_currency_cells_read_back_as_numbers():
    from treasurer.views import D
    assert D("$1,200.50") == Decimal("1200.50")
    assert D("-$5.00") == D("($5.00)") == Decimal("-5.00")
    assert D("") == Decimal("0")
    assert D(500) == Decimal("500")
    with pytest.raises(ValueError, match="isn't a number"):
        D("abc")


def test_semester_schools_get_semester_tabs():
    from treasurer.views import academic_term
    assert academic_term("2026-08-28") == "Fall 2026"
    assert academic_term("2027-03-01") == "Spring 2027"
    assert academic_term("2027-03-01", "quarter") == "Winter 2027"
    assert academic_term("2027-06-15") == "Summer 2027"
