"""The club comes first: the club menu at the top of the sidebar, switching and adding clubs, the
club's balance, and the "Which club?" page when there's more than one. The page itself is club_home.py."""
from __future__ import annotations

import html
from datetime import date
from decimal import Decimal

import streamlit as st

from treasurer import session_store
from treasurer.ledger_view import school_year
from ui import club
from ui.common import PAST, ss, usd
from ui.sidebar import DEFAULT_EVENT, open_past, save_session, start_new_event


def year_events() -> list[dict]:
    """The open club's saved events this school year, newest first, each with its net."""
    year = school_year(date.today())
    events = [e for e in session_store.past_nets(PAST) if club.owns(e) and school_year(e["date"]) == year]
    return sorted(events, key=lambda e: str(e["date"]), reverse=True)


def balance(events: list[dict]) -> Decimal | None:
    """Starting balance plus every event's net this year. None until the starting balance is typed."""
    start = club.load()["start_balance"]
    return None if start is None else Decimal(str(start)) + sum((e["net"] for e in events), Decimal("0"))


def badge(name: str, size: str = "") -> str:
    return f'<span class="tly-club-badge {size}">{html.escape(club.initials(name) or "?")}</span>'


def switch(cid: str) -> None:
    """Open another club: save this event, then open that club's latest unfinished event (or a blank one)."""
    ss.setdefault("event", dict(DEFAULT_EVENT))  # a first visit picks a club before any event exists
    save_session()
    club.set_current(cid)
    ss.club_picked = True
    still_open = [e for e in session_store.past_events(PAST) if club.owns(e) and not e["finished"]]
    if still_open:
        open_past(still_open[0]["path"])
    else:
        start_new_event()
    go_home()


def add_club(key: str) -> None:
    """Add a club callback: the typed name becomes a club, opened on a blank event."""
    name = ss.get(key, "")
    ss[key] = ""
    if not name.strip():
        return
    ss.setdefault("event", dict(DEFAULT_EVENT))
    save_session()
    club.add(name)
    ss.club_picked = True
    start_new_event()
    go_home()


def go_home() -> None:
    """Club home. The step is unpicked (and remembered) so any step click comes back to the event."""
    if ss.get("step"):
        ss.last_step = ss.step
    ss.step = None
    ss.view = "club"
    ss["club-pop"] = False  # close the club menu


def menu() -> None:
    """Top of the sidebar: the open club and its balance. Opens Club home, other clubs, Add a club."""
    me = club.load()
    money = balance(year_events())
    sub = "Club home" + (f" · {usd(money)}" if money is not None else "")
    with st.sidebar.container(key="club-menu"), st.popover(me["name"], width="stretch", key="club-pop", on_change="rerun"):
        st.button("Club home", icon=":material/home:", key="club-home", type="tertiary", on_click=go_home)
        st.markdown('<p class="tly-field-label">Your clubs</p>', unsafe_allow_html=True)
        for cid, c in club.clubs().items():
            here = cid == club.current()
            st.button(c["name"], key=f"club-pick-{cid}", type="tertiary", disabled=here,
                      icon=":material/check:" if here else None, on_click=switch, args=(cid,))
        c = st.columns([2, 1.2], vertical_alignment="bottom")
        c[0].text_input("New club", key="club-menu-new", placeholder="New club name", label_visibility="collapsed",
                        on_change=add_club, args=("club-menu-new",))
        c[1].button("Add", icon=":material/add:", key="club-menu-add", width="stretch", on_click=add_club,
                    args=("club-menu-new",))
    # The button shows the club's initials in a badge and the balance under the name (style.css).
    st.html(f'<style>.st-key-club-menu [data-testid="stPopoverButton"] p::before {{ content: "{club.initials(me["name"])}"; }}'
            f' .st-key-club-menu [data-testid="stPopoverButton"] p::after {{ content: "{sub}"; }}</style>')


def needs_picking() -> bool:
    """No club yet, or more than one and this tab hasn't picked (Kevin: one club never sees it)."""
    return not club.clubs() or (len(club.clubs()) > 1 and not ss.get("club_picked"))


def picker() -> None:
    """Which club are you doing the books for? One card per club, then Add a club."""
    have = club.clubs()
    st.header("Which club are you doing the books for?" if have else "What's your club called?")
    cols = st.columns(3)
    for n, (cid, c) in enumerate(have.items()):
        with cols[n % 3].container(border=True, key=f"pick-club-{cid}"):
            st.html(f'{badge(c["name"], "big")}<p class="tly-pick-name">{html.escape(c["name"])}</p>'
                    f'<p class="tly-pick-sub">{len(c["members"])} member{"s" if len(c["members"]) != 1 else ""}</p>')
            st.button(f"Open {c['name']}", key=f"open-club-{cid}", on_click=switch, args=(cid,), width="stretch",
                      type="primary" if cid == club.current() else "secondary")
    with cols[len(have) % 3].container(border=True, key="pick-club-new"):
        st.markdown("**Add a club**" if have else "**Your club's name**")
        st.text_input("Club name", key="club-first-name", placeholder="e.g. Sunrise Hiking Club",
                      label_visibility="collapsed", on_change=add_club, args=("club-first-name",))
        st.button("Add club", icon=":material/add:", key="club-first-add", type="primary" if not have else "secondary",
                  width="stretch", on_click=add_club, args=("club-first-name",))
