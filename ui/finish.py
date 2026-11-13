"""F2: the finish page. Close out ends here with the recap, the money, the club's balance and
what to do next. Also the Finish event button at the bottom of Close out, and the open items
(still owed, no payer, not pushed) both of them list honestly. Finishing never blocks."""
from __future__ import annotations

import html
import random
from datetime import date
from decimal import Decimal

import streamlit as st

from treasurer import closeout as co
from treasurer import session_store
from treasurer.ledger_view import school_year
from treasurer.models import Status
from treasurer.photo_pdf import receipts_pdf
from treasurer.post import TX_FIELDS, event_totals
from treasurer.reimburse import totals_by_payer
from treasurer.sheets import EventInfo, local_transactions, local_views
from treasurer.xlsx_export import book_xlsx
from ui import club, done_card
from ui.common import dec, get_sink, mascot_uri, past, saved_reimbursements, ss, usd
from ui.home import go_home
from ui.sidebar import save_session, start_new_event

FIX = {"2. Review": "Fix in Review", "3. Summary": "Go push", "4. Close out": "Pay back"}


def open_items(lines: list) -> list[tuple[str, str]]:
    """What's still not done, each with the step that fixes it."""
    items = []
    owing = [x for x in lines if x.owed > 0 and x.payer != "(no payer)"]
    if owing:
        who = "1 person" if len(owing) == 1 else f"{len(owing)} people"
        items.append((f"{who} still owed {usd(sum((x.owed for x in owing), Decimal('0')))}", "4. Close out"))
    rs = list(ss.receipts.values())
    items += [(f"{r.receipt_id} has no payer", "2. Review") for r in rs if r.counts and not (r.payer or "").strip()]
    waiting = [r.receipt_id for r in rs if r.status is Status.DRAFTED]
    if waiting:
        items.append((f"{', '.join(waiting)} not reviewed yet", "2. Review"))
    if not ss.event.get("pushed_at"):
        items.append(("Not pushed to the books yet", "3. Summary"))
    elif ss.event.get("pushed_sig") != done_card.fingerprint():
        items.append((f"Changes since {ss.event['pushed_at']} aren't in the books yet", "3. Summary"))
    return items


REOPEN_HELP = "Back to Close out. It leaves Past events until you finish again."


def payback_lines(sink, event: EventInfo) -> list:
    done = [r for r in ss.receipts.values() if r.counts]
    paybacks = [p for p in saved_reimbursements(sink) if str(p["event_id"]) == event.event_id]
    return co.payer_summary(done, totals_by_payer(paybacks, event.event_id))


def set_finished(done: bool, step: str = "4. Close out", late: bool = False) -> None:
    """Button callback: finish (or reopen) the event and save it, so Past events shows it right away.
    late: reopened to add a missed receipt, so every step shows the way back to the finish."""
    if done and ss.event.get("pushed_at"):  # paybacks only save their own row: the sheet's Receipts tab catches up here
        try:
            get_sink()[0].refresh_receipts()
        except Exception as e:
            ss.finish_note = f"Finished, but the sheet's Receipts tab didn't update ({e}). Push again on Summary to redraw it."
    ss.event = {**ss.event, "finished": done, "late": late}
    ss.pop("last_draft", None)  # "Done! I read all 14" is old news on a reopened Upload
    ss.revisit = False  # just finished: the next step is Club home, not Reopen
    ss.confetti = done  # once, right after Finish event: not on every visit to the page
    ss.step = step
    save_session()


def next_event() -> None:
    save_session()
    start_new_event()
    ss.step = "1. Upload"


def finish_button(lines: list) -> None:
    """Bottom of Close out, pinned to the bottom of the screen (like Upload's), so it's found without scrolling."""
    items = open_items(lines)
    note = ("Everything's wrapped up!" if not items else
            "1 thing's still open, but you can finish anyway! It stays listed on the event." if len(items) == 1 else
            f"{len(items)} things are still open, but you can finish anyway! They stay listed on the event.")
    with st.container(key="finish-next"), st.container(border=True, key="finish-row"):
        # Message on the left, button on the right: the same order as the other "what's next" boxes.
        c = st.columns([4, 1.3], vertical_alignment="center")
        c[0].markdown(f'<p class="tly-done-title">Ready to finish?</p><p class="tly-done-sub">{html.escape(note)}</p>',
                      unsafe_allow_html=True)
        c[1].button("Finish event", type="primary", icon=":material/check:", icon_position="right", key="finish-event",
                    on_click=set_finished, args=(True,), width="stretch")


def club_balance(event: EventInfo, net: Decimal) -> Decimal | None:
    """Starting balance plus every saved event's net this school year (this one live). None
    when the starting balance was never set: a made-up number would mislead."""
    if event.start_balance is None:
        return None
    year = school_year(event.date)
    others = [e["net"] for e in session_store.past_nets(past())
              if club.owns(e) and e["finished"] and e["event_id"] != event.event_id and school_year(e["date"]) == year]
    return event.start_balance + sum(others, Decimal("0")) + net


def confetti() -> str:
    """Paper bits in the app's colors falling over the page (CSS only, ignores clicks, gone in ~4s)."""
    rng = random.Random(7)
    colors = ["#1C5C36", "#3F8A5A", "#F7BE3F", "#C44536", "#8FB38A", "#6B4E8A"]
    bits = "".join(f'<i style="left:{rng.uniform(0, 100):.1f}%;background:{rng.choice(colors)};'
                   f'--d:{rng.uniform(2.2, 3.8):.2f}s;--w:{rng.uniform(0.3, 1.2):.2f}s;--r:{rng.choice([-1, 1]) * 540}deg"></i>'
                   for _ in range(90))
    return f'<div class="tly-confetti" aria-hidden="true">{bits}</div>'


