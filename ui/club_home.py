"""Club home (Kevin's pick C): a split hero with the club's money on the left and the next step on
the right, then this year's event tickets and the crew. Tally has a pose for each part."""
from __future__ import annotations

import html
from datetime import date
from decimal import Decimal

import streamlit as st

from treasurer.ledger_view import school_year
from ui import club, connect
from ui.common import STEPS, mascot_uri, reviewed, ss, usd
from ui.home import badge, balance, year_events
from ui.sidebar import start_new_event
from ui.tickets import PALETTE, _vars


def next_step() -> tuple[str, list[tuple[bool, str]], str, str | None]:
    """What to do next with the open event: title, checklist, button label, and the step the
    button opens (None: start a new event)."""
    ev, rs = ss.event, ss.receipts
    if ev.get("finished") or (not ev.get("set_up") and not rs):
        return ("Start your next event", [(False, "Name it and choose who paid"), (False, "Upload the receipts")],
                "Start an event", None if ev.get("finished") else STEPS[0])
    n, checked, pushed = len(rs), reviewed(), bool(ev.get("pushed_at"))
    items = [(n > 0, f"{n} receipt{'s' if n != 1 else ''} in" if n else "Upload the receipts"),
             (n > 0 and checked == n, "Every receipt checked" if n and checked == n else
              f"Check {n - checked} more receipt{'s' if n - checked != 1 else ''}"),
             (pushed, "Pushed to the books" if pushed else "Push to the books"),
             (False, "Pay everyone back and finish")]
    target = next(step for (done, _), step in zip(items, STEPS, strict=True) if not done)
    return f"Finish {ev['name']}", items, "Keep going", target


def go(step: str | None) -> None:
    """Hero button: open the step (or a fresh event) in the event view."""
    if step is None:
        start_new_event()
        return
    ss.step = step
    ss.view = "event"


def hero(me: dict, events: list[dict]) -> None:
    money = balance(events)
    start = me["start_balance"]
    with st.container(key="home-hero", horizontal=True, gap=None):
        with st.container(key="hero-money"):
            n = len(me["members"])
            amount = usd(money) if money is not None else "$ —"
            # No starting balance yet: it's asked when the club is made, or set later in Club settings.
            sub = "in the club bank" if money is not None else "No starting balance yet (Club settings)"
            up = None if money is None else money - Decimal(str(start))
            delta = ("" if not up else
                     f'<span class="tly-delta{" down" if up < 0 else ""}"><b>{"▲" if up >= 0 else "▼"}</b> '
                     f'{usd(abs(up))} since the year started</span>')
            st.html(f'<div class="tly-hero-id">{badge(me["name"], "mid")}<div><b>{html.escape(me["name"])}</b>'
                    f'<small>{n} member{"s" if n != 1 else ""} · {school_year(date.today()).replace("-", "–")}</small></div></div>'
                    f'<p class="tly-hero-money">{amount}</p><p class="tly-hero-sub">{sub}</p>{delta}'
                    f'<img class="tly-hero-jar" src="{mascot_uri("tally-coin-jar.png")}" alt="">')
        with st.container(key="hero-next"):
            title, items, label, target = next_step()
            checks = "".join(f'<li class="{"done" if done else ""}">{html.escape(text)}</li>' for done, text in items)
            st.html(f'<p class="tly-kick">YOUR NEXT STEP</p><p class="tly-next-title">{html.escape(title)}</p>'
                    f'<ul class="tly-checks">{checks}</ul>'
                    f'<img class="tly-hero-clip" src="{mascot_uri("tally-clipboard.png")}" alt="">')
            st.button(f"{label} →", key="home-go", type="primary", on_click=go, args=(target,))


def ticket_html(e: dict) -> str:
    d = date.fromisoformat(str(e["date"])[:10])
    money = (f'<span class="{"neg" if e["net"] < 0 else "pos"}">{"+" if e["net"] >= 0 else ""}{usd(e["net"])}</span>'
             if e["finished"] else '<span class="open">Open</span>')
    return (f'<div class="tly-event" style="{_vars(e.get("color") or list(PALETTE)[0])}"><div class="stub"><span>'
            f'{d.strftime("%b").upper()}</span><b>{d.day}</b><span>{d.year}</span></div><div class="info">'
            f'<b>{html.escape(e["name"])}</b>{money}</div></div>')


