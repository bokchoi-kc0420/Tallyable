"""Tally's one-line reaction to a new event's name ("Ooh, a picnic! 🧺") on the Start page.

Just for fun: it never touches money or the books. With an API key, Claude writes the line;
without one (start.bat's stub mode), or if the call fails, a canned line shows instead.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

from .reader import ROOT

MODEL = "claude-opus-5-5"
SYSTEM = ("You are Tally, a cheerful paper-receipt mascot in an app that helps college club treasurers "
          "close out events. The user message is the name of the club event being set up. Reply with "
          "ONE short, excited reaction to it, at most 7 words, and at most one emoji. Casual and friendly. "
          "No quotes, no hashtags, no questions about money. If the name is unclear, just cheer the event on.")
CANNED = {"picnic": "Ooh, a picnic! 🧺", "bbq": "BBQ time! 🔥", "barbecue": "BBQ time! 🔥",
          "gala": "Fancy! A gala! ✨", "retreat": "Retreat time! Pack snacks! 🏕️", "dinner": "Dinner party! 🍜",
          "party": "Party time! 🎉", "movie": "Movie night! 🍿", "game": "Game on! 🎲"}


def canned(name: str) -> str:
    low = name.lower()
    return next((line for word, line in CANNED.items() if word in low), "Got it! Let's set it up.")  # neutral fallback


def react(name: str) -> str:
    """One short line about the event. Falls back quietly to a canned line."""
    load_dotenv(ROOT / ".env")
    if os.getenv("TALLYABLE_EXTRACTOR", "").lower() == "stub" or not os.getenv("ANTHROPIC_API_KEY"):
        return canned(name)
    try:
        import anthropic
        resp = anthropic.Anthropic(timeout=8.0, max_retries=0).messages.create(
            model=MODEL, max_tokens=1024, output_config={"effort": "low"}, system=SYSTEM,
            messages=[{"role": "user", "content": name[:80]}])
    except Exception:  # a fun line is never worth an error box
        return canned(name)
    text = next((b.text for b in resp.content if b.type == "text"), "").strip().strip('"')
    if resp.stop_reason != "end_turn" or not text or len(text) > 60:
        return canned(name)
    return text
