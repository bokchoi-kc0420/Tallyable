"""The sidebar: New event, the event ticket with the step timeline, Edit event and Past events.
Also saving the session, and opening a past event."""
from __future__ import annotations

import html
import os
import time
from datetime import date
from pathlib import Path

import streamlit as st

from treasurer import session_store
from treasurer.sheets import DEFAULT_SOURCES, EventInfo
from ui.common import ART, PAST, SESSION_FILE, STEPS, reviewed, ss, step_label, step_status

DEFAULT_EVENT = {"event_id": "EVT-FAKE-01", "name": "Fall Mentor Mixer (FAKE)", "date": date(2026, 11, 14),
                 "attendees": 45, "members": "",  # added on Upload; nobody can be tagged until there is one
                 "sources": ", ".join(DEFAULT_SOURCES)}
HOME_URL = os.environ.get("TALLYABLE_HOME_URL", "http://localhost:3000")  # the landing page start.bat serves


def event_id_for(name: str, d: date) -> str:
    slug = "".join(ch for ch in name.upper() if ch.isalnum())[:12] or "EVENT"
    return f"EVT-{d.isoformat()}-{slug}"


def start_new_event() -> None:
    """Clear the screen for the next event. The finished one stays under Past events.
    Club settings (members, income sources) carry over."""
    ss.event = {**ss.event, "name": "New event", "date": date.today(),
                "event_id": event_id_for("New event", date.today())}
    for k in ("receipts", "images", "notes", "failed"):
        ss[k] = {}
    ss.edits, ss.drafted_at, ss.review_started, ss.income = 0, None, None, {}
    ss.pop("last_draft", None)
    ss.pop("last_push", None)
    ss.started = time.time()
    session_store.clear(SESSION_FILE)


def save_session() -> None:
    """Write the session to disk when it changed since the last save."""
    if not ss.receipts:
        return
    state = {k: ss[k] for k in session_store.SAVED_KEYS}
    text = session_store.dump(state)
    if text == ss.get("_saved"):
        return
    session_store.save(SESSION_FILE, state)
    session_store.save(PAST / f"{ss.event['event_id']}.json", state)
    ss._saved = text


def open_past(path: Path) -> None:
    """Button callback: switch to a saved event. The current one is already saved."""
    saved = session_store.load(path)
    if not saved:
        ss.past_error = f"Could not open {path.name}."
        return
    ss.update(saved)
    ss.failed = {}
    ss.pop("last_draft", None)
    ss.pop("last_push", None)
    ss.pop("_saved", None)
    ss.step = "4. Close out"


def stepper_css(current: str) -> None:
    """Timeline stepper in the sidebar (prototype B). The radio's labels stay fixed so the widget
    keeps its state; this run's CSS adds each step's status line, the checks, and how far the
    green line has filled (down to this step, plus Review's progress)."""
    done, _ = step_status()
    rs, checked = list(ss.receipts.values()), reviewed()
    sub = {"1. Upload": f"{len(rs)} receipt{'s' if len(rs) != 1 else ''} in" if rs else "Photos, screenshots, PDFs",
           "2. Review": f"{checked} of {len(rs)} checked" if rs else "Check each one",
           "3. Summary": "In the books" if done["3. Summary"] else "Add income, push",
           "4. Close out": "Who's owed, report"}
    frac = STEPS.index(current) / (len(STEPS) - 1)
    if current == "2. Review" and rs:
        frac += checked / len(rs) / (len(STEPS) - 1) * 0.8
    rules = [f'.st-key-step [role="radiogroup"] {{ --tly-fill: {frac * 100:.1f}%; }}']
    for n, name in enumerate(STEPS, start=1):
        row = f'.st-key-step [role="radiogroup"] > div:nth-child({n}) label'
        rules.append(f'{row} p::after {{ content: "{sub[name]}"; }}')
        if name != current:
            rules.append(f'{row}::before {{ content: "✓"; background: var(--tly-forest); border-color: var(--tly-forest); '
                         "color: #fff; }" if done[name] else f'{row}::before {{ content: "{n}"; }}')
            continue
        rules.append(f'{row}::before {{ content: "{n}"; border-color: var(--tly-forest); color: var(--tly-forest); '
                     "box-shadow: 0 0 0 4px rgba(247,190,63,.5); }" f" {row} p {{ font-weight: 700; }}")
        if name == "2. Review" and rs:
            pct = checked / len(rs) * 100
            rules.append(f'{row}::after {{ content: ""; position: absolute; left: 52px; right: 12px; bottom: 4px; '
                         f"height: 6px; border-radius: 9px; background: linear-gradient(90deg, var(--tly-sun) {pct:.0f}%, "
                         f"#E6DEC0 {pct:.0f}%); }}")
    st.html("<style>" + "\n".join(rules) + "</style>")


