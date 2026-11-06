from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from treasurer.demo_workspace import create_workspace, workspace_path

APP = str(Path(__file__).parents[1] / "app.py")


def test_workspace_codes_cannot_select_paths(tmp_path):
    first, second = create_workspace(tmp_path), create_workspace(tmp_path)
    assert first != second
    assert workspace_path(tmp_path, first) != workspace_path(tmp_path, second)
    for code in ("../session", "", "a" * 64, "/tmp/other"):
        with pytest.raises(ValueError):
            workspace_path(tmp_path, code)


def test_two_testers_and_returning_session(monkeypatch, tmp_path):
    monkeypatch.setenv("TALLYABLE_PUBLIC_DEMO", "true")
    monkeypatch.setenv("TALLYABLE_SHEET_ID", "must-not-use-shared-sheet")
    from treasurer.sheets import GoogleSheetsSink
    monkeypatch.setattr(GoogleSheetsSink, "from_env", lambda *a: pytest.fail("Shared Sheet accessed"))
    first = AppTest.from_file(APP, default_timeout=30).run()
    next(b for b in first.button if b.label == "Start my demo").click().run()
    code = first.session_state["_demo_code"]
    next(b for b in first.button if b.label.startswith("Use the fake event")).click().run()
    next(b for b in first.button if b.label == "Draft rows").click().run()
    first.sidebar.radio[0].set_value("3. Summary").run()
    first.text_input(key="income-Cash").set_value("123.45").run()
    assert not first.exception

    second = AppTest.from_file(APP, default_timeout=30).run()
    next(b for b in second.button if b.label == "Start my demo").click().run()
    assert second.session_state["receipts"] == {}
    assert second.session_state["income"] == {}
    assert second.session_state["_demo_code"] != code
    assert not second.exception

    returning = AppTest.from_file(APP, default_timeout=30).run()
    next(t for t in returning.text_input if t.label == "Return code").set_value(code)
    next(b for b in returning.button if b.label == "Resume my demo").click().run()
    assert returning.sidebar.radio[0].value == "3. Summary"
    assert returning.text_input(key="income-Cash").value == "123.45"
    assert len(returning.session_state["receipts"]) == 14
    assert not returning.exception
    root = tmp_path / "output"
    assert not (root / "session.json").exists()
    assert (workspace_path(root, code) / "session.json").exists()


def test_public_demo_never_uses_paid_reader(monkeypatch):
    from treasurer.reader import make_extractor
    monkeypatch.setenv("TALLYABLE_PUBLIC_DEMO", "true")
    monkeypatch.setenv("TALLYABLE_EXTRACTOR", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
    assert make_extractor()[1] == "stub"
