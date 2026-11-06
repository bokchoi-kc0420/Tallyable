"""Headless run of the Streamlit app: draft the fake event, approve, fix a math error."""
import csv
import os
from pathlib import Path

from streamlit.testing.v1 import AppTest

from treasurer.models import Status

APP = str(Path(__file__).parent.parent / "app.py")
MEMBERS = "Member A, Member B, Member C, Member D"


def new_app(members: str = MEMBERS) -> AppTest:
    """The app with the club's members already added, as a treasurer would on Upload."""
    from ui.sidebar import DEFAULT_EVENT
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["event"] = {**DEFAULT_EVENT, "members": members, "set_up": True}
    return at


def owed_table(at) -> list[dict]:
    """Rows of the Payback details table, read back from its HTML."""
    import re
    page = next(m.value for m in at.markdown if "<th" in m.value and ">Owed<" in m.value)
    heads = re.findall(r"<th(?: [^>]*)?>(.*?)</th>", page)
    rows = re.findall(r"<tr>(.*?)</tr>", page.split("<tbody>")[1])
    return [dict(zip(heads, re.findall(r"<td(?: [^>]*)?>(.*?)</td>", r), strict=True)) for r in rows]


def test_draft_approve_and_fix():
    at = new_app().run()
    at.button[0].click().run()  # use the fake event's receipts
    for sb in at.selectbox:
        if sb.key and sb.key.startswith("payer-R"):
            sb.set_value("Member A")
    at.run()
    next(b for b in at.button if b.label == "Draft rows").click().run()
    assert "R15" in at.session_state["receipts"]  # ids follow file names

    at.sidebar.radio[0].set_value("2. Review").run()
    assert not at.exception
    next(b for b in at.button if b.label == "Approve").click().run()
    assert at.session_state["receipts"]["R01"].status.value == "approved"

    at.sidebar.radio(key="review-pick").set_value("R06").run()
    assert any("off by" in m.value for m in at.markdown)
    at.text_input(key="total-R06").set_value("110.26").run()
    assert not any("off by" in m.value for m in at.markdown)


def test_push_logs_time_and_close_out_shows_owed_and_report():
    at = new_app().run()
    at.button[0].click().run()
    for sb in at.selectbox:
        if sb.key and sb.key.startswith("payer-R"):
            sb.set_value("Member A")
    at.run()
    next(b for b in at.button if b.label == "Draft rows").click().run()
    at.sidebar.radio[0].set_value("2. Review").run()
    next(b for b in at.button if b.label == "Approve").click().run()  # R01

    at.sidebar.radio[0].set_value("3. Summary").run()
    at.text_input(key="income-Cash").set_value("100.00").run()
    push = next(b for b in at.button if b.label.startswith("Push to"))
    assert push.disabled  # other receipts still drafted
    for rid, r in list(at.session_state["receipts"].items()):
        if rid != "R01":
            at.session_state["receipts"][rid] = r.model_copy(update={"status": Status.REJECTED})
    at.run()
    next(b for b in at.button if b.label.startswith("Push to")).click().run()
    assert not at.exception
    assert at.session_state["receipts"]["R01"].status is Status.POSTED
    assert {"Balance Sheet", "General Ledger", "Expense Report", "Receipts"} <= {b.label for b in at.get("download_button")}
    log = Path(os.environ["TALLYABLE_OUTPUT_DIR"]) / "run_log.csv"
    row = list(csv.DictReader(log.open()))[-1]
    assert row["posted"] == "1" and row["minutes_review_to_push"] != ""

    at.sidebar.radio[0].set_value("4. Close out").run()
    assert not at.exception
    owed = owed_table(at)
    assert [r["Payer"] for r in owed] == ["Member A"] and owed[0]["Owed"] == "$31.07"
    at.selectbox(key="funder").set_value("Example: event grant (up to $2,500)").run()
    assert any(b.label.startswith("Download funder report") for b in at.get("download_button"))


