"""Save the review session to disk so a browser refresh or a crash loses nothing.

Streamlit keeps everything in memory per browser tab. A treasurer halfway through
14 receipts who hits refresh would lose every edit, so after each change the app
writes the session to output/session.json, and the Upload screen offers to resume.
Photos are stored base64 so the file is self-contained (about 1 MB for 14 photos).
"""
from __future__ import annotations

import base64
import json
from datetime import date
from pathlib import Path

from .models import Receipt

VERSION = 1


def dump(state: dict) -> str:
    ev = dict(state["event"])
    ev["date"] = ev["date"].isoformat()
    return json.dumps({
        "version": VERSION,
        "event": ev,
        "receipts": {k: r.model_dump(mode="json") for k, r in state["receipts"].items()},
        "images": {k: [base64.b64encode(b).decode(), m] for k, (b, m) in state["images"].items()},
        "notes": state["notes"],
        "edits": state["edits"],
        "income": state["income"],
        "drafted_at": state["drafted_at"],
        "review_started": state["review_started"],
        "started": state["started"],
    }, sort_keys=True)


def save(path: Path, state: dict) -> None:
    """Write atomically (temp file, then rename) so a crash mid-write can't corrupt it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(dump(state))
    tmp.replace(path)


def load(path: Path) -> dict | None:
    """The saved state, or None if there is none or it can't be read."""
    try:
        raw = json.loads(path.read_text())
        if raw.get("version") != VERSION:
            return None
        ev = raw["event"]
        ev["date"] = date.fromisoformat(ev["date"])
        return {
            "event": ev,
            "receipts": {k: Receipt.model_validate(v) for k, v in raw["receipts"].items()},
            "images": {k: (base64.b64decode(b), m) for k, (b, m) in raw["images"].items()},
            "notes": raw["notes"], "edits": raw["edits"], "income": raw["income"],
            "drafted_at": raw["drafted_at"], "review_started": raw["review_started"], "started": raw["started"],
        }
    except (OSError, ValueError, KeyError, TypeError):
        return None


def clear(path: Path) -> None:
    path.unlink(missing_ok=True)
