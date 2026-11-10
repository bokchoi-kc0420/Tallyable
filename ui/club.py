"""Club settings: what stays the same all year (members, starting balance, profit target, where
the books go). Saved on this computer (output/club.json), so every new event starts from them."""
from __future__ import annotations

import html
import json

import streamlit as st

from ui import connect
from ui.common import OUT, ss

CLUB = OUT / "club.json"
DEFAULT = {"members": [], "start_balance": None, "target": 10, "books": None}  # books: None (not asked) or "local"
AVATARS = ["#1C5C36", "#B0413E", "#6B4E8A", "#2F4B7C", "#C8673C", "#1F7A73"]


def load() -> dict:
    try:
        return {**DEFAULT, **json.loads(CLUB.read_text())}
    except (OSError, ValueError):
        return dict(DEFAULT)


def save(**changes) -> None:
    CLUB.parent.mkdir(parents=True, exist_ok=True)
    CLUB.write_text(json.dumps({**load(), **changes}))


def seed(event: dict) -> None:
    """Saved events from before Club settings existed: start the club from the open event."""
    if CLUB.exists() or not event.get("members"):
        return
    save(members=[m.strip() for m in event["members"].split(",") if m.strip()],
         start_balance=event.get("start_balance"), target=event.get("target", 10))


def add_member(key: str) -> str | None:
    """Enter / Add callback: the typed name joins the club (commas would split it, so they're dropped)."""
    name = ss.get(key, "").replace(",", " ").strip()
    ss[key] = ""
    members = load()["members"]
    if name and name not in members:
        save(members=[*members, name])
    return name or None


def initials(name: str) -> str:
    return "".join(w[0] for w in name.split()[:2]).upper()


def chip_style(prefix: str, names: list[str]) -> None:
    """Colored initials in front of each name chip, same colors as on the ticket."""
    rules = "".join(f'.st-key-{prefix}-{n} button::before {{ content: "{html.escape(initials(name))}"; '
                    f"background: {AVATARS[n % len(AVATARS)]}; }}" for n, name in enumerate(names))
    st.html(f"<style>{rules}</style>")


def settings() -> None:
    """The Club settings dropdown in the sidebar."""
    club = load()
    with st.sidebar.expander("Club settings", icon=":material/settings:"):
        st.markdown("**Club members**")
        st.caption("Everyone who might pay for club stuff. New events start with all of them.")
        c = st.columns([2, 1.4], vertical_alignment="bottom")
        c[0].text_input("Name", key="club-new", placeholder="Name", label_visibility="collapsed",
                        on_change=add_member, args=("club-new",))
        c[1].button("Add", icon=":material/add:", key="club-add", width="stretch", on_click=add_member, args=("club-new",))
        names = club["members"]
        with st.container(horizontal=True, key="club-chips"):
            for n, name in enumerate(names):
                st.button(name, icon=":material/close:", icon_position="right", key=f"club-rm-{n}",
                          help=f"Remove {name} from the club list", on_click=save,
                          kwargs={"members": [x for x in names if x != name]})
        chip_style("club-rm", names)
        start = st.number_input("Starting balance this school year ($)", value=club["start_balance"],
                                step=10.0, format="%.2f", placeholder="0.00", key="club-start",
                                help="What the club had before this year's first event. Type it once a year: "
                                     "the General Ledger starts from it.")
        target = int(st.number_input("Profit target (%)", min_value=0, max_value=100, value=int(club["target"]),
                                     help="The margin your club aims for. The Summary shows if an event hit it."))
        if (start, target) != (club["start_balance"], club["target"]):
            save(start_balance=start, target=target)
        st.markdown("**Google Sheets**")
        label = "Google Sheets connected" if connect.linked() else "Connect Google Sheets"
        if st.button(label, icon=":material/link:", key="open-connect", width="stretch"):
            connect.dialog()