def test_one_click_mark_paid_uses_chosen_method():
    at = new_app().run()
    at.button[0].click().run()
    for sb in at.selectbox:
        if sb.key and sb.key.startswith("payer-R"):
            sb.set_value("Member C")
    at.run()
    next(b for b in at.button if b.label == "Draft rows").click().run()
    r = at.session_state["receipts"]["R01"]
    at.session_state["receipts"]["R01"] = r.model_copy(update={"status": Status.APPROVED})
    at.sidebar.radio[0].set_value("4. Close out").run()
    at.selectbox(key="quick-method").set_value("Venmo").run()
    at.button(key="paid-Member C").click().run()
    assert not at.exception
    assert owed_table(at)[0]["Owed"] == "$0.00"
    rows = list(csv.DictReader(open(Path(os.environ["TALLYABLE_OUTPUT_DIR"]) / "reimbursements.csv")))
    assert rows[-1]["method"] == "Venmo" and rows[-1]["payer"] == "Member C"
    assert not [b for b in at.button if b.key == "paid-Member C"]  # now shows Paid instead
    at.button(key="undo-paid").click().run()  # a misclick can be taken back
    assert owed_table(at)[0]["Owed"] != "$0.00"
    assert not list(csv.DictReader(open(Path(os.environ["TALLYABLE_OUTPUT_DIR"]) / "reimbursements.csv")))


def test_mark_paid_back_updates_owed():
    at = new_app().run()
    at.button[0].click().run()
    for sb in at.selectbox:
        if sb.key and sb.key.startswith("payer-R"):
            sb.set_value("Member B")
    at.run()
    next(b for b in at.button if b.label == "Draft rows").click().run()
    r = at.session_state["receipts"]["R01"]
    at.session_state["receipts"]["R01"] = r.model_copy(update={"status": Status.APPROVED, "payer": "Member B"})
    at.sidebar.radio[0].set_value("4. Close out").run()
    form_amount = next(t for t in at.text_input if t.label == "Amount")
    form_amount.set_value("99.00")
    next(b for b in at.button if b.label == "Mark paid back").click().run()
    assert any("overpay" in e.value for e in at.error)       # more than owed is blocked
    form_amount = next(t for t in at.text_input if t.label == "Amount")
    form_amount.set_value("")
    next(b for b in at.button if b.label == "Mark paid back").click().run()
    assert not at.exception
    assert owed_table(at)[0]["Owed"] == "$0.00"


def test_password_gate(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "fake-test-pw")
    at = new_app().run()
    assert at.text_input[0].label == "Password" and not at.sidebar.radio
    at.text_input[0].set_value("nope").run()
    assert any("Wrong password" in e.value for e in at.error)
    at.text_input[0].set_value("fake-test-pw").run()
    assert at.sidebar.radio[0].value == "1. Upload"


def test_unreadable_file_can_be_entered_by_hand():
    at = new_app().run()
    at.session_state["failed"] = {"R16.jpg": (None, "R16.jpg won't open as an image.")}
    at.run()
    assert any("won't open" in e.value for e in at.error)
    labels = {}
    for t in at.text_input:  # first form on the page is the one for R16
        labels.setdefault(t.label, t)
    labels["Place"].set_value("Corner Store")
    labels["Item"].set_value("Ice")
    labels["Price per unit"].set_value("3.00")
    labels["Total"].set_value("3.00")
    next(b for b in at.button if b.label == "Add").click().run()
    assert not at.exception
    r = at.session_state["receipts"]["R16"]
    assert r.place == "Corner Store" and r.image_file == "R16.jpg"
    assert "R16.jpg" not in at.session_state["failed"]


