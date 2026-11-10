"""Tally's reaction to the event name never breaks the Start page."""
from treasurer import reaction


def test_reaction_falls_back_to_a_canned_line(monkeypatch):
    assert reaction.react("Spring Picnic") == "Ooh, a picnic! 🧺"  # stub mode (tests): no API call
    monkeypatch.setenv("TALLYABLE_EXTRACTOR", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")
    monkeypatch.setattr("anthropic.Anthropic", lambda **_: (_ for _ in ()).throw(RuntimeError("offline")))
    assert reaction.react("Board Meeting") == "Got it! Let's set it up."
