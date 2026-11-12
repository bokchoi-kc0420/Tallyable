"""Save the review session to disk so a browser refresh or a crash loses nothing.

Streamlit keeps everything in memory per browser tab. A treasurer halfway through
14 receipts who hits refresh would lose every edit, so after each change the app
writes the session to output/session.json, and a new tab picks it up where it left off.
The photos (most of the bytes) go in a file of their own next to it, session.photos, written
only when they change: every click saves the small file, and the Past events list reads only that.
"""
from __future__ import annotations

import base64
import json
from datetime import date
from pathlib import Path

from .models import Receipt

VERSION = 2  # 1 kept the photos inside the event file; those files still open
# Saved as they are. The event, receipts and photos need converting, so dump/load handle them by name.
PLAIN_KEYS = ("notes", "edits", "income", "drafted_at", "review_started", "started", "step")
SAVED_KEYS = ("event", "receipts", "images", *PLAIN_KEYS)
STEP = "1. Upload"  # files saved before the step was kept open on Upload


def dump(state: dict) -> str:
    ev = dict(state["event"])
    ev["date"] = ev["date"].isoformat()
    return json.dumps({
        "version": VERSION,
        "event": ev,
        "receipts": {k: r.model_dump(mode="json") for k, r in state["receipts"].items()},
        "images": {k: m for k, (_, m) in state["images"].items()},  # media types; the bytes are in photo_file()
        **{k: state.get(k, STEP if k == "step" else None) for k in PLAIN_KEYS},
    }, sort_keys=True)


def photo_file(path: Path) -> Path:
    return path.with_suffix(".photos")


def write(path: Path, text: str) -> None:
    """Write atomically (temp file, then rename) so a crash mid-write can't corrupt it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def save(path: Path, state: dict, photos: bool = True) -> None:
    """Save the session. `photos=False` skips rewriting the photos when the caller knows they haven't changed."""
    if photos:
        write(photo_file(path), json.dumps({k: base64.b64encode(b).decode() for k, (b, _) in state["images"].items()}))
    write(path, dump(state))


def load_photos(path: Path, media: dict) -> dict:
    """Receipt id -> (bytes, media type) from the photo file; a missing or damaged one loses the photos, not the event."""
    try:
        data = json.loads(photo_file(path).read_text()) if media else {}
    except (OSError, ValueError):
        return {}
    return {k: (base64.b64decode(data[k]), m) for k, m in media.items() if k in data}


def load(path: Path) -> dict | None:
    """The saved state, or None if there is none or it can't be read."""
    try:
        raw = json.loads(path.read_text())
        if raw.get("version") not in (1, VERSION):
            return None
        ev = raw["event"]
        ev["date"] = date.fromisoformat(ev["date"])
        images = ({k: (base64.b64decode(b), m) for k, (b, m) in raw["images"].items()} if raw["version"] == 1
                  else load_photos(path, raw["images"]))
        return {
            "event": ev,
            "receipts": {k: Receipt.model_validate(v) for k, v in raw["receipts"].items()},
            "images": images,
            **{k: raw[k] for k in PLAIN_KEYS if k != "step"},
            "step": raw.get("step") or STEP,
        }
    except (OSError, ValueError, KeyError, TypeError):
        return None


def clear(path: Path) -> None:
    path.unlink(missing_ok=True)
    photo_file(path).unlink(missing_ok=True)


def past_events(folder: Path) -> list[dict]:
    """Every saved event in `folder` (one file per event id), newest event first.
    Each entry: path, event_id, name, date, receipts, color, finished, club."""
    out = []
    for p in folder.glob("*.json") if folder.exists() else []:
        try:
            raw = json.loads(p.read_text())
            ev = raw["event"]
            out.append({"path": p, "event_id": ev["event_id"], "name": ev["name"], "date": ev["date"],
                        "receipts": len(raw["receipts"]), "color": ev.get("color"),
                        "finished": bool(ev.get("finished")), "club": ev.get("club")})
        except (OSError, ValueError, KeyError, TypeError):
            continue  # a damaged file is skipped, not fatal
    return sorted(out, key=lambda e: e["date"], reverse=True)


def past_nets(folder: Path) -> list[dict]:
    """Every saved event's money: event_id, name, date, finished, club, and net (income minus
    counted receipts), for the club balance. Photos aren't decoded, so this stays quick."""
    from decimal import Decimal

    from .models import cell_decimal
    out = []
    for p in folder.glob("*.json") if folder.exists() else []:
        try:
            raw = json.loads(p.read_text())
            receipts = [Receipt.model_validate(v) for v in raw["receipts"].values()]
            spent = sum((r.posted_amount for r in receipts if r.counts), Decimal("0"))
            got = sum((cell_decimal(v or 0) for v in (raw.get("income") or {}).values()), Decimal("0"))
            ev = raw["event"]
            out.append({"event_id": ev["event_id"], "name": ev["name"], "date": ev["date"], "net": got - spent,
                        "color": ev.get("color"), "finished": bool(ev.get("finished")), "club": ev.get("club")})
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return out
