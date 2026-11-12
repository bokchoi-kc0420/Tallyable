"""Headless run of the Streamlit app: draft the fake event, approve, fix a math error."""
import csv
import os
from datetime import date
from pathlib import Path

from streamlit.testing.v1 import AppTest

from treasurer.models import Status

APP = str(Path(__file__).parent.parent / "app.py")
MEMBERS = "Member A, Member B, Member C, Member D"


def new_app(members: str = MEMBERS) -> AppTest:
    """The app with the club's members already added, as a treasurer would on Upload."""
    from ui.sidebar import DEFAULT_EVENT
    at = AppTest.from_file(APP, default_timeout=30)
    base = Path(os.environ["TALLYABLE_OUTPUT_DIR"])
    base.mkdir(parents=True, exist_ok=True)
    (base / "mode.txt").write_text("demo")  # the fake event's receipts only show in the demo
    at.session_state["event"] = {**DEFAULT_EVENT, "event_id": "EVT-FAKE-01", "name": "Fall Mentor Mixer (FAKE)",
                                 "date": date(2026, 11, 14), "attendees": 45, "members": members, "set_up": True}
    return at


def draft(at) -> None:
    """Click Read, tagging every untagged receipt with the first member first (Read waits for tags)."""
    if at.button(key="read").disabled:
        next(b for b in at.button if b.label == "Apply to all").click().run()
    at.button(key="read").click().run()


def owed_table(at) -> list[dict]:
    """Still owed per payer, read back from the Who's owed ledger."""
    import re
    cells = [re.search(r'data-payer="(.*?)">(.*?)<', m.value) for m in at.markdown]
    return [{"Payer": c[1], "Owed": c[2]} for c in cells if c]


def test_draft_approve_and_fix():
    at = new_app().run()
    at.button[0].click().run()  # use the fake event's receipts
    for sb in at.selectbox:
        if sb.key and sb.key.startswith("payer-R"):
            sb.set_value("Member A")
    at.run()
    draft(at)
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
    draft(at)
    at.sidebar.radio[0].set_value("2. Review").run()
    next(b for b in at.button if b.label == "Approve").click().run()  # R01

    at.sidebar.radio[0].set_value("3. Summary").run()
    at.text_input(key="income-Cash").set_value("100.00").run()
    push = at.download_button(key="dl-xlsx-row")
    assert push.disabled  # other receipts still drafted
    for rid, r in list(at.session_state["receipts"].items()):
        if rid != "R01":
            at.session_state["receipts"][rid] = r.model_copy(update={"status": Status.REJECTED})
    at.run()
    at.download_button(key="dl-xlsx-row").click().run()  # no Google Sheet: saving is the push
    assert not at.exception
    assert at.session_state["receipts"]["R01"].status is Status.POSTED
    assert {"Balance Sheet", "General Ledger", "Expense Report", "Receipts"} <= {b.label for b in at.get("download_button")}
    log = Path(os.environ["TALLYABLE_OUTPUT_DIR"]) / "demo" / "run_log.csv"
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
    draft(at)
    r = at.session_state["receipts"]["R01"]
    at.session_state["receipts"]["R01"] = r.model_copy(update={"status": Status.APPROVED})
    at.sidebar.radio[0].set_value("4. Close out").run()
    at.selectbox(key="method-Member C").set_value("Venmo").run()
    at.button(key="paid-Member C").click().run()
    assert not at.exception
    assert owed_table(at)[0]["Owed"] == "$0.00"
    rows = list(csv.DictReader((Path(os.environ["TALLYABLE_OUTPUT_DIR"], "demo", "reimbursements.csv")).read_text().splitlines()))
    assert rows[-1]["method"] == "Venmo" and rows[-1]["payer"] == "Member C"
    assert not [b for b in at.button if b.key == "paid-Member C"]  # now shows Paid instead
    at.button(key="undo-paid").click().run()  # a misclick can be taken back
    assert owed_table(at)[0]["Owed"] != "$0.00"
    assert not list(csv.DictReader((Path(os.environ["TALLYABLE_OUTPUT_DIR"], "demo", "reimbursements.csv")).read_text().splitlines()))


def test_mark_paid_back_updates_owed():
    at = new_app().run()
    at.button[0].click().run()
    for sb in at.selectbox:
        if sb.key and sb.key.startswith("payer-R"):
            sb.set_value("Member B")
    at.run()
    draft(at)
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
    draft(at)
    at.run()
    next(t for t in at.sidebar.text_input if t.label == "Event name").set_value("Winter Gala (FAKE)").run()
    assert at.session_state["event"]["name"] == "Winter Gala (FAKE)"  # renaming is fine before Push...
    assert at.session_state["event"]["event_id"].startswith("EVT-2026-11-14-WINTER")  # ...the id stays put
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
    draft(at)
    at.sidebar.radio[0].set_value("2. Review").run()
    next(b for b in at.button if b.label == "Approve").click().run()

    fresh = AppTest.from_file(APP, default_timeout=30).run()  # a new browser tab, e.g. back from the home page
    assert fresh.sidebar.radio[0].value == "2. Review"
    assert fresh.session_state["receipts"]["R01"].status.value == "approved"
    assert fresh.session_state["images"]["R01"][1] == "image/jpeg"


