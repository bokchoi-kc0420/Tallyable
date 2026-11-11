"""Step 2: check each drafted receipt against its photo, then approve it or leave it out of the books."""
from __future__ import annotations

import html
import time
from decimal import Decimal

import pandas as pd
import streamlit as st

from treasurer.checks import Severity, can_approve, run_checks
from treasurer.models import LineItem, Status
from ui.common import FLAG_ICON, ICON, STATUS_CHIP, dec, guide, md, next_step, payers, plural, reviewed, ss, step_bar, usd

FLAG_LOOK = {"math_error": (":material/calculate:", "The math doesn't add up"),
             "missing_payer": (":material/person_alert:", "Who paid for this?"),
             "missing_receipt": (":material/hide_image:", "No photo attached"),
             "unusual_tax": (":material/percent:", "Tax looks high"),
             "returned_item": (":material/undo:", "Returned item"),
             "possible_duplicate": (":material/content_copy:", "Possible duplicate")}
FLAG_TONE = {Severity.BLOCK: ("block", "Must fix"), Severity.WARN: ("warn", "Check"), Severity.INFO: ("info", "FYI")}


def next_drafted(after: str) -> str | None:
    """The next receipt still to review, wrapping around, so Approve opens it by itself."""
    order = list(ss.receipts)
    rest = order[order.index(after) + 1:] + order[:order.index(after)]
    return next((x for x in rest if ss.receipts[x].status is Status.DRAFTED), None)


def set_status(rid: str, status: Status, **changes) -> None:
    ss.receipts[rid] = ss.receipts[rid].model_copy(update={"status": status, **changes})


def needs_look(rid: str, flags: dict) -> bool:
    """A Check or Must fix flag, or a photo warning (blurry, small, a note from the reader). FYI flags don't count."""
    return any(f.severity is not Severity.INFO for f in flags[rid]) or bool(ss.notes.get(rid))


def approve_all(rids: list[str]) -> None:
    """Button callback: approve every receipt with nothing to fix, then open the first one left."""
    for x in rids:
        set_status(x, Status.APPROVED)
    ss.next_pick = next((x for x, rec in ss.receipts.items() if rec.status is Status.DRAFTED), None)


def approve_clean(flags: dict) -> None:
    """One click for every receipt with nothing to fix, so a big event goes fast. Flagged ones stay one by one."""
    clean = [x for x, rec in ss.receipts.items() if rec.status is Status.DRAFTED and not needs_look(x, flags)]
    if not clean:
        return
    n = len(clean)
    with st.container(border=True, key="clean-card"):
        c = st.columns([3.2, 1.4], vertical_alignment="center")
        c[0].markdown(f'<p class="tly-done-title">{plural(n, "receipt")} look{"s" if n == 1 else ""} good!</p>'
                      '<p class="tly-done-sub">The math adds up and everyone\'s tagged. '
                      "Peek at the photos to be sure I read them right.</p>", unsafe_allow_html=True)
        c[1].button(f"Approve all {n}" if n > 1 else "Approve it", type="primary", icon=":material/done_all:",
                    key="approve-clean", width="stretch", on_click=approve_all, args=(clean,))


def photo(rid: str) -> None:
    image = ss.images.get(rid)
    if not image:
        st.warning("No photo for this receipt.")
        return
    if image[1] != "application/pdf":
        st.image(image[0], width="stretch", alt=f"Receipt photo for {rid}")
        return
    st.info("PDF receipt.")
    st.download_button("Open the PDF", image[0], file_name=f"{rid}.pdf", mime="application/pdf")


