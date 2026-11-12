"""Demo and real mode keep their data apart: switching never mixes a fake receipt into real books."""
import os
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).parent.parent / "app.py")


def test_demo_and_real_never_share_data():
    base = Path(os.environ["TALLYABLE_OUTPUT_DIR"])
    at = AppTest.from_file(APP, default_timeout=30).run()  # a new install opens in real mode: set up your club
    at.text_input(key="club-first-name").set_value("Chess Club").run()
    at.button(key="club-first-add").click().run()
    at.button(key="home-go").click().run()
    assert not [b for b in at.button if b.label.startswith("Use the fake event")]  # no fake receipts in real mode

    at.button(key="club-home").click().run()
    at.button(key="to-demo").click().run()
    assert not at.exception
    assert any("Demo mode" in h.value for h in at.sidebar.html)
    assert len(at.session_state["demo"]) == 14  # the sample receipts are already loaded
    assert "Sunrise Hiking Club" in (base / "demo" / "clubs.json").read_text()
    assert "Sunrise" not in (base / "real" / "clubs.json").read_text()

    at.button(key="to-real").click().run()
    assert not at.exception
    assert not any("Demo mode" in h.value for h in at.sidebar.html)
    assert (base / "mode.txt").read_text() == "real"
    fresh = AppTest.from_file(APP, default_timeout=30).run()  # a new tab opens the mode you left in
    assert not any("Demo mode" in h.value for h in fresh.sidebar.html)


def test_real_books_never_go_to_the_env_test_sheet(monkeypatch):
    monkeypatch.setenv("TALLYABLE_SHEET_ID", "the-test-sheet")
    from ui import common
    monkeypatch.setitem(common.ss, "demo_mode", False)
    sink, error = common.get_sink()
    assert sink.label != "Google Sheets" and error is None