def test_corrupt_session_file_is_ignored():
    out = Path(os.environ["TALLYABLE_OUTPUT_DIR"]) / "demo"
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
    draft(at)
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
    at.download_button(key="dl-xlsx-row").click().run()  # no Google Sheet: saving is the push
    assert not at.exception
    assert any("stopped partway" in e.value for e in at.error)
    assert at.session_state["receipts"]["R01"].status is Status.APPROVED   # not marked posted


def test_upload_says_what_to_do_and_sets_every_payer_at_once():
    at = new_app().run()
    next(b for b in at.button if b.label.startswith("Use the fake event")).click().run()
    assert any("14 receipts in" in i.value for i in at.markdown)
    assert any("14 still need a payer" in i.value for i in at.markdown)
    next(sb for sb in at.selectbox if sb.label == "Set every payer to").set_value("Member C")
    next(b for b in at.button if b.label == "Apply to all").click().run()
    assert at.selectbox(key="payer-R07.jpg").value == "Member C"
    assert any("Everyone's tagged" in i.value for i in at.markdown)
    draft(at)
    assert not at.exception
    assert {r.payer for r in at.session_state["receipts"].values()} == {"Member C"}


def test_each_step_says_what_comes_next():
    at = new_app().run()
    next(b for b in at.button if b.label.startswith("Use the fake event")).click().run()
    draft(at)
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
    next(b for b in at.button if b.label == "Next: Close out").click().run()
    assert at.sidebar.radio(key="step").value == "4. Close out"


def test_photos_already_read_are_not_read_again():
    at = new_app().run()
    next(b for b in at.button if b.label.startswith("Use the fake event")).click().run()
    draft(at)
    next(b for b in at.button if b.label.startswith("Use the fake event")).click().run()
    assert not [b for b in at.button if b.key == "read"]  # nothing new: Go to Review is the next step
    assert len(at.session_state["receipts"]) == 14
    from treasurer.reader import make_extractor
    from ui.upload import read_one
    photo, data = at.session_state["images"]["R01"]
    import hashlib
    f, r, problem, repeat = read_one(make_extractor()[0], "copy.jpg", photo, "EVT", "R99", {hashlib.sha256(photo).hexdigest(): "R01"})
    assert r is None and problem is None and repeat == "R01"  # the same photo under another name is skipped, not paid for twice


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
    draft(at)
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
    draft(at)
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
    draft(at)
    for rid in list(at.session_state["receipts"]):
        at.session_state["receipts"][rid] = at.session_state["receipts"][rid].model_copy(
            update={"status": Status.APPROVED if rid == "R01" else Status.REJECTED})
    at.sidebar.radio[0].set_value("3. Summary").run()
    next(b for b in at.button if b.label == "Push to Google Sheets").click().run()
    assert not at.exception
    assert "Download as Excel" in [b.label for b in at.download_button]
    assert [lb.label for lb in at.get("link_button")] == ["Open the sheet"]


def test_approve_all_clean_leaves_flagged_ones_and_decided_ones_lock():
    at = new_app().run()
    next(b for b in at.button if b.label.startswith("Use the fake event")).click().run()
    next(b for b in at.button if b.label == "Apply to all").click().run()
    draft(at)
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
    draft(at)
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
    base = Path(os.environ["TALLYABLE_OUTPUT_DIR"])
    base.mkdir(parents=True, exist_ok=True)
    (base / "mode.txt").write_text("real")  # your own club, not the demo's sample one
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert any("Welcome to Tallyable" in h.value for h in at.html)  # the club comes first
    at.text_input(key="club-first-name").set_value("Sunrise Hiking Club").run()
    at.button(key="club-first-add").click().run()
    at.sidebar.button(key="new-event").click().run()
    assert at.header[0].value == "Start a new event"
    assert at.button(key="start-go").disabled  # nobody in yet
    at.text_input(key="new-member").set_value("Jamie Lee").run()  # Enter adds the name
    at.text_input(key="start-name").set_value("Spring Picnic (FAKE)").run()
    at.button(key="start-go").click().run()
    assert at.header[0].value == "Upload receipts"
    assert at.session_state["event"]["members"] == "Jamie Lee"
    assert at.session_state["event"]["event_id"].startswith(f"EVT-{date.today().isoformat()}-SPRINGPICNIC-")  # blank start: today
    at.button(key="edit-members").click().run()  # back to change who's in
    assert at.header[0].value == "Start a new event"
    at.pills(key="roster").unselect("Jamie Lee").run()  # tap to leave someone out
    assert at.session_state["event"]["members"] == ""