def test_event_setup_and_start_new_event():
    at = new_app("Treasurer").run()
    name = next(t for t in at.sidebar.text_input if t.label == "Event name")
    name.set_value("Winter Social (FAKE)").run()
    assert at.session_state["event"]["event_id"].startswith("EVT-2026-11-14-WINTER")
    at.button[0].click().run()
    next(b for b in at.button if b.label == "Draft rows").click().run()
    at.run()
    assert next(t for t in at.sidebar.text_input if t.label == "Event name").disabled
    assert all(r.event_id.startswith("EVT-2026-11-14-WINTER") for r in at.session_state["receipts"].values())
    at.sidebar.button(key="new-event").click().run()
    assert at.session_state["receipts"]  # nothing cleared until the treasurer confirms
    at.button(key="confirm-new-no").click().run()
    assert at.session_state["receipts"]
    at.sidebar.button(key="new-event").click().run()
    at.button(key="confirm-new-yes").click().run()
    assert at.session_state["receipts"] == {}
    assert at.header[0].value == "Start a new event"  # who's in carries over, ready to confirm
    assert at.session_state["event"]["members"] == "Treasurer"


def test_an_event_set_up_but_not_drafted_survives_a_new_event():
    at = new_app().run()
    at.session_state["event"] = {**at.session_state["event"], "name": "Bake Sale (FAKE)", "event_id": "EVT-BAKE"}
    at.run()
    at.sidebar.button(key="new-event").click().run()
    at.button(key="confirm-new-yes").click().run()
    assert any("Bake Sale" in m.value for m in at.sidebar.markdown)  # under Past events, not wiped


def test_a_new_tab_reopens_the_saved_session_on_the_same_step():
    at = new_app().run()
    next(b for b in at.button if b.label.startswith("Use the fake event")).click().run()
    for sb in at.selectbox:
        if sb.key and sb.key.startswith("payer-R"):
            sb.set_value("Member A")
    at.run()
    next(b for b in at.button if b.label == "Draft rows").click().run()
    at.sidebar.radio[0].set_value("2. Review").run()
    next(b for b in at.button if b.label == "Approve").click().run()

    fresh = AppTest.from_file(APP, default_timeout=30).run()  # a new browser tab, e.g. back from the home page
    assert fresh.sidebar.radio[0].value == "2. Review"
    assert fresh.session_state["receipts"]["R01"].status.value == "approved"
    assert fresh.session_state["images"]["R01"][1] == "image/jpeg"