def ticket(d: date, name: str, receipts: int, small: bool = False) -> str:
    """An event as a ticket: a date stub, then the name and receipt count."""
    return (f'<div class="tly-event{" small" if small else ""}"><div class="stub"><span>{d.strftime("%b").upper()}</span>'
            f'<b>{d.day}</b><span>{d.year}</span></div><div class="info"><b>{html.escape(name)}</b>'
            f'<small>{receipts} receipt{"s" if receipts != 1 else ""}</small></div></div>')


def show() -> tuple[str, EventInfo]:
    """Draw the sidebar. Returns the step to show and the event being closed out."""
    ss.setdefault("event", dict(DEFAULT_EVENT))
    st.logo(str(ART / "logo.png"), size="large", link=HOME_URL)
    st.sidebar.caption("Close out a club event: receipts in, checked books out.")
    if st.sidebar.button("New event", icon=":material/add:", key="new-event", type="primary", width="stretch",
                         help="Starts a blank event. This one stays saved under Past events."):
        start_new_event()
        st.rerun()
    event_group = st.sidebar.container(border=True, key="event-group")  # ticket, steps and Edit event in one box
    event_card = event_group.empty()  # filled below, once the event fields are read
    steps_slot = event_group.container()  # the stepper sits under the ticket; Edit event goes below it
    with event_group.container(key="edit-event"), st.expander("Edit event", icon=":material/edit:",
                                                             expanded=not ss.receipts and ss.event == DEFAULT_EVENT):
        locked = bool(ss.receipts)
        name = st.text_input("Event name", ss.event["name"], disabled=locked)
        d = st.date_input("Event date", ss.event["date"], disabled=locked)
        attendees = int(st.number_input("Attendees", min_value=1, value=ss.event["attendees"]))
        cal = st.radio("School calendar", ["Semesters", "Quarters"], horizontal=True,
                       index=0 if ss.event.get("calendar", "semester") == "semester" else 1,
                       help="Your books get one balance sheet per term.")
        target = int(st.number_input("Profit target (%)", min_value=0, max_value=100, value=int(ss.event.get("target", 10)),
                                     help="The margin your club aims for. The Summary shows if an event hit it."))
        changed = name != ss.event["name"] or d != ss.event["date"]
        ss.event.update(calendar="semester" if cal == "Semesters" else "quarter", target=target)
        ss.event.update(name=name, date=d, attendees=attendees,
                        event_id=event_id_for(name, d) if changed else ss.event["event_id"])
        if locked:
            st.caption("Name and date are locked once receipts are drafted.")
    event = EventInfo(ss.event["event_id"], ss.event["name"], ss.event["date"], ss.event["attendees"],
                      calendar=ss.event.get("calendar", "semester"))
    event_card.markdown(ticket(event.date, event.name, len(ss.receipts)), unsafe_allow_html=True)
    page = steps_slot.radio("Steps", STEPS, key="step", format_func=step_label)
    stepper_css(page)
    past = [e for e in session_store.past_events(PAST) if e["event_id"] != ss.event["event_id"]]
    if past:
        with st.sidebar.expander(f"Past events ({len(past)})", icon=":material/history:"):
            for n, e in enumerate(past):
                d = e["date"] if isinstance(e["date"], date) else date.fromisoformat(str(e["date"])[:10])
                with st.container(key=f"past-{n}"):
                    st.markdown(ticket(d, e["name"], e["receipts"], small=True), unsafe_allow_html=True)
                    st.button("Open", key=f"open-past-{n}", on_click=open_past, args=(e["path"],),
                              icon=":material/open_in_new:", type="tertiary",
                              help="Your current event is saved first, so you can come back to it here.")
    if ss.get("past_error"):
        st.sidebar.error(ss.pop("past_error"))
    return page, event
