"""The sidebar (under the club menu): New event, the event ticket with the step timeline, Edit event and Past events.
Also saving the session, and opening a past event."""
from __future__ import annotations

import os
import secrets
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

import streamlit as st

from treasurer import session_store
from treasurer.sheets import DEFAULT_SOURCES, EventInfo
from ui import club
from ui.common import STEPS, out, past, reviewed, ss, step_label, step_status
from ui.tickets import NAMES, PALETTE, next_color, stub, ticket

# A first visit starts from zero: no name, no members. The fake event is one click away on Upload.
DEFAULT_EVENT = {"event_id": "EVT-NEW", "name": "New event", "date": date.today(), "attendees": 30,
                 "members": "", "sources": ", ".join(DEFAULT_SOURCES)}
HOME_URL = os.environ.get("TALLYABLE_HOME_URL", "http://localhost:3000")  # the landing page start.bat serves


def event_id_for(name: str, d: date) -> str:
    """Date + name + a random tail, so two events named "Picnic" never share an id
    (a shared id merged their rows in the sheet and skipped the second one's receipts)."""
    slug = "".join(ch for ch in name.upper() if ch.isalnum())[:12] or "EVENT"
    return f"EVT-{d.isoformat()}-{slug}-{secrets.token_hex(2).upper()}"


def start_new_event() -> None:
    """Clear the screen for the next event. The finished one stays under Past events.
    Income sources carry over; who's in starts as the whole club list."""
    ss.event = {k: v for k, v in ss.event.items() if k not in ("pushed_at", "pushed_sig", "finished")}
    ss.event = {**ss.event, "members": ", ".join(club.load()["members"]), "name": "New event", "date": date.today(), "set_up": False,
                "event_id": event_id_for("New event", date.today()), "color": next_color(ss.event.get("color")),
                "club": club.current()}
    for k in ("receipts", "images", "notes", "failed", "skipped"):
        ss[k] = {}
    ss.edits, ss.drafted_at, ss.review_started, ss.income = 0, None, None, {}
    ss.pop("last_draft", None)
    ss.pop("ticket-color", None)  # the color list shows the new event's color, not the last one's
    ss.started = time.time()
    ss.step = STEPS[0]  # the new event opens on its first step, not where the last one ended
    ss.view = "event"
    session_store.clear(out() / "session.json")
    ss.pop("_saved", None)


def close_confirm() -> None:
    ss.pop("confirm", None)


@st.dialog("Start a new event?", on_dismiss=close_confirm)
def confirm_new_event() -> None:
    """Ask before clearing the screen, so a stray click can't wipe an event in progress.
    Shown while `confirm` is "new", so each button click redraws it until one closes it."""
    n = len(ss.receipts)
    st.markdown(f'<div class="tly-confirm">{ticket(ss.event["date"], ss.event["name"], n, ss.event.get("color"))}</div>',
                unsafe_allow_html=True)
    st.markdown('<p class="tly-confirm-note"><b>Saved to Past events ✓</b> You can reopen it anytime!<br>'
                "<small>Photos you uploaded but haven't drafted yet won't come along.</small></p>", unsafe_allow_html=True)
    c = st.columns(2)
    if c[0].button("Keep going", key="confirm-new-no", width="stretch"):
        close_confirm()
        st.rerun()
    if c[1].button("Yes, start a new one", type="primary", key="confirm-new-yes", width="stretch"):
        close_confirm()
        save_session()
        start_new_event()
        st.rerun()


@st.dialog("Delete this event?", on_dismiss=close_confirm)
def confirm_delete() -> None:
    """Delete the open event for good: its saved file and the screen. The sheet isn't touched."""
    n = len(ss.receipts)
    st.markdown(f'<div class="tly-confirm">{ticket(ss.event["date"], ss.event["name"], n, ss.event.get("color"))}</div>',
                unsafe_allow_html=True)
    pushed = "<br><small>What you already pushed stays in your sheet.</small>" if ss.event.get("pushed_at") else ""
    st.markdown(f'<p class="tly-confirm-note"><b style="color: var(--tly-berry)">This can\'t be undone!</b> '
                f"Its receipts, photos and notes go away for good.{pushed}</p>", unsafe_allow_html=True)
    c = st.columns(2)
    if c[0].button("Keep it", key="delete-no", width="stretch"):
        close_confirm()
        st.rerun()
    if c[1].button("Yes, delete it", type="primary", key="delete-yes", width="stretch"):
        close_confirm()
        session_store.clear(past() / f"{ss.event['event_id']}.json")
        start_new_event()
        st.rerun()


