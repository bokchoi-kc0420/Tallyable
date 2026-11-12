"""Receipt extraction behind one interface.

The app only talks to `Extractor`. Today it uses `StubExtractor`, which
replays the fake answer key with a few realistic AI misreads. Week 2 adds a
`ClaudeExtractor` with the same method, and nothing else in the app changes.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Protocol

from .loader import load_answer_key
from .models import Receipt


class ExtractionError(Exception):
    """The image could not be read into a receipt."""


class Extractor(Protocol):
    """`more` is the rest of the screenshots (bytes, file name) when one receipt came as several."""

    def extract(self, image: bytes, filename: str, event_id: str, receipt_id: str,
                more: list[tuple[bytes, str]] = ()) -> Receipt: ...


# Misreads a vision model plausibly makes. Each one should be caught in review,
# and the tax and tip ones should also trip the math check.
STUB_MISREADS: dict[str, dict] = {
    "R02": {"tax": Decimal("7.10")},           # 8 read as 0
    "R05": {"item_unit": (2, 7)},              # quantity 1 read as 7 on line 3
    "R08": {"place": "Party Supp1y Co"},       # l read as 1
    "R13": {"tip": Decimal("0")},              # printed tip line skipped
}


class StubExtractor:
    """Looks up the answer key by file name (R01.jpg -> R01). No network."""

    def __init__(self, answer_key: Path, misreads: dict[str, dict] | None = None):
        self._truth = {r.receipt_id: r for r in load_answer_key(answer_key)}
        self._misreads = STUB_MISREADS if misreads is None else misreads

    def extract(self, image: bytes, filename: str, event_id: str, receipt_id: str,
                more: list[tuple[bytes, str]] = ()) -> Receipt:
        key = Path(filename).stem.upper()
        if key not in self._truth:
            raise ExtractionError(f"Demo mode only reads the fake event's receipts, so it can't read {filename}.")
        r = self._truth[key]
        items = [i.model_copy() for i in r.items]
        update: dict = {"receipt_id": receipt_id, "event_id": event_id, "payer": None,
                        "image_file": filename, "image_hash": None}
        m = self._misreads.get(key, {})
        if "item_unit" in m:
            idx, unit = m["item_unit"]
            items[idx] = items[idx].model_copy(update={"unit": unit})
        for f in ("tax", "tip", "place", "total"):
            if f in m:
                update[f] = m[f]
        update["items"] = items
        return r.model_copy(update=update)
