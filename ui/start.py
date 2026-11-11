"""Step 0 of a new event: name it, date it, and say who's in. Upload opens once someone is."""
from __future__ import annotations

import html

import streamlit as st

from treasurer.reaction import react
from ui import club
from ui.common import mascot_uri, payers, ss
from ui.sidebar import event_id_for
from ui.tickets import ticket


def needed() -> bool:
    """A new event that isn't set up yet, or Edit was clicked. Older saved events with receipts
    (from before this page existed) have no set_up flag and skip it."""
    return ss.event.get("set_up") is False or (not ss.receipts and "set_up" not in ss.event)


def reopen() -> None:
    ss.event = {**ss.event, "set_up": False}


def set_members(names: list[str]) -> None:
    ss.event = {**ss.event, "members": ", ".join(names)}


def add_member() -> None:
    """Button and Enter callback: the typed name joins the club list and this event."""
    name = club.add_member("new-member")
    if name and name not in payers():
        set_members([*payers()[1:], name])


def pick_members(options: list[str]) -> None:
    """Pills callback: who's in, in club-list order."""
    set_members([x for x in options if x in ss.roster])


def members_box() -> None:
    """Who might have paid, picked from the club list. Receipts are tagged with these names."""
    with st.container(border=True, key="members-box"):
        st.markdown("**Who's in on this tally?**")
        st.caption("Tap a name to leave them out. Anyone new gets added to your club list too.")
        c = st.columns([3, 1], vertical_alignment="bottom")
        c[0].text_input("Name", key="new-member", placeholder="e.g. Jamie Lee", label_visibility="collapsed",
                        on_change=add_member)
        c[1].button("Add", icon=":material/add:", key="add-member", on_click=add_member, width="stretch")
        names = payers()[1:]
        members = club.load()["members"]
        options = [*members, *[n for n in names if n not in members]]
        if not options:
            return
        ss.roster = names  # the widget shows this event's members, even right after an Add
        st.pills("Who's in", options, selection_mode="multi", key="roster", label_visibility="collapsed",
                 on_change=pick_members, args=(options,))


@st.cache_data(show_spinner=False, max_entries=200)
def reaction(name: str) -> str:
    """Once per name: Claude's line (or the canned one) doesn't change on reruns."""
    return react(name)


def preview(name: str, d, people: int, names: list[str]) -> str:
    """A: the sidebar ticket, big and tilted, filling in as you type. Tally reacts to the name."""
    named = name.strip() and name.strip() != "New event"
    say = reaction(name.strip()) if named else "Name your event!"
    dots = "".join(f'<span style="background:{club.AVATARS[n % len(club.AVATARS)]}">{html.escape(club.initials(x))}</span>'
                   for n, x in enumerate(names[:6]))
    t = ticket(d, name.strip() or "New event", 0, ss.event.get("color")).replace(
        "<small>0 receipts</small>", f'<small>{people} people · 0 receipts</small><div class="who">{dots}</div>')
    return (f'<div class="tly-live"><div class="bubble">{html.escape(say)}</div>'
            f'<img src="{mascot_uri("tally-hello.png")}" alt="">{t}'
            '<p>This is the ticket that lands in your sidebar.</p></div>')


def show() -> None:
    st.header("Who's in?" if ss.receipts else "Start a new event")
    st.markdown('<p class="tly-start-sub">Fill it in and watch your ticket print!</p>', unsafe_allow_html=True)
    left, right = st.columns([1.25, 1], gap="large")
    with left:
        with st.container(border=True, key="event-box"):
            st.markdown("**What's the event?**")
            c = st.columns([3, 2, 1.3])
            locked = bool(ss.receipts)  # receipts carry the event id, so it stays put (name and date can change)
            name = c[0].text_input("Event name", ss.event["name"], key="start-name")
            d = c[1].date_input("Date", ss.event["date"], key="start-date")
            people = int(c[2].number_input("People", min_value=1, value=ss.event["attendees"], key="start-people"))
        members_box()
        names = payers()[1:]
        if not names:
            st.caption(":red[Add at least one member to keep going.]")
        if st.button("Continue to receipts →", type="primary", disabled=not names, key="start-go"):
            ss.event = {**ss.event, "name": name, "date": d, "attendees": people, "set_up": True,
                        "event_id": ss.event["event_id"] if locked else event_id_for(name, d)}
            st.rerun()
    right.html(preview(name, d, people, names))