def tiles(t: dict, balance: Decimal | None) -> str:
    left = t["net"]
    cells = [("Money in", usd(t["income"]), ""), ("Money out", usd(t["expenses"]), ""),
             ("Left over", usd(left), "good" if left >= 0 else "bad")]
    if balance is None:
        cells.append(("Club balance now", "Set your starting balance", "dark unset"))
    else:
        cells.append(("Club balance now", usd(balance), "dark bad" if balance < 0 else "dark"))
    return '<div class="tly-tiles">' + "".join(
        f'<div class="tile {cls}"><small>{label}</small><b>{html.escape(value)}</b></div>'
        for label, value, cls in cells) + "</div>"


def show(event: EventInfo) -> None:
    sink, err = get_sink()
    if err:
        st.error(err)
    done = [r for r in ss.receipts.values() if r.counts]
    lines = payback_lines(sink, event)
    items = open_items(lines)
    t = event_totals(done, {k: dec(v) for k, v in ss.income.items()})
    left_out = sum(1 for r in ss.receipts.values() if r.status is Status.REJECTED)
    count = f"{len(done)} receipt{'s' if len(done) != 1 else ''}" + (f" ({left_out} left out)" if left_out else "")
    paid = "everyone paid back" if not any(x.owed > 0 for x in lines) else "paybacks still open"
    # Last school year's books are closed: a late receipt would change a year that's already reported.
    # 60 days of grace, so a July event can still take a receipt found in August.
    locked = school_year(event.date) != school_year(date.today()) and (date.today() - event.date).days > 60
    if ss.get("finish_note"):
        st.warning(ss.pop("finish_note"))
    with st.container(border=True, key="finish-page"):
        st.html(f'<div class="tly-finish"><img src="{mascot_uri("tally-flag.png")}" alt="">'
                f'<h2>{html.escape(event.name)} is closed out!</h2>'
                f'<p>{event.date:%b} {event.date.day}, {event.date.year} · {count} · {paid}</p>'
                f'{tiles(t, club_balance(event, t["net"]))}</div>')
        if items:
            with st.container(key="open-items"):
                st.markdown('<p class="tly-open-title">Still open</p>', unsafe_allow_html=True)
                for n, (text, step) in enumerate(items):
                    row = st.columns([3, 1.4], vertical_alignment="center")
                    row[0].markdown(f'<p class="tly-open-item"><i class="tly-warn">!</i>{html.escape(text)}</p>',
                                   unsafe_allow_html=True)
                    row[1].button(FIX[step], key=f"fix-{n}", icon=":material/arrow_forward:", width="stretch",
                                  icon_position="right", on_click=set_finished, args=(False, step), disabled=locked)
        with st.container(horizontal=True, horizontal_alignment="center", key="finish-buttons"):
            # Back from Past events it's usually to change something, so Reopen leads. Right after finishing, home does.
            lead = bool(ss.get("revisit")) and not locked
            if lead:
                st.button("Reopen this event", key="reopen-event", type="primary", icon=":material/undo:",
                          on_click=set_finished, args=(False,), help=REOPEN_HELP)
            st.button("Back to club home", type="secondary" if lead else "primary", key="to-home", icon=":material/home:",
                      on_click=go_home)
            st.button("Start the next event", key="next-event", on_click=next_event)
            if not locked:
                st.button("Add a missed receipt", key="add-missed", icon=":material/add:", on_click=set_finished,
                          args=(False, "1. Upload", True))
        # The downloads sit a row lower and quieter, so the two ways on don't compete with them.
        with st.container(horizontal=True, horizontal_alignment="center", key="finish-downloads"):
            ledger = getattr(getattr(sink, "ledger_book", None), "url", None)
            if ledger:
                st.link_button("Open General Ledger", ledger, icon=":material/arrow_outward:", icon_position="right",
                               type="tertiary")
            else:
                income = {k: dec(v) for k, v in ss.income.items()}
                receipts = list(ss.receipts.values())
                views = local_views(receipts, event, income, saved_reimbursements(sink))
                st.download_button("Download the whole book (Excel)", key="dl-xlsx-finish", on_click="ignore", type="tertiary",
                                   icon=":material/download:",
                                   data=lambda: book_xlsx(views, local_transactions(receipts), TX_FIELDS),
                                   file_name=f"{event.event_id}_books.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            owed = {x.payer: x.owed for x in lines}
            state = {r.receipt_id: ("Not yet" if owed.get(r.payer, 0) > 0 else "Yes") if r.payer else "" for r in done}
            images = ss.images
            st.download_button("Download receipt photos", key="dl-photos-finish", mime="application/pdf", on_click="ignore",
                               type="tertiary", icon=":material/download:",
                               file_name=f"{event.event_id}_receipt_photos.pdf", data=lambda: receipts_pdf(done, images, state))
    if locked:
        st.caption(f"Locked: this event is from the {school_year(event.date).replace('-', '–')} school year, "
                   "so it can't be reopened or take new receipts.")
    elif not lead:
        st.button("Reopen this event", key="reopen-event", type="tertiary", icon=":material/undo:", on_click=set_finished,
                  args=(False,), help=REOPEN_HELP)
    if ss.pop("confetti", False):  # last, so it falls once the whole page is built
        st.html(confetti())