def test_a_forgotten_member_can_be_added_after_drafting():
    at = new_app("Jamie Lee").run()
    next(b for b in at.button if b.label.startswith("Use the fake event")).click().run()
    draft(at)
    event_id = at.session_state["event"]["event_id"]
    at.button(key="edit-members").click().run()
    at.text_input(key="start-name").set_value("Fall Mixer, renamed")  # renaming is fine: the id stays
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


def test_connect_catches_a_viewer_only_share(monkeypatch):
    from ui import connect

    class Book:
        title = "Club books"

        def __init__(self, editor):
            self.editor = editor

        def batch_update(self, body):
            if not self.editor:
                raise PermissionError("403")

    class Client:
        def __init__(self, editor):
            self.editor = editor

        def open_by_key(self, key):
            return Book(self.editor)

    monkeypatch.setattr(connect, "bot_client", lambda root, key: Client(editor=False))
    assert "Editor, not Viewer" in connect.check({"book": "x"})
    monkeypatch.setattr(connect, "bot_client", lambda root, key: Client(editor=True))
    assert connect.check({"book": "x"}) is None


def test_read_waits_for_every_payer():
    at = new_app().run()
    next(b for b in at.button if b.label.startswith("Use the fake event")).click().run()
    assert at.button(key="read").label == "Read 14 receipts" and at.button(key="read").disabled
    next(b for b in at.button if b.label == "Apply to all").click().run()
    assert not at.button(key="read").disabled


def test_delete_event_removes_it_for_good():
    at = drafted_app()
    at.sidebar.button(key="delete-event").click().run()
    at.button(key="delete-yes").click().run()
    assert not at.exception
    assert at.session_state["receipts"] == {}
    assert not any("Fall Mentor Mixer" in m.value for m in at.sidebar.markdown)


def test_club_members_fill_each_new_event_and_settings_hold_the_year():
    at = new_app("Kevin, Mitch Lee").run()  # an older event: the club list starts from it
    at.button(key="club-home").click().run()
    at.text_input(key="club-new").set_value("Sam Cho").run()
    next(n for n in at.number_input if n.label == "Started the year with ($)").set_value(420.0).run()  # Club settings
    at.sidebar.button(key="new-event").click().run()
    at.button(key="confirm-new-yes").click().run()
    assert at.session_state["event"]["members"] == "Kevin, Mitch Lee, Sam Cho"
    assert at.session_state["event"]["start_balance"] == 420.0
    at.pills(key="roster").unselect("Mitch Lee").run()
    assert at.session_state["event"]["members"] == "Kevin, Sam Cho"


def test_each_club_keeps_its_own_members_events_and_balance():
    at = new_app("Kevin, Mitch Lee").run()  # an older event becomes "My club"
    at.sidebar.button(key="new-event").click().run()
    at.button(key="confirm-new-yes").click().run()  # the older event is saved under My club
    at.button(key="club-menu-new").click().run()  # the New club pop-up
    at.text_input(key="new-club-name").set_value("Chess Club").run()
    at.text_input(key="new-club-who").set_value("Dana Cho").run()  # the crew can join in the pop-up
    at.button(key="new-club-add").click().run()
    assert any("Chess Club" in h.value for h in at.html)
    at.sidebar.button(key="new-event").click().run()
    assert at.session_state["event"]["members"] == "Dana Cho"
    assert at.session_state["event"]["club"] == "chess-club"
    assert not any("Past events" in e.label for e in at.sidebar.expander)  # My club's event isn't Chess Club's
    at.button(key="club-pick-my-club").click().run()
    assert at.session_state["event"]["name"] == "Fall Mentor Mixer (FAKE)"  # back to My club's open event
    fresh = AppTest.from_file(APP, default_timeout=30).run()  # a new tab with two clubs asks which one
    assert fresh.header[0].value == "Which club are you doing the books for?"


def test_club_home_steps_open_the_event_and_clubs_can_be_deleted():
    at = new_app().run()
    at.button(key="club-home").click().run()
    at.sidebar.radio(key="step-home").set_value("1. Upload").run()  # the event's own step: used to do nothing
    assert at.session_state["view"] == "event"
    at.button(key="club-menu-new").click().run()
    at.text_input(key="new-club-name").set_value("Chess Club").run()
    at.button(key="new-club-add").click().run()
    at.button(key="club-menu-new").click().run()  # the same name again opens it, no second Chess Club
    at.text_input(key="new-club-name").set_value("chess club").run()
    at.button(key="new-club-add").click().run()
    from ui import club
    assert [c["name"] for c in club.clubs().values()] == ["My club", "Chess Club"]
    at.button(key="delete-club").click().run()
    at.button(key="club-delete-yes").click().run()
    assert not at.exception
    assert [c["name"] for c in club.clubs().values()] == ["My club"]
    assert club.current() == "my-club"