def tickets(events: list[dict]) -> None:
    strip = "".join(ticket_html(e) for e in reversed(events)) or (
        '<p class="tly-home-line">No events this school year yet. Hit New event and your first ticket shows up here!</p>')
    with st.container(border=True, key="home-tickets"):
        st.html(f'<p class="tly-card-title">This year\'s tickets</p><div class="tly-strip">{strip}</div>'
                f'<img class="tly-card-tally" src="{mascot_uri("tally-tickets.png")}" alt="">')


def save_from(field: str, key: str) -> None:
    """Edit callback: save one club setting (a blank name keeps the old one)."""
    value = ss[key].strip() if isinstance(ss[key], str) else ss[key]
    if value != "":
        club.save(**{field: int(value) if field == "target" else value})


def settings(me: dict) -> None:
    """Club settings behind one button: name, starting balance, profit target, Google Sheets, Delete club."""
    with st.popover("Club settings", icon=":material/settings:", key="club-set", on_change="rerun"), st.container(key="club-settings"):
        st.html(f'<div class="tly-set-head">{badge(me["name"], "mid")}<div><b>Club settings</b>'
                f'<small>{html.escape(me["name"])}</small></div></div>')
        # Keys carry the saved value, so a change made elsewhere (or another club) redraws them fresh.
        k = f"{club.current()}-{me['name']}-{me['start_balance']}-{me['target']}"
        st.text_input("Club name", me["name"], key=f"club-name-{k}", on_change=save_from, args=("name", f"club-name-{k}"))
        c = st.columns(2)
        c[0].number_input("Started the year with ($)", value=me["start_balance"], step=10.0, format="%.2f",
                          placeholder="0.00", key=f"club-start-{k}", on_change=save_from, args=("start_balance", f"club-start-{k}"),
                          help="What the club had before this year's first event. The General Ledger starts from it.")
        c[1].number_input("Profit goal (%)", min_value=0, max_value=100, value=int(me["target"]), key=f"club-target-{k}",
                          on_change=save_from, args=("target", f"club-target-{k}"), help="The Summary shows if an event hit it.")
        label = "Google Sheets connected" if connect.linked() else "Connect Google Sheets"
        if st.button(label, icon=":material/table_chart:", key="open-connect", width="stretch"):
            connect.dialog()
        st.button("Delete club", icon=":material/delete:", key="delete-club", width="stretch",
                  on_click=lambda: ss.update({"confirm_club_delete": True, "club-set": False}))


def crew(me: dict) -> None:
    names = me["members"]
    with st.container(border=True, key="home-crew"):
        st.html(f'<p class="tly-card-title">The crew</p>'
                f'<img class="tly-card-tally" src="{mascot_uri("tally-high-five.png")}" alt="">')
        c = st.columns([2.4, 1, 2], vertical_alignment="bottom")
        c[0].text_input("Name", key="club-new", placeholder="Add someone, e.g. Jamie Lee", label_visibility="collapsed",
                        on_change=club.add_member, args=("club-new",))
        c[1].button("Add", icon=":material/add:", key="club-add", width="stretch", on_click=club.add_member,
                    args=("club-new",))
        with st.container(horizontal=True, key="club-chips"):
            for n, name in enumerate(names):
                st.button(name, icon=":material/close:", icon_position="right", key=f"club-rm-{n}",
                          help=f"Remove {name} from the club", on_click=club.save,
                          kwargs={"members": [x for x in names if x != name]})
        club.chip_style("club-rm", names)
        start = "not set" if me["start_balance"] is None else usd(Decimal(str(me["start_balance"])))
        books = ("table", "Google Sheets") if connect.linked() else ("laptop_mac", "This computer")
        facts = [("savings", "Started with", start), ("flag", "Profit goal", f'{me["target"]}%'),
                 (books[0], "Books saved on", books[1])]
        st.html('<div class="tly-facts">' + "".join(
            f'<div><i class="ms">{icon}</i><span><small>{label}</small><b>{value}</b></span></div>'
            for icon, label, value in facts) + "</div>")
        settings(me)


def show() -> None:
    me = club.load()
    events = year_events()
    hero(me, events)
    tickets(events)
    crew(me)
