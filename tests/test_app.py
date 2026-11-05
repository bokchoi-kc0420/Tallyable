"""Headless run of the Streamlit app: draft the fake event, approve, fix a math error."""
import csv
import os
from pathlib import Path

from streamlit.testing.v1 import AppTest

from treasurer.models import Status

APP = str(Path(__file__).parent.parent / "app.py")


def test_draft_approve_and_fix():
    at = AppTest.from_file(APP, default_timeout=30).run()
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

    at.sidebar.radio[1].set_value("R06").run()
    assert any("off by" in e.value for e in at.error)
    at.text_input(key="total-R06").set_value("110.26").run()
    assert not any("off by" in e.value for e in at.error)


def test_push_logs_time_and_close_out_shows_owed_and_report():
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.button[0].click().run()
    for sb in at.selectbox:
        if sb.key and sb.key.startswith("payer-R"):
            sb.set_value("Member A")
    at.run()
    next(b for b in at.button if b.label == "Draft rows").click().run()
    at.sidebar.radio[0].set_value("2. Review").run()
    next(b for b in at.button if b.label == "Approve").click().run()  # R01

    at.sidebar.radio[0].set_value("3. Summary").run()
    at.text_input(key="income-Zelle").set_value("100.00").run()
    push = next(b for b in at.button if b.label.startswith("Push to"))
    assert push.disabled  # other receipts still drafted
    for rid, r in list(at.session_state["receipts"].items()):
        if rid != "R01":
            at.session_state["receipts"][rid] = r.model_copy(update={"status": Status.REJECTED})
    at.run()
    next(b for b in at.button if b.label.startswith("Push to")).click().run()
    assert not at.exception
    assert at.session_state["receipts"]["R01"].status is Status.POSTED
    assert {"Balance Sheet", "Ledger", "Expense Report"} <= {b.label for b in at.get("download_button")}
    log = Path(os.environ["TALLYABLE_OUTPUT_DIR"]) / "run_log.csv"
    row = list(csv.DictReader(log.open()))[-1]
    assert row["posted"] == "1" and row["minutes_review_to_push"] != ""

    at.sidebar.radio[0].set_value("4. Close out").run()
    assert not at.exception
    owed = next(d.value for d in at.dataframe if "owed" in d.value.columns)
    assert list(owed["payer"]) == ["Member A"] and owed["owed"][0] == "31.07"
    assert any(b.label.startswith("Download funder report") for b in at.get("download_button"))


def test_mark_paid_back_updates_owed():
    at = AppTest.from_file(APP, default_timeout=30).run()
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
    owed = next(d.value for d in at.dataframe if "owed" in d.value.columns)
    assert owed["owed"][0] == "0.00"


def test_password_gate(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "fake-test-pw")
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert at.text_input[0].label == "Password" and not at.sidebar.radio
    at.text_input[0].set_value("nope").run()
    assert any("Wrong password" in e.value for e in at.error)
    at.text_input[0].set_value("fake-test-pw").run()
    assert at.sidebar.radio[0].value == "1. Upload"


def test_unreadable_file_can_be_entered_by_hand():
    at = AppTest.from_file(APP, default_timeout=30).run()
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
    at = AppTest.from_file(APP, default_timeout=30).run()
    name = next(t for t in at.sidebar.text_input if t.label == "Event name")
    name.set_value("Winter Social (FAKE)").run()
    assert at.session_state["event"]["event_id"].startswith("EVT-2026-11-14-WINTER")
    members = next(t for t in at.sidebar.text_input if t.label == "Members who might pay")
    members.set_value("Treasurer, Member Z").run()
    assert "Member Z" in [o for sb in at.selectbox if sb.label == "Payer" for o in sb.options]

    at.button[0].click().run()
    next(b for b in at.button if b.label == "Draft rows").click().run()
    at.run()
    assert next(t for t in at.sidebar.text_input if t.label == "Event name").disabled
    assert all(r.event_id.startswith("EVT-2026-11-14-WINTER") for r in at.session_state["receipts"].values())
    at.sidebar.checkbox[0].check().run()
    next(b for b in at.sidebar.button if b.label == "Start a new event").click().run()
    assert at.session_state["receipts"] == {}