def save_session() -> None:
    """Write the session to disk when it changed since the last save. An event counts once
    it's set up, even before any receipts, so starting a new one never loses it."""
    if not ss.receipts and not ss.event.get("set_up"):
        return
    # On Club home the event's step radio isn't drawn, so its step lives in last_step.
    state = {k: ss[k] if k != "step" else ss.get("step") or ss.get("last_step") or STEPS[0] for k in session_store.SAVED_KEYS}
    text = session_store.dump(state)
    if text == ss.get("_saved"):
        return
    photos = (ss.event["event_id"], list(ss.images))  # photos rarely change: rewrite them only when they do
    fresh = photos != ss.get("_saved_photos")
    session_store.save(out() / "session.json", state, photos=fresh)
    session_store.save(past() / f"{ss.event['event_id']}.json", state, photos=fresh)
    ss._saved, ss._saved_photos = text, photos


def open_past(path: Path) -> None:
    """Button callback: switch to a saved event. The current one is already saved."""
    saved = session_store.load(path)
    if not saved:
        ss.past_error = f"Could not open {path.name}."
        return
    ss.update(saved)
    ss.pop("ticket-color", None)
    ss.failed, ss.skipped, ss.joins = {}, {}, {}
    ss.pop("last_draft", None)
    ss.pop("_saved", None)
    ss.pop("_saved_photos", None)
    ss.step = "4. Close out" if ss.receipts else STEPS[0]
    ss.view = "event"


def reopen() -> None:
    """Button callback: un-finish this event and go back to Close out."""
    ss.event = {**ss.event, "finished": False}
    ss.step = "4. Close out"
    ss.view = "event"


def past_events_box() -> None:
    """Past events in two tabs: Still open (full tickets) and Finished (torn-off stubs)."""
    here = ss.event["event_id"]  # the current event joins once it's finished, with Reopen
    saved = [e for e in session_store.past_events(past())
            if club.owns(e) and (e["event_id"] != here or ss.event.get("finished"))]
    if not saved:
        return
    groups = {"open": [e for e in saved if not e.get("finished")], "done": [e for e in saved if e.get("finished")]}
    with st.sidebar.expander(f"Past events ({len(saved)})", icon=":material/confirmation_number:"):
        names = {"open": f"Still open · {len(groups['open'])}", "done": f"Finished · {len(groups['done'])}"}
        tab = st.segmented_control("Show", list(names), format_func=names.get, key="past-tab", width="stretch",
                                   label_visibility="collapsed", default="open" if groups["open"] else "done")
        shown = groups[tab or "open"]
        if not shown:
            st.caption("Nothing still open: every past event is finished!" if tab != "done" else
                       "No finished events yet. Hit Finish event on Close out to tear off a stub!")
        cols = st.columns(2) if tab == "done" else None
        for n, e in enumerate(shown):
            d = e["date"] if isinstance(e["date"], date) else date.fromisoformat(str(e["date"])[:10])
            slot = cols[n % 2] if cols else st.container()
            art = stub(d, e["name"], e.get("color")) if cols else ticket(d, e["name"], e["receipts"], e.get("color"))
            with slot.container(key=f"past-{n}"):
                st.markdown(art, unsafe_allow_html=True)
                # The whole ticket or stub is the button: an invisible one laid over it (finish.css).
                here_now = e["event_id"] == here
                st.button("Reopen", key=f"open-past-{n}", on_click=reopen if here_now else open_past,
                          args=() if here_now else (e["path"],), help=f"Reopen {e['name']}")


def leave_home() -> None:
    """A step clicked on Club home: open the event on that step."""
    ss.step = ss.pop("step-home")
    ss.view = "event"


def stepper_css(current: str) -> None:
    """Timeline stepper in the sidebar (prototype B). The radio's labels stay fixed so the widget
    keeps its state; this run's CSS adds each step's status line, the checks, and how far the
    green line has filled (down to this step, plus Review's progress)."""
    done, _ = step_status()
    rs, checked = list(ss.receipts.values()), reviewed()
    sub = {"1. Upload": f"{len(rs)} receipt{'s' if len(rs) != 1 else ''} in" if rs else "Photos, screenshots, PDFs",
           "2. Review": f"{checked} of {len(rs)} checked" if rs else "Check each one",
           "3. Summary": "In the books" if done["3. Summary"] else "Add income, push",
           "4. Close out": "Finished!" if done["4. Close out"] else "Who's owed, report"}
    frac = STEPS.index(current) / (len(STEPS) - 1)
    if current == "2. Review" and rs:
        frac += checked / len(rs) / (len(STEPS) - 1) * 0.8
    rules = [f'.st-key-steps [role="radiogroup"] {{ --tly-fill: {frac * 100:.1f}%; }}']
    for n, name in enumerate(STEPS, start=1):
        row = f'.st-key-steps [role="radiogroup"] > div:nth-child({n}) label'
        rules.append(f'{row} p::after {{ content: "{sub[name]}"; }}')
        if name != current:
            rules.append(f'{row}::before {{ content: "✓"; background: var(--tly-forest); border-color: var(--tly-forest); '
                         "color: var(--tly-white); }" if done[name] else f'{row}::before {{ content: "{n}"; }}')
            continue
        rules.append(f'{row}::before {{ content: "{n}"; border-color: var(--tly-forest); color: var(--tly-forest); '
                     "box-shadow: var(--tly-ring); }" f" {row} p {{ font-weight: 700; }}")
        if name == "2. Review" and rs:
            pct = checked / len(rs) * 100
            rules.append(f'{row}::after {{ content: ""; position: absolute; left: 52px; right: 12px; bottom: 4px; '
                         f"height: 6px; border-radius: 999px; background: linear-gradient(90deg, var(--tly-sun) {pct:.0f}%, "
                         f"var(--tly-line) {pct:.0f}%); }}")
    st.html("<style>" + "\n".join(rules) + "</style>")