def test_corrupt_session_file_is_ignored():
    out = Path(os.environ["TALLYABLE_OUTPUT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    (out / "session.json").write_text("{not json")
    at = new_app().run()
    assert not at.exception
    assert at.session_state["receipts"] == {}


def drafted_app(payer="Member A"):
    at = new_app().run()
    next(b for b in at.button if b.label.startswith("Use the fake event")).click().run()
    for sb in at.selectbox:
        if sb.key and sb.key.startswith("payer-R"):
            sb.set_value(payer)
    at.run()
    next(b for b in at.button if b.label == "Draft rows").click().run()
    at.sidebar.radio[0].set_value("2. Review").run()
    return at


def test_approve_moves_to_next_receipt_and_reopen_undoes():
    at = drafted_app()
    assert at.sidebar.radio(key="review-pick").value == "R01"
    next(b for b in at.button if b.label == "Approve").click().run()
    assert at.sidebar.radio(key="review-pick").value == "R02"
    at.sidebar.radio(key="review-pick").set_value("R01").run()
    next(b for b in at.button if b.label == "Reopen").click().run()
    assert at.session_state["receipts"]["R01"].status.value == "drafted"


def test_needs_attention_filter_lists_only_flagged_receipts():
    at = drafted_app()
    at.sidebar.selectbox(key="review-filter").set_value("Needs attention").run()
    shown = {o.split(" ")[1] for o in at.sidebar.radio(key="review-pick").options}
    assert {"R02", "R06", "R13"} <= shown   # math errors (stub misreads and planted)
    assert "R01" not in shown


def test_failed_push_shows_message_instead_of_crashing(monkeypatch):
    from treasurer.post import LocalCsvSink

    def boom(self, *a, **k):
        raise ConnectionError("network down")
    monkeypatch.setattr(LocalCsvSink, "post", boom)
    at = drafted_app()
    for rid, r in list(at.session_state["receipts"].items()):
        at.session_state["receipts"][rid] = r.model_copy(update={"status": Status.REJECTED})
    at.session_state["receipts"]["R01"] = at.session_state["receipts"]["R01"].model_copy(
        update={"status": Status.APPROVED})
    at.sidebar.radio[0].set_value("3. Summary").run()
    next(b for b in at.button if b.label.startswith("Push to")).click().run()
    assert not at.exception
    assert any("stopped partway" in e.value for e in at.error)
    assert at.session_state["receipts"]["R01"].status is Status.APPROVED   # not marked posted


def test_upload_says_what_to_do_and_sets_every_payer_at_once():
    at = new_app().run()
    next(b for b in at.button if b.label.startswith("Use the fake event")).click().run()
    assert any("14 receipts in" in i.value and "14 still need a payer" in i.value for i in at.markdown)
    next(sb for sb in at.selectbox if sb.label == "Set every payer to").set_value("Member C")
    next(b for b in at.button if b.label == "Apply to all").click().run()
    assert at.selectbox(key="payer-R07.jpg").value == "Member C"
    assert any("Everyone's tagged" in i.value for i in at.markdown)
    next(b for b in at.button if b.label == "Draft rows").click().run()
    assert not at.exception
    assert {r.payer for r in at.session_state["receipts"].values()} == {"Member C"}


def test_each_step_says_what_comes_next():
    at = new_app().run()
    next(b for b in at.button if b.label.startswith("Use the fake event")).click().run()
    next(b for b in at.button if b.label == "Draft rows").click().run()
    next(b for b in at.button if b.label == "Go to Review →").click().run()
    assert at.sidebar.radio(key="step").value == "2. Review"
    assert not any(b.label == "Go to Summary →" for b in at.button)
    at.sidebar.radio(key="review-pick").set_value("R01").run()
    assert next(b for b in at.button if b.label == "Leave out").disabled  # needs a reason first
    for rid in list(at.session_state["receipts"]):  # leave everything out: quickest way to finish review
        at.sidebar.radio(key="review-pick").set_value(rid).run()
        at.text_input(key=f"note-{rid}").set_value("not ours").run()
        next(b for b in at.button if b.label == "Leave out").click().run()
    assert at.session_state["receipts"]["R01"].review_note == "not ours"
    next(b for b in at.button if b.label == "Go to Summary →").click().run()
    assert at.sidebar.radio(key="step").value == "3. Summary"
    assert any("Review" in m.value and "✓" in m.value for m in at.markdown)  # step bar marks review done
    next(b for b in at.button if b.label.startswith("Push to")).click().run()
    assert not at.exception
    next(b for b in at.button if b.label == "Go to Close out →").click().run()
    assert at.sidebar.radio(key="step").value == "4. Close out"


def test_drafting_the_same_photos_twice_reads_them_once():
    at = new_app().run()
    for _ in range(2):
        next(b for b in at.button if b.label.startswith("Use the fake event")).click().run()
        next(b for b in at.button if b.label == "Draft rows").click().run()
    assert len(at.session_state["receipts"]) == 14
    assert "Skipped 14 I'd already read" in at.session_state["last_draft"]


def test_a_finished_event_can_be_reopened_later():
    at = drafted_app()
    next(b for b in at.button if b.label == "Approve").click().run()
    at.sidebar.button(key="new-event").click().run()
    at.button(key="confirm-new-yes").click().run()
    assert at.session_state["receipts"] == {}
    assert at.session_state["event"]["name"] == "New event"
    assert at.session_state["event"]["members"].startswith("Member A")  # club settings carry over
    assert any("Fall Mentor Mixer" in m.value for m in at.sidebar.markdown)
    at.sidebar.button(key="open-past-0").click().run()
    assert not at.exception
    assert len(at.session_state["receipts"]) == 14
    assert at.session_state["receipts"]["R01"].status.value == "approved"
    assert at.sidebar.radio(key="step").value == "4. Close out"


def test_manual_purchase_needs_place_and_item_and_takes_dollar_signs():
    at = new_app().run()
    add = next(b for b in at.button if b.label == "Add")
    add.click().run()
    assert any("Fill in Place and Item" in e.value for e in at.error) and not at.session_state["receipts"]
    next(t for t in at.text_input if t.label == "Place").set_value("Campus Market")
    next(t for t in at.text_input if t.label == "Item").set_value("Ice")
    next(t for t in at.text_input if t.label == "Price per unit").set_value("$3.50")
    next(t for t in at.text_input if t.label == "Total").set_value("$3.50")
    next(b for b in at.button if b.label == "Add").click().run()
    assert not at.exception
    r = next(iter(at.session_state["receipts"].values()))
    assert str(r.items[0].price) == "3.50" and str(r.total) == "3.50"


def test_summary_warns_about_junk_and_negative_income():
    at = new_app().run()
    at.button[0].click().run()
    next(b for b in at.button if b.label == "Draft rows").click().run()
    at.sidebar.radio[0].set_value("3. Summary").run()
    at.button(key="add-source").click().run()  # Zelle
    at.button(key="add-source").click().run()  # Venmo
    at.text_input(key="income-Zelle").set_value("abc").run()
    at.text_input(key="income-Cash").set_value("-20").run()
    at.text_input(key="income-Venmo").set_value("$1,200.50").run()
    warnings = " ".join(w.value for w in at.warning)
    assert "isn't an amount" in warnings and "Cash is negative" in warnings
    assert next(m for m in at.metric if m.label == "Income").value == "$1,180.50"


def test_empty_review_guide_button_goes_to_upload():
    at = new_app().run()
    at.sidebar.radio[0].set_value("2. Review").run()
    assert any("Nothing to review yet" in m.value for m in at.markdown)
    at.button(key="go-review-empty").click().run()
    assert at.sidebar.radio[0].value == "1. Upload"
    assert not at.exception


def test_income_sources_can_be_added_renamed_and_removed():
    at = new_app().run()
    next(b for b in at.button if b.label.startswith("Use the fake event")).click().run()
    next(b for b in at.button if b.label == "Draft rows").click().run()
    at.sidebar.radio[0].set_value("3. Summary").run()
    assert at.session_state["event"]["sources"] == "Cash"  # a new event starts with Cash only
    at.button(key="add-source").click().run()
    at.button(key="add-source").click().run()
    at.text_input(key="income-Venmo").set_value("40").run()
    at.selectbox(key="src-Venmo").set_value("Ticket sales").run()
    assert at.text_input(key="income-Ticket sales").value == "40"
    assert "Venmo" not in at.session_state["event"]["sources"]
    at.button(key="rm-Cash").click().run()
    assert "Cash" not in at.session_state["event"]["sources"]
    assert not at.exception


def test_with_google_sheets_push_offers_the_sheet_not_an_excel_file(monkeypatch, tmp_path):
    from treasurer import sheets
    from treasurer.post import LocalCsvSink

    class FakeSheet(LocalCsvSink):
        label = "Google Sheets"
        url = "https://docs.google.com/spreadsheets/d/fake"

    monkeypatch.setattr(sheets.GoogleSheetsSink, "from_env", classmethod(lambda cls, *a: FakeSheet(tmp_path / "t.csv")))
    at = new_app().run()
    next(b for b in at.button if b.label.startswith("Use the fake event")).click().run()
    next(b for b in at.button if b.label == "Apply to all").click().run()
    next(b for b in at.button if b.label == "Draft rows").click().run()
    for rid in list(at.session_state["receipts"]):
        at.session_state["receipts"][rid] = at.session_state["receipts"][rid].model_copy(
            update={"status": Status.APPROVED if rid == "R01" else Status.REJECTED})
    at.sidebar.radio[0].set_value("3. Summary").run()
    next(b for b in at.button if b.label == "Push to Google Sheets").click().run()
    assert not at.exception
    assert any(e.label.startswith("Download a copy instead") for e in at.expander)
    assert [lb.label for lb in at.get("link_button")] == ["Open the sheet"]


def test_approve_all_clean_leaves_flagged_ones_and_decided_ones_lock():
    at = new_app().run()
    next(b for b in at.button if b.label.startswith("Use the fake event")).click().run()
    next(b for b in at.button if b.label == "Apply to all").click().run()
    next(b for b in at.button if b.label == "Draft rows").click().run()
    at.sidebar.radio[0].set_value("2. Review").run()
    at.button(key="approve-clean").click().run()
    rs = at.session_state["receipts"]
    approved = [x for x, r in rs.items() if r.status is Status.APPROVED]
    assert approved and len(approved) < len(rs)  # flagged ones wait for a person
    at.sidebar.radio(key="review-pick").set_value(approved[0]).run()
    assert next(b for b in at.button if b.label == "Approve").disabled
    assert any("Approved" in m.value and "Reopen" in m.value for m in at.markdown)
    assert not at.exception


def test_my_funder_rules():
    at = new_app().run()
    next(b for b in at.button if b.label.startswith("Use the fake event")).click().run()
    next(b for b in at.button if b.label == "Apply to all").click().run()
    next(b for b in at.button if b.label == "Draft rows").click().run()
    at.sidebar.radio[0].set_value("2. Review").run()
    at.button(key="approve-clean").click().run()
    at.sidebar.radio[0].set_value("4. Close out").run()
    assert at.selectbox(key="funder").value == "No funder"
    at.selectbox(key="funder").set_value("My funder's rules").run()
    next(t for t in at.text_input if t.label == "Funder name").set_value("Student Government").run()
    assert not at.exception
    assert any("Student Government" in m.value for m in [*at.markdown, *at.success, *at.caption, *at.error, *at.warning, *at.info])
    assert at.session_state["event"]["funder"]["name"] == "Student Government"


def test_a_new_event_starts_with_who_is_in_before_upload():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert at.header[0].value == "Start a new event"
    assert at.button(key="start-go").disabled  # nobody in yet
    at.text_input(key="new-member").set_value("Jamie Lee").run()  # Enter adds the name
    at.text_input(key="start-name").set_value("Spring Picnic (FAKE)").run()
    at.button(key="start-go").click().run()
    assert at.header[0].value == "Upload receipts"
    assert at.session_state["event"]["members"] == "Jamie Lee"
    assert at.session_state["event"]["event_id"].startswith("EVT-2026-11-14-SPRINGPICNIC")
    at.button(key="edit-members").click().run()  # back to change who's in
    assert at.header[0].value == "Start a new event"
    at.button(key="rm-member-0").click().run()
    assert at.session_state["event"]["members"] == ""


def test_a_forgotten_member_can_be_added_after_drafting():
    at = new_app("Jamie Lee").run()
    next(b for b in at.button if b.label.startswith("Use the fake event")).click().run()
    next(b for b in at.button if b.label == "Draft rows").click().run()
    event_id = at.session_state["event"]["event_id"]
    at.button(key="edit-members").click().run()
    assert at.text_input(key="start-name").disabled  # the receipts carry this event's id
    at.text_input(key="new-member").set_value("Sam Park").run()
    at.button(key="start-go").click().run()
    assert at.session_state["event"]["members"] == "Jamie Lee, Sam Park"
    assert at.session_state["event"]["event_id"] == event_id


def test_each_new_event_gets_the_next_ticket_color():
    from ui.tickets import NAMES, next_color, short_name
    assert next_color(None) == NAMES[0] and next_color(NAMES[-1]) == NAMES[0]
    assert next_color("Forest") != "Forest"
    assert short_name("Fall Mentor Mixer (FAKE)") == "Mentor Mixer"
    at = drafted_app()
    first = at.session_state["event"].get("color")
    at.sidebar.button(key="new-event").click().run()
    at.button(key="confirm-new-yes").click().run()
    assert at.session_state["event"]["color"] == next_color(first)
