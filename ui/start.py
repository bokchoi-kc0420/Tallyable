"""Step 0 of a new event: name it, date it, and say who's in. Upload opens once someone is."""
from __future__ import annotations

import streamlit as st

from ui.common import ART, payers, ss
from ui.sidebar import event_id_for


def needed() -> bool:
    """A new event that isn't set up yet, or Edit was clicked. Older saved events with receipts
    (from before this page existed) have no set_up flag and skip it."""
    return ss.event.get("set_up") is False or (not ss.receipts and "set_up" not in ss.event)


def reopen() -> None:
    ss.event = {**ss.event, "set_up": False}


def set_members(names: list[str]) -> None:
    ss.event = {**ss.event, "members": ", ".join(names)}


def add_member() -> None:
    """Button and Enter callback: add the typed name (commas would split it, so they're dropped)."""
    name = ss.get("new-member", "").replace(",", " ").strip()
    if name and name not in payers():
        set_members([*payers()[1:], name])
    ss["new-member"] = ""


def members_box() -> None:
    """Who might have paid. Receipts are tagged with these names."""
    with st.container(border=True, key="members-box"):
        st.markdown("**Who's in on this tally?**")
        st.caption("Add everyone who might've paid for something. You'll tag each receipt with one of them.")
        c = st.columns([3, 1], vertical_alignment="bottom")
        c[0].text_input("Name", key="new-member", placeholder="e.g. Jamie Lee", label_visibility="collapsed",
                        on_change=add_member)
        c[1].button("Add member", icon=":material/add:", key="add-member", on_click=add_member, width="stretch")
        names = payers()[1:]
        with st.container(horizontal=True, key="member-chips"):
            for n, name in enumerate(names):
                st.button(name, icon=":material/close:", key=f"rm-member-{n}", help=f"Remove {name}",
                          on_click=set_members, args=([x for x in names if x != name],))


def show() -> None:
    st.header("Who's in?" if ss.receipts else "Start a new event")
    with st.container(key="mascot-empty"):
        st.image(str(ART / "mascot-empty.png"), width=150)
    with st.container(border=True, key="event-box"):
        st.markdown("**What's the event?**")
        c = st.columns([3, 2, 1])
        locked = bool(ss.receipts)  # receipts carry the event id, so name and date stay put
        name = c[0].text_input("Event name", ss.event["name"], key="start-name", disabled=locked)
        d = c[1].date_input("Date", ss.event["date"], key="start-date", disabled=locked)
        people = int(c[2].number_input("Attendees", min_value=1, value=ss.event["attendees"], key="start-people"))
    members_box()
    ready = bool(payers()[1:])
    if not ready:
        st.caption(":red[Add at least one member to keep going.]")
    if st.button("Continue to receipts →", type="primary", disabled=not ready, key="start-go"):
        ss.event = {**ss.event, "name": name, "date": d, "attendees": people, "set_up": True,
                    "event_id": ss.event["event_id"] if locked else event_id_for(name, d)}
        st.rerun()