def edit_form(rid: str, flags: list) -> None:
    """The receipt's fields, line items, and the Approve / Leave out / Reopen buttons."""
    r = ss.receipts[rid]
    for note in ss.notes.get(rid, []):
        st.warning(md(note))
    if r.status is not Status.DRAFTED:  # decided: one card says what happened, the flags are done with
        label, tone = STATUS_CHIP[r.status]
        why = f" · {html.escape(r.review_note)}" if r.review_note else ""
        undo = "" if r.status is Status.POSTED else "<br><small>Changed your mind? Hit Reopen.</small>"
        st.markdown(f'<div class="tly-decided {tone}"><b>{label.capitalize()}</b>{why}{undo}</div>',
                    unsafe_allow_html=True)
    for n, f in enumerate(flags if r.status is Status.DRAFTED else []):
        icon, title = FLAG_LOOK.get(f.code, (":material/flag:", "Check this"))
        tone, hint = FLAG_TONE[f.severity]
        with st.container(key=f"flag-{tone}-{rid}-{n}"):
            st.markdown(f"{icon} **{title}** <span class='tly-flagpill'>{hint}</span>\n\n"
                        f"<span class='tly-flagmsg'>{html.escape(f.message)}</span>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    place = c1.text_input("Place", r.place, key=f"place-{rid}")
    d = c2.date_input("Date", r.date, key=f"date-{rid}")
    options = payers() if (r.payer or "") in payers() else [*payers(), r.payer]
    payer = c3.selectbox("Payer", options, index=options.index(r.payer or ""), key=f"payer-{rid}")
    df = pd.DataFrame([{"category": i.category, "item": i.item, "unit": i.unit, "price": float(i.price),
                        "returned": i.returned} for i in r.items])
    columns = {"category": st.column_config.SelectboxColumn("Category", options=["Food", "Drink", "Other"]),
               "item": "Item", "unit": "Qty", "returned": "Returned",
               "price": st.column_config.NumberColumn("Price", format="%.2f")}
    edited = st.data_editor(df, num_rows="dynamic", key=f"items-{rid}", width="stretch", column_config=columns)
    c1, c2, c3 = st.columns(3)
    tax = c1.text_input("Tax", str(r.tax), key=f"tax-{rid}")
    tip = c2.text_input("Tip", str(r.tip), key=f"tip-{rid}")
    total = c3.text_input("Total", str(r.total), key=f"total-{rid}")

    try:
        items = [LineItem(category=row.category, item=str(row.item), unit=int(row.unit),
                          price=Decimal(f"{row.price:.2f}"), returned=bool(row.returned))
                 for row in edited.itertuples() if pd.notna(row.item) and str(row.item).strip()]
        new = r.model_copy(update=dict(place=place, date=d, payer=payer or None, items=items,
                                       tax=dec(tax), tip=dec(tip), total=dec(total)))
    except (ValueError, TypeError):
        st.error("Something's off in the line items! Each line needs an item, a qty and a price.")
    else:
        if new != r:
            ss.edits += 1
            ss.receipts[rid] = new
            st.rerun()  # re-run checks on the edited values

    st.caption(md(f"Items + tax + tip = {usd(r.computed_total)} · goes in the books as {usd(r.posted_amount)}"))
    note = st.text_input("Note", r.review_note or "", key=f"note-{rid}",
                         placeholder="Why you're approving a red flag, or leaving this out (duplicate, personal...)",
                         help="Needed to approve a receipt with a red flag, and to leave one out. "
                              "It's saved with the receipt, so you can explain the call later.")
    b1, b2, b3 = st.columns(3)
    locked = r.status is Status.POSTED
    if locked:
        st.caption("Posted to the books, so it can't change here. Fix it in the sheet's Transactions tab.")
    decided = r.status is not Status.DRAFTED
    approve = b1.button("Approve", type="primary", disabled=locked or decided or not can_approve(flags, note))
    leave_out = b2.container(key="leave-out").button("Leave out", disabled=locked or decided or not note.strip(),
                          help="Not a club expense (a duplicate, a personal buy, another event). "
                               "Write why in the note first.")
    if approve or leave_out:
        set_status(rid, Status.APPROVED if approve else Status.REJECTED, review_note=note.strip() or None)
        ss.next_pick = next_drafted(rid)
        st.rerun()
    if b3.button("Reopen", disabled=locked or not decided, help="Undo an approve or leave out"):
        set_status(rid, Status.DRAFTED)
        st.rerun()


def show() -> None:
    st.header("Review")
    step_bar("2. Review")
    if not ss.receipts:
        guide("Nothing to review yet!", "Drop your receipts on the Upload step and I'll read them for you.",
              key="review-empty", to="1. Upload")
        return
    ss.review_started = ss.review_started or time.time()
    flags = run_checks(list(ss.receipts.values()))
    checked = reviewed()
    st.progress(checked / len(ss.receipts), text=f"{checked} of {len(ss.receipts)} reviewed")
    approve_clean(flags)
    if checked == len(ss.receipts):
        ok = sum(1 for x in ss.receipts.values() if x.counts)
        next_step(f"**That's all {checked}!** {ok} approved, {checked - ok} left out. "
                  "Next up: add the money that came in.",
                  "Go to Summary →", "3. Summary", "to-summary")

    show_only = st.sidebar.selectbox("Show", ["All", "Not reviewed yet", "Needs attention"], key="review-filter")
    ids = [x for x, rec in ss.receipts.items()
           if show_only == "All" or (show_only == "Not reviewed yet" and rec.status is Status.DRAFTED)
           or (show_only == "Needs attention" and needs_look(x, flags))]
    if not ids:
        st.success("Nothing left in this view.")
        return
    labels = {x: f"{ICON[ss.receipts[x].status]} {x} · {ss.receipts[x].place}" + (f" {FLAG_ICON}" if needs_look(x, flags) else "")
              for x in ids}
    if ss.get("next_pick") in ids:  # set by "Approve" so the next receipt opens by itself
        ss["review-pick"] = ss.pop("next_pick")
    elif ss.get("review-pick") not in ids:
        ss["review-pick"] = ids[0]
    rid = st.sidebar.radio("Receipts", ids, format_func=labels.get, key="review-pick",
                           help=f"{ICON[Status.DRAFTED]} to review · {ICON[Status.APPROVED]} approved · "
                                f"{ICON[Status.REJECTED]} left out · {ICON[Status.POSTED]} posted · {FLAG_ICON} has a flag")
    left, right = st.columns([2, 3])
    with left:
        photo(rid)
    with right:
        edit_form(rid, flags[rid])
