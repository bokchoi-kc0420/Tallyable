"""S1: the "Books are in!" card at the bottom of Summary after Push, with one clear next step.

It remembers what was pushed (a fingerprint of the receipts and income) so an edit after
Push flips it to "You changed something since 6:02 PM. Push again?"."""
from __future__ import annotations

import hashlib
import html
import json
import time
from decimal import Decimal

import streamlit as st

from treasurer.models import Receipt, Status
from treasurer.post import TX_FIELDS
from treasurer.sheets import EventInfo, local_transactions, local_views
from treasurer.xlsx_export import book_xlsx
from ui.common import go, mascot_uri, md, saved_reimbursements, ss, usd


def fingerprint() -> str:
    """Everything a push writes: the receipts (with their status) and the income."""
    data = {"r": {k: r.model_dump(mode="json") for k, r in ss.receipts.items()}, "i": ss.income}
    return hashlib.sha1(json.dumps(data, sort_keys=True).encode()).hexdigest()


def mark_pushed() -> None:
    """Call right after a push: the card shows from now on, until something changes."""
    ss.event = {**ss.event, "pushed_at": time.strftime("%I:%M %p").lstrip("0"), "pushed_sig": fingerprint()}


def counts_line(receipts: list[Receipt], income: dict[str, Decimal]) -> str:
    """'12 receipts (2 left out) and $500.00 income'."""
    n = sum(1 for r in receipts if r.status is Status.POSTED)
    out = sum(1 for r in receipts if r.status is Status.REJECTED)
    line = f"{n} receipt{'s' if n != 1 else ''}" + (f" ({out} left out)" if out else "")
    return f"{line} and {usd(sum(income.values(), Decimal('0')))} income"


def show(sink, receipts: list[Receipt], event: EventInfo, income: dict[str, Decimal], push) -> None:
    """Draw the card if this event was pushed. `push` re-runs the push for the stale variant."""
    at = ss.event.get("pushed_at")
    if not at:
        return
    if ss.event.get("pushed_sig") != fingerprint():
        with st.container(border=True, key="push-stale"):
            c = st.columns([3.2, 1.4], vertical_alignment="center")
            c[0].markdown(f'<p class="tly-done-title">You changed something since {at}.</p>'
                          '<p class="tly-done-sub">Push again so your books match!</p>', unsafe_allow_html=True)
            if c[1].button("Push again", type="primary", icon=":material/upload:", key="push-again", width="stretch"):
                push()
        return
    on_sheets = sink.label == "Google Sheets"
    title = "Books are in!" if on_sheets else "Your book is ready!"
    where = f"went to your Google Sheet at {at}." if on_sheets else f"are saved on this computer as of {at}."
    with st.container(border=True, key="books-in"):
        art, body = st.columns([1, 5.2], vertical_alignment="center")
        art.html(f'<img class="tly-done-art" src="{mascot_uri("tally-cheer.png")}" alt="">')
        body.markdown(f'<p class="tly-done-title">{title} <span>✓</span></p>'
                      f'<p class="tly-done-sub">{html.escape(counts_line(receipts, income))} {where}</p>',
                      unsafe_allow_html=True)
        with body.container(horizontal=True, key="books-in-buttons"):
            st.button("Next: Close out", type="primary", icon=":material/arrow_forward:", icon_position="right",
                      on_click=go, args=("4. Close out",), key="to-closeout")
            if on_sheets and getattr(sink, "url", None):
                st.link_button("Open the sheet", sink.url, icon=":material/arrow_outward:", icon_position="right")
            elif not on_sheets:
                views = local_views(receipts, event, income, saved_reimbursements(sink))
                st.download_button("Download the whole book (Excel)", icon=":material/download:", key="dl-xlsx-done",
                                   data=book_xlsx(views, local_transactions(receipts), TX_FIELDS),
                                   file_name=f"{event.event_id}_books.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if ss.get("format_errors"):
        st.warning(md("Your numbers are in the sheet, but Google wouldn't apply the colors and layout on: "
                      + "; ".join(ss.format_errors) + ". Send this to whoever set up Tallyable."))
