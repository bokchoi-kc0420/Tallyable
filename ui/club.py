"""Clubs: what stays the same all year (name, members, starting balance, profit target, where the
books go). Saved on this computer (output/clubs.json). One club is open at a time; every event
belongs to the club that was open when it started."""
from __future__ import annotations

import html
import json
import re

import streamlit as st

from ui.common import OUT, ss

CLUBS = OUT / "clubs.json"
OLD = OUT / "club.json"  # one unnamed club, from before clubs had names
DEFAULT = {"name": "My club", "members": [], "start_balance": None, "target": 10, "sheets": {}}
AVATARS = ["#1C5C36", "#B0413E", "#6B4E8A", "#2F4B7C", "#C8673C", "#1F7A73"]


def _read() -> dict:
    try:
        return json.loads(CLUBS.read_text())
    except (OSError, ValueError):
        pass
    try:  # the old single club becomes "My club", with its linked sheets
        old = json.loads(OLD.read_text())
    except (OSError, ValueError):
        return {"current": None, "clubs": {}}
    try:
        old["sheets"] = json.loads((OUT / "sheets.json").read_text())
    except (OSError, ValueError):
        pass
    return {"current": "my-club", "clubs": {"my-club": {**DEFAULT, **old}}}


def _write(data: dict) -> None:
    CLUBS.parent.mkdir(parents=True, exist_ok=True)
    CLUBS.write_text(json.dumps(data))


def clubs() -> dict[str, dict]:
    """Every club by id, in the order they were added."""
    return {k: {**DEFAULT, **v} for k, v in _read()["clubs"].items()}


def current() -> str | None:
    return _read()["current"]


def load() -> dict:
    """The open club's settings (defaults when there is no club yet)."""
    return clubs().get(current(), dict(DEFAULT))


def save(**changes) -> None:
    """Change the open club's settings."""
    data = _read()
    cid = data["current"]
    data["clubs"][cid] = {**data["clubs"].get(cid, DEFAULT), **changes}
    _write(data)


def set_current(cid: str) -> None:
    _write({**_read(), "current": cid})


def add(name: str, start_balance: float | None = None, members: list[str] = ()) -> str | None:
    """A new club, opened right away. Returns its id, or None for a blank name. A name that's
    already a club opens that club instead of making a second one with the same name."""
    name = name.strip()
    if not name:
        return None
    data = _read()
    same = next((cid for cid, c in data["clubs"].items() if c["name"].casefold() == name.casefold()), None)
    if same:
        _write({**data, "current": same})
        return same
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "club"
    cid, n = base, 2
    while cid in data["clubs"]:
        cid, n = f"{base}-{n}", n + 1
    data["clubs"][cid] = {**DEFAULT, "name": name, "start_balance": start_balance, "members": list(members)}
    _write({**data, "current": cid})
    return cid


def remove(cid: str) -> str | None:
    """Delete a club. The first club left is opened; returns its id (None when none are left)."""
    data = _read()
    data["clubs"].pop(cid, None)
    left = next(iter(data["clubs"]), None)
    _write({**data, "current": left if data["current"] == cid else data["current"]})
    return current()


def owns(event: dict) -> bool:
    """Is this saved event the open club's? Events from before clubs had names belong to the first club."""
    ids = list(_read()["clubs"])
    return (event.get("club") or (ids[0] if ids else None)) == current()


def seed(event: dict) -> None:
    """Saved events from before clubs existed: start a club from the open event's members."""
    if _read()["clubs"] or not event.get("members"):
        return
    _write({"current": "my-club", "clubs": {"my-club": {
        **DEFAULT, "members": [m.strip() for m in event["members"].split(",") if m.strip()],
        "start_balance": event.get("start_balance"), "target": event.get("target", 10)}}})


def add_member(key: str) -> str | None:
    """Enter / Add callback: the typed name joins the club (commas would split it, so they're dropped)."""
    name = ss.get(key, "").replace(",", " ").strip()
    ss[key] = ""
    members = load()["members"]
    if name and name not in members:
        save(members=[*members, name])
    return name or None


def initials(name: str) -> str:
    """First letters of the first two words, skipping words like "&" (safe inside CSS content too)."""
    return "".join(w[0] for w in name.split() if w[0].isalnum())[:2].upper()


def chip_style(prefix: str, names: list[str]) -> None:
    """Colored initials in front of each name chip, same colors as on the ticket."""
    rules = "".join(f'.st-key-{prefix}-{n} button::before {{ content: "{html.escape(initials(name))}"; '
                    f"background: {AVATARS[n % len(AVATARS)]}; }}" for n, name in enumerate(names))
    st.html(f"<style>{rules}</style>")
