"""Pick the receipt reader: real Claude if an API key is set, else the stub.

The key lives in a local .env file at the repo root (git ignores it):
    ANTHROPIC_API_KEY=sk-ant-...
    TALLYABLE_MODEL=claude-sonnet-5-5   (optional; or claude-haiku-5-5, claude-opus-5-5)
Set TALLYABLE_EXTRACTOR=stub to force the stub (the tests do this).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from .extract import Extractor, StubExtractor

ROOT = Path(__file__).resolve().parent.parent
ANSWER_KEY = ROOT / "fake_event" / "answer_key.csv"


def make_extractor() -> tuple[Extractor, str]:
    """Returns (extractor, label). Label is "claude" or "stub"."""
    load_dotenv(ROOT / ".env")
    if os.getenv("TALLYABLE_EXTRACTOR", "").lower() != "stub" and os.getenv("ANTHROPIC_API_KEY"):
        from .claude_extract import MODEL, ClaudeExtractor
        return ClaudeExtractor(model=os.getenv("TALLYABLE_MODEL") or MODEL), "claude"
    return StubExtractor(ANSWER_KEY), "stub"
