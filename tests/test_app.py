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