def show() -> tuple[str, EventInfo]:
    """Draw the sidebar. Returns the step to show and the event being closed out."""
    ss.setdefault("event", dict(DEFAULT_EVENT))
    ss.event.setdefault("club", club.current())
    if st.sidebar.button("New event", icon=":material/add:", key="new-event", width="stretch",
                         help="Starts a blank event. This one stays saved under Past events."):
        if ss.event.get("finished") or (not ss.receipts and not ss.event.get("set_up")):  # nothing to lose
            save_session()
            start_new_event()
            st.rerun()
        ss.confirm = "new"
    if ss.get("confirm") == "new":
        confirm_new_event()
    if ss.get("confirm") == "delete":
        confirm_delete()
    event_group = st.sidebar.container(border=True, key="event-group")  # ticket, steps and Edit event in one box
    event_card = event_group.empty()  # filled below, once the event fields are read
    steps_slot = event_group.container()  # the stepper sits under the ticket; Edit event goes below it
    with event_group.container(key="edit-event"), st.expander("Edit event", icon=":material/edit:"):
        locked = bool(ss.event.get("pushed_at"))  # the sheet's tabs are named after the event
        name = st.text_input("Event name", ss.event["name"], disabled=locked)
        d = st.date_input("Event date", ss.event["date"], disabled=locked)
        attendees = int(st.number_input("Attendees", min_value=1, value=ss.event["attendees"]))
        # The radio's pick from this click, not the saved color: the label is drawn before the radio
        # runs, so reading the saved color showed the previous pick (Sunflower while Sage was picked).
        current = ss.get("ticket-color") or ss.event.get("color") or NAMES[0]
        st.markdown('<p class="tly-field-label">Ticket color</p>', unsafe_allow_html=True,
                    help="Picked for you so events in a row don't match. Change it anytime!")
        with st.container(key="color-menu"), st.popover(current, width="stretch"), st.container(height=190, border=False):
            color = st.radio("Ticket color", NAMES, index=NAMES.index(current), key="ticket-color",
                             label_visibility="collapsed")
        changed = (name != ss.event["name"] or d != ss.event["date"]) and not ss.receipts  # receipts carry the id
        settings = club.load()
        ss.event.update(target=settings["target"], start_balance=settings["start_balance"], color=color)
        ss.event.update(name=name, date=d, attendees=attendees,
                        event_id=event_id_for(name, d) if changed else ss.event["event_id"])
        if locked:
            st.caption("Name and date are locked once the books are pushed.")
        st.button("Delete event", icon=":material/delete:", key="delete-event", width="stretch",
                  on_click=ss.update, kwargs={"confirm": "delete"})
    start = ss.event.get("start_balance")
    event = EventInfo(ss.event["event_id"], ss.event["name"], ss.event["date"], ss.event["attendees"],
                      start_balance=None if start is None else Decimal(str(start)))
    event_card.markdown(ticket(event.date, event.name, len(ss.receipts), ss.event.get("color")), unsafe_allow_html=True)
    with steps_slot.container(key="steps"):
        if ss.get("view") == "club":
            # A fresh radio with nothing picked, so clicking any step (even the event's current one) opens it.
            # Reusing the event's radio left the browser showing the old pick, and that click did nothing.
            st.radio("Steps", STEPS, index=None, key="step-home", format_func=step_label, on_change=leave_home)
            page = ss.get("last_step") or STEPS[0]
        else:
            page = st.radio("Steps", STEPS, key="step", format_func=step_label)
    stepper_css(page)
    dots = "".join(f".st-key-ticket-color [role=radiogroup] > div:nth-of-type({n}) p::before {{ background: {c}; }}"
                   for n, (c, _) in enumerate(PALETTE.values(), start=1))
    picked = PALETTE[ss.event.get("color") or NAMES[0]][0]
    # No ticket before the first event starts, and none once it's finished: it lives under Past events then.
    blank = ss.event.get("finished") or (ss.get("view") == "club" and not ss.event.get("set_up") and not ss.receipts)
    hide = ".st-key-event-group { display: none; }" if blank else ""
    st.html(f"<style>{dots} .st-key-color-menu button p::before {{ background: {picked}; }} {hide}</style>")
    past_events_box()
    if ss.get("past_error"):
        st.sidebar.error(ss.pop("past_error"))
    return page, event
