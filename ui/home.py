"""The club comes first: the club menu at the top of the sidebar, the Club home page (balance,
this year's events, members, settings) and the "Which club?" page when there's more than one."""
from __future__ import annotations

import html
from datetime import date
from decimal import Decimal

import streamlit as st

from treasurer import session_store
from treasurer.ledger_view import school_year
from ui import club, connect
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


def members_card() -> None:
    names = club.load()["members"]
    with st.container(border=True, key="home-members"):
        st.markdown(f"**Members ({len(names)})**")
        st.caption("New events start with everyone here.")
        c = st.columns([3, 1], vertical_alignment="bottom")
        c[0].text_input("Name", key="club-new", placeholder="e.g. Jamie Lee", label_visibility="collapsed",
                        on_change=club.add_member, args=("club-new",))
        c[1].button("Add", icon=":material/add:", key="club-add", width="stretch", on_click=club.add_member,
                    args=("club-new",))
        with st.container(horizontal=True, key="club-chips"):
            for n, name in enumerate(names):
                st.button(name, icon=":material/close:", icon_position="right", key=f"club-rm-{n}",
                          help=f"Remove {name} from the club", on_click=club.save,
                          kwargs={"members": [x for x in names if x != name]})
        club.chip_style("club-rm", names)


def save_from(field: str, key: str) -> None:
    """Edit callback: save one club setting (a blank name keeps the old one)."""
    value = ss[key].strip() if isinstance(ss[key], str) else ss[key]
    if value != "":
        club.save(**{field: int(value) if field == "target" else value})


def settings_card() -> None:
    me = club.load()
    start = "not set" if me["start_balance"] is None else usd(Decimal(str(me["start_balance"])))
    books = "Google Sheets" if connect.linked() else "this computer"
    with st.container(border=True, key="home-settings"):
        st.markdown("**Club settings**")
        st.markdown(f'<p class="tly-home-line">Starting balance <b>{start}</b> · Profit target <b>{me["target"]}%</b>'
                    f" · Books go to <b>{books}</b></p>", unsafe_allow_html=True)
        with st.popover("Edit", icon=":material/edit:"):
            # Keys carry the saved value, so a change made elsewhere (or another club) redraws them fresh.
            k = f"{club.current()}-{me['name']}-{me['start_balance']}-{me['target']}"
            st.text_input("Club name", me["name"], key=f"club-name-{k}", on_change=save_from, args=("name", f"club-name-{k}"))
            st.number_input("Starting balance this school year ($)", value=me["start_balance"], step=10.0, format="%.2f",
                            placeholder="0.00", key=f"club-start-{k}", on_change=save_from,
                            args=("start_balance", f"club-start-{k}"),
                            help="What the club had before this year's first event. The General Ledger starts from it.")
            st.number_input("Profit target (%)", min_value=0, max_value=100, value=int(me["target"]), key=f"club-target-{k}",
                            on_change=save_from, args=("target", f"club-target-{k}"),
                            help="The Summary shows if an event hit it.")
            label = "Google Sheets connected" if connect.linked() else "Connect Google Sheets"
            if st.button(label, icon=":material/table_chart:", key="open-connect", width="stretch"):
                connect.dialog()


def events_table(events: list[dict]) -> str:
    if not events:
        return '<p class="tly-home-line">No events this school year yet. Hit New event to start one!</p>'
    status = {True: ("ok", "Finished"), False: ("wait", "In progress")}
    rows = "".join(
        f'<tr><td>{html.escape(e["name"])}</td><td>{date.fromisoformat(str(e["date"])[:10]):%b %d}</td>'
        '<td><span class="tly-status {}">{}</span></td>'.format(*status[e["finished"]]) +
        f'<td class="num{" neg" if e["net"] < 0 else ""}">{usd(e["net"])}</td></tr>' for e in events)
    return ('<table class="tly-table"><thead><tr><th>Event</th><th>Date</th><th>Status</th><th class="num">Net</th>'
            f"</tr></thead><tbody>{rows}</tbody></table>")


def show() -> None:
    """Club home: the club's name, its money this year, its members and its settings."""
    me = club.load()
    events = year_events()
    money = balance(events)
    st.html(f'<div class="tly-home-head">{badge(me["name"], "huge")}<h1>{html.escape(me["name"])}</h1></div>')
    left, right = st.columns([1.15, 1], gap="medium")
    with left.container(border=True, key="home-money"):
        st.markdown("**Club balance**")
        finished = sum(e["finished"] for e in events)
        if money is None:
            st.caption("Type what the club had before this year's first event, and Tally keeps the balance from there.")
            begin = st.number_input("Starting balance this school year ($)", value=None, step=10.0, format="%.2f",
                                    placeholder="0.00", key="home-start")
            if begin is not None:
                club.save(start_balance=begin)
                st.rerun()
        else:
            st.html(f'<p class="tly-home-money{" neg" if money < 0 else ""}">{usd(money)}</p>'
                    f'<p class="tly-home-line">Started the year at {usd(Decimal(str(me["start_balance"])))} · '
                    f'{finished} event{"s" if finished != 1 else ""} finished</p>')
        st.html(events_table(events))
    with right:
        members_card()
        settings_card()
