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
from ui.common import PAST, STEPS, mascot_uri, ss, usd
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


def add_club(prefix: str) -> None:
    """Add club callback: the form's name (and starting balance) becomes a club, opened on a blank event."""
    name, start = ss.get(f"{prefix}-name", ""), ss.get(f"{prefix}-start")
    if not name.strip():
        return
    ss.club_added = prefix == "new-club"  # the pop-up closes itself on the next run (see new_club_dialog)
    ss.setdefault("event", dict(DEFAULT_EVENT))
    save_session()
    club.add(name, start, ss.pop(f"{prefix}-crew", []))
    ss.club_picked = True
    start_new_event()
    go_home()


def add_to_crew(prefix: str) -> None:
    """Enter / Add callback: the typed name waits in the form until the club is added."""
    name = ss.get(f"{prefix}-who", "").replace(",", " ").strip()
    ss[f"{prefix}-who"] = ""
    crew = ss.setdefault(f"{prefix}-crew", [])
    if name and name not in crew:
        crew.append(name)


def club_form(prefix: str, primary: bool = True) -> None:
    """Name, starting balance and (optional) members for a new club, with its Add button."""
    st.text_input("Club name", key=f"{prefix}-name", placeholder="e.g. Sunrise Hiking Club")
    st.number_input("Money in the bank right now ($)", value=None, step=10.0, format="%.2f", placeholder="0.00",
                    key=f"{prefix}-start", help="What the club has before this year's first event. "
                    "Not sure yet? Leave it blank and add it later in Club settings.")
    st.text_input("Who's in? (optional)", key=f"{prefix}-who", placeholder="Add someone, e.g. Jamie Lee",
                  on_change=add_to_crew, args=(prefix,))
    crew = ss.get(f"{prefix}-crew", [])
    with st.container(horizontal=True, key=f"{prefix}-chips"):
        for n, name in enumerate(crew):
            st.button(name, icon=":material/close:", icon_position="right", key=f"club-rm-{prefix}-{n}",
                      help=f"Take {name} off", on_click=crew.remove, args=(name,))
    club.chip_style(f"club-rm-{prefix}", crew)
    st.button("Add club", icon=":material/add:", key=f"{prefix}-add", type="primary" if primary else "secondary",
              width="stretch", on_click=add_club, args=(prefix,))


@st.dialog("Start a new club", width="medium", on_dismiss=lambda: ss.update(new_club=False))
def new_club_dialog() -> None:
    if ss.pop("club_added", False):  # a dialog only closes when its own code reruns the app
        ss.new_club = False
        st.rerun()
    art, form = st.columns([2, 3], gap="medium")
    art.html(f'<div class="tly-newclub"><p>New club</p><b>Let\'s set up your club!</b>'
             f'<img src="{mascot_uri("tally-party.png")}" alt=""></div>')
    with form:
        club_form("new-club")


def delete_club(cid: str) -> None:
    """Delete club callback: the club, its saved events, and the screen. Opens the next club (or the first-club page)."""
    ss.club_deleted = True  # the pop-up closes itself on the next run
    for e in session_store.past_events(PAST):
        if e["club"] == cid or (e["club"] is None and club.owns(e)):
            session_store.clear(e["path"])
    left = club.remove(cid)
    ss.event = dict(DEFAULT_EVENT)
    ss.club_picked = left is not None
    still_open = [e for e in session_store.past_events(PAST) if club.owns(e) and not e["finished"]] if left else []
    if still_open:
        open_past(still_open[0]["path"])
    else:
        start_new_event()
    go_home()


@st.dialog("Delete this club?", on_dismiss=lambda: ss.update(confirm_club_delete=False))
def confirm_club_delete() -> None:
    if ss.pop("club_deleted", False):
        ss.confirm_club_delete = False
        st.rerun()
    me, cid = club.load(), club.current()
    n = sum(1 for e in session_store.past_events(PAST) if club.owns(e))
    st.html(f'<img class="tly-dialog-tally" src="{mascot_uri("tally-trash.png")}" alt="">'
            f'<div class="tly-confirm">{badge(me["name"], "big")}<b class="tly-pick-name">{html.escape(me["name"])}</b></div>')
    events = f"its {n} saved event{'s' if n != 1 else ''}, " if n else ""
    st.markdown(f'<p class="tly-confirm-note"><b style="color: var(--tly-berry)">This can\'t be undone!</b> '
                f"The club, {events}members and settings go away for good.<br>"
                "<small>What you already pushed stays in your Google Sheet.</small></p>", unsafe_allow_html=True)
    c = st.columns(2)
    if c[0].button("Keep it", key="club-delete-no", width="stretch"):
        ss.confirm_club_delete = False
        st.rerun()
    c[1].button("Yes, delete it", type="primary", key="club-delete-yes", width="stretch", on_click=delete_club, args=(cid,))


def go_home() -> None:
    """Club home. The event's step is remembered for the sidebar, which shows a fresh step list here."""
    ss.last_step = ss.get("step") or ss.get("last_step") or STEPS[0]
    ss.view = "club"
    ss["club-pop"] = False  # close the club menu


def menu() -> None:
    """Top of the sidebar: the open club and its balance. Opens Club home, other clubs, New club."""
    me = club.load()
    money = balance(year_events())
    sub = "Club home" + (f" · {usd(money)}" if money is not None else "")
    with st.sidebar.container(key="club-menu"), st.popover(me["name"], width="stretch", key="club-pop", on_change="rerun"):
        st.button("Club home", icon=":material/home:", key="club-home", width="stretch", on_click=go_home)
        st.markdown('<p class="tly-menu-label">Your clubs</p>', unsafe_allow_html=True)
        have = club.clubs()
        with st.container(key="club-list"):
            for cid, c in have.items():
                here = cid == club.current()
                st.button(c["name"], key=f"club-pick-{cid}", width="stretch", disabled=here,
                          icon=":material/check_circle:" if here else None, icon_position="right",
                          on_click=switch, args=(cid,))
        st.button("New club", icon=":material/add:", key="club-menu-new", width="stretch",
                  on_click=lambda: ss.update({"new_club": True, "club-pop": False}))
    # The button shows the club's initials in a badge and the balance under the name (style.css);
    # each club in the list gets its own colored initials.
    rows = "".join(f'.st-key-club-pick-{cid} button p::before {{ content: "{club.initials(c["name"]) or "?"}"; '
                   f"background: {club.AVATARS[n % len(club.AVATARS)]}; }}" for n, (cid, c) in enumerate(have.items()))
    st.html(f'<style>.st-key-club-menu [data-testid="stPopoverButton"] p::before {{ content: "{club.initials(me["name"])}"; }}'
            f' .st-key-club-menu [data-testid="stPopoverButton"] p::after {{ content: "{sub}"; }} {rows}</style>')
    if ss.get("new_club"):
        new_club_dialog()
    if ss.get("confirm_club_delete"):
        confirm_club_delete()


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
        st.markdown("**Add a club**" if have else "**Your club**")
        club_form("club-first", primary=not have)
