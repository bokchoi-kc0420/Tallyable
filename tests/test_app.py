"""Headless run of the Streamlit app: draft the fake event, approve, fix a math error."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

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