def test_refresh_can_resume_the_saved_session():
    at = AppTest.from_file(APP, default_timeout=30).run()
    next(b for b in at.button if b.label.startswith("Use the fake event")).click().run()
    for sb in at.selectbox:
        if sb.key and sb.key.startswith("payer-R"):
            sb.set_value("Member A")
    at.run()
    next(b for b in at.button if b.label == "Draft rows").click().run()
    at.sidebar.radio[0].set_value("2. Review").run()
    next(b for b in at.button if b.label == "Approve").click().run()

    fresh = AppTest.from_file(APP, default_timeout=30).run()  # a new browser tab
    assert fresh.session_state["receipts"] == {}
    assert any("1 reviewed" in i.value for i in fresh.info)
    next(b for b in fresh.button if b.label == "Resume where I left off").click().run()
    assert fresh.session_state["receipts"]["R01"].status.value == "approved"
    assert fresh.session_state["images"]["R01"][1] == "image/jpeg"


def test_corrupt_session_file_is_ignored():
    out = Path(os.environ["TALLYABLE_OUTPUT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    (out / "session.json").write_text("{not json")
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert not any(b.label == "Resume where I left off" for b in at.button)


def drafted_app(payer="Member A"):
    at = AppTest.from_file(APP, default_timeout=30).run()
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
    at.sidebar.selectbox[0].set_value("Needs attention").run()
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
    at = AppTest.from_file(APP, default_timeout=30).run()
    next(b for b in at.button if b.label.startswith("Use the fake event")).click().run()
    assert any("14 receipts loaded" in i.value and "14 still have no payer" in i.value for i in at.info)
    at.selectbox(key="payer-all").set_value("Member C")
    next(b for b in at.button if b.label == "Apply to all").click().run()
    assert at.selectbox(key="payer-R07.jpg").value == "Member C"
    assert any("Every receipt has a payer" in i.value for i in at.info)
    next(b for b in at.button if b.label == "Draft rows").click().run()
    assert not at.exception
    assert {r.payer for r in at.session_state["receipts"].values()} == {"Member C"}


def test_each_step_says_what_comes_next():
    at = AppTest.from_file(APP, default_timeout=30).run()
    next(b for b in at.button if b.label.startswith("Use the fake event")).click().run()
    next(b for b in at.button if b.label == "Draft rows").click().run()
    next(b for b in at.button if b.label == "Go to Review →").click().run()
    assert at.sidebar.radio(key="step").value == "2. Review"
    assert not any(b.label == "Go to Summary →" for b in at.button)
    for rid in list(at.session_state["receipts"]):  # reject everything: quickest way to finish review
        at.sidebar.radio(key="review-pick").set_value(rid).run()
        next(b for b in at.button if b.label == "Reject").click().run()
    next(b for b in at.button if b.label == "Go to Summary →").click().run()
    assert at.sidebar.radio(key="step").value == "3. Summary"
    assert any("Review" in m.value and "✓" in m.value for m in at.markdown)  # step bar marks review done
    next(b for b in at.button if b.label.startswith("Push to")).click().run()
    assert not at.exception
    next(b for b in at.button if b.label == "Go to Close out →").click().run()
    assert at.sidebar.radio(key="step").value == "4. Close out"


def test_drafting_the_same_photos_twice_reads_them_once():
    at = AppTest.from_file(APP, default_timeout=30).run()
    for _ in range(2):
        next(b for b in at.button if b.label.startswith("Use the fake event")).click().run()
        next(b for b in at.button if b.label == "Draft rows").click().run()
    assert len(at.session_state["receipts"]) == 14
    assert "Skipped 14 already drafted" in at.session_state["last_draft"]


def test_a_finished_event_can_be_reopened_later():
    at = drafted_app()
    next(b for b in at.button if b.label == "Approve").click().run()
    at.sidebar.checkbox[0].check().run()
    next(b for b in at.sidebar.button if b.label == "Start a new event").click().run()
    assert at.session_state["receipts"] == {}
    assert at.session_state["event"]["name"] == "New event"
    assert at.session_state["event"]["members"].startswith("Member A")  # club settings carry over
    assert "Fall Mentor Mixer" in at.sidebar.selectbox(key="past-pick").options[0]
    next(b for b in at.sidebar.button if b.label == "Open this event").click().run()
    assert not at.exception
    assert len(at.session_state["receipts"]) == 14
    assert at.session_state["receipts"]["R01"].status.value == "approved"
    assert at.sidebar.radio(key="step").value == "4. Close out"
