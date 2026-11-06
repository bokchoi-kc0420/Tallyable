"""Step 2: check each drafted receipt against its photo, then approve or reject it."""
from __future__ import annotations

import html
import time
from decimal import Decimal

import pandas as pd
import streamlit as st

from treasurer.checks import Severity, can_approve, run_checks
from treasurer.models import LineItem, Status
from ui.common import ICON, STATUS_CHIP, dec, guide, md, next_step, payers, reviewed, ss, step_bar, usd

FLAG_LOOK = {"math_error": (":material/calculate:", "The math doesn't add up"),
             "missing_payer": (":material/person_alert:", "Who paid for this?"),
             "missing_receipt": (":material/hide_image:", "No photo attached"),
             "unusual_tax": (":material/percent:", "Tax looks high"),
             "returned_item": (":material/undo:", "Returned item"),
             "possible_duplicate": (":material/content_copy:", "Possible duplicate")}
FLAG_TONE = {Severity.BLOCK: ("block", "Fix this or add a note to approve"), Severity.WARN: ("warn", "Worth a second look"),
             Severity.INFO: ("info", "Just so you know")}


def next_drafted(after: str) -> str | None:
    """The next receipt still to review, wrapping around, so Approve opens it by itself."""
    order = list(ss.receipts)
    rest = order[order.index(after) + 1:] + order[:order.index(after)]
    return next((x for x in rest if ss.receipts[x].status is Status.DRAFTED), None)


def set_status(rid: str, status: Status, **changes) -> None:
    ss.receipts[rid] = ss.receipts[rid].model_copy(update={"status": status, **changes})


def approve_clean(flags: dict) -> None:
    """Offer one click for the receipts the checks found nothing wrong with."""
    clean = [x for x, rec in ss.receipts.items() if rec.status is Status.DRAFTED and not flags[x] and not ss.notes.get(x)]
    if not clean:
        return
    c = st.columns([3, 1.4], vertical_alignment="center")
    c[0].caption(f"{len(clean)} receipt{'s have' if len(clean) != 1 else ' has'} no flags at all. You can approve "
                 "them in one click. Flagged ones still need you, one by one. Glance at the photos first: "
                 "the checks catch math and missing info, not a wrong item.")
    if not c[1].button(f"Approve the {len(clean)} with no flags", icon=":material/done_all:", key="approve-clean",
                       width="stretch"):
        return
    for x in clean:
        set_status(x, Status.APPROVED)
    ss.next_pick = next((x for x, rec in ss.receipts.items() if rec.status is Status.DRAFTED), None)
    st.rerun()


def photo(rid: str) -> None:
    image = ss.images.get(rid)
    if not image:
        st.warning("No photo for this receipt.")
        return
    if image[1] != "application/pdf":
        st.image(image[0], width="stretch")
        return
    st.info("PDF receipt.")
    st.download_button("Open the PDF", image[0], file_name=f"{rid}.pdf", mime="application/pdf")


def edit_form(rid: str, flags: list) -> None:
    """The receipt's fields, line items, and the Approve / Reject / Reopen buttons."""
    r = ss.receipts[rid]
    for note in ss.notes.get(rid, []):
        st.warning(md(note))
    if r.status is not Status.DRAFTED:
        label, tone = STATUS_CHIP[r.status]
        st.markdown(f'<div class="tly-decided {tone}">This receipt is <b>{label}</b>.'
                    f'{" Click Reopen to change it." if r.status is not Status.POSTED else ""}</div>',
                    unsafe_allow_html=True)
    for n, f in enumerate(flags):
        icon, title = FLAG_LOOK.get(f.code, (":material/flag:", "Check this"))
        tone, hint = FLAG_TONE[f.severity]
        with st.container(key=f"flag-{tone}-{rid}-{n}"):
            st.markdown(f"{icon} **{title}** <span class='tly-flaghint'>· {hint}</span>\n\n"
                        f"<span class='tly-flagmsg'>{html.escape(f.message)}</span>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    place = c1.text_input("Place", r.place, key=f"place-{rid}")
    d = c2.date_input("Date", r.date, key=f"date-{rid}")
    options = payers() if (r.payer or "") in payers() else [*payers(), r.payer]
    payer = c3.selectbox("Payer", options, index=options.index(r.payer or ""), key=f"payer-{rid}")
    df = pd.DataFrame([{"category": i.category, "item": i.item, "unit": i.unit, "price": float(i.price),
                        "returned": i.returned} for i in r.items])
    edited = st.data_editor(df, num_rows="dynamic", key=f"items-{rid}", width="stretch",
                            column_config={"category": st.column_config.SelectboxColumn(options=["Food", "Drink", "Other"]),
                                           "price": st.column_config.NumberColumn(format="%.2f")})
    c1, c2, c3 = st.columns(3)
    tax = c1.text_input("Tax", str(r.tax), key=f"tax-{rid}")
    tip = c2.text_input("Tip", str(r.tip), key=f"tip-{rid}")
    total = c3.text_input("Total", str(r.total), key=f"total-{rid}")

    try:
        items = [LineItem(category=row.category, item=str(row.item), unit=int(row.unit),
                          price=Decimal(f"{row.price:.2f}"), returned=bool(row.returned))
                 for row in edited.itertuples() if str(row.item).strip()]
        new = r.model_copy(update=dict(place=place, date=d, payer=payer or None, items=items,
                                       tax=dec(tax), tip=dec(tip), total=dec(total)))
    except (ValueError, TypeError) as e:
        st.error(f"Fix the line items: {e}")
    else:
        if new != r:
            ss.edits += 1
            ss.receipts[rid] = new
            st.rerun()  # re-run checks on the edited values

    st.caption(md(f"Items + tax + tip = {usd(r.computed_total)} · posts {usd(r.posted_amount)}"))
    note = st.text_input("Override note (needed to approve with a red flag)", r.review_note or "",
                         key=f"note-{rid}")
    b1, b2, b3 = st.columns(3)
    locked = r.status is Status.POSTED
    if locked:
        st.caption("Posted to the books, so it can't change here. Fix it in the sheet's Transactions tab.")
    decided = r.status is not Status.DRAFTED
    approve = b1.button("Approve", type="primary", disabled=locked or decided or not can_approve(flags, note))
    reject = b2.button("Reject", disabled=locked or decided)
    if approve or reject:
        set_status(rid, Status.APPROVED if approve else Status.REJECTED, review_note=note or None)
        ss.next_pick = next_drafted(rid)
        st.rerun()
    if b3.button("Reopen", disabled=locked or not decided, help="Undo an approve or reject"):
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
        next_step(f"**All {checked} receipts reviewed:** {ok} approved, {checked - ok} rejected. "
                  "Next, add the event's income and push the approved rows to the books.",
                  "Go to Summary →", "3. Summary", "to-summary")

    def attention(x: str) -> bool:
        return any(f.severity is not Severity.INFO for f in flags[x]) or bool(ss.notes.get(x))

    show_only = st.sidebar.selectbox("Show", ["All", "Not reviewed yet", "Needs attention"])
    ids = [x for x, rec in ss.receipts.items()
           if show_only == "All" or (show_only == "Not reviewed yet" and rec.status is Status.DRAFTED)
           or (show_only == "Needs attention" and attention(x))]
    if not ids:
        st.success("Nothing left in this view.")
        return
    labels = {x: f"{ICON[ss.receipts[x].status].split()[0]} {x} · {ss.receipts[x].place}" + (" ⚠️" if attention(x) else "")
              for x in ids}
    if ss.get("next_pick") in ids:  # set by "Approve" so the next receipt opens by itself
        ss["review-pick"] = ss.pop("next_pick")
    elif ss.get("review-pick") not in ids:
        ss["review-pick"] = ids[0]
    rid = st.sidebar.radio("Receipts", ids, format_func=labels.get, key="review-pick",
                           help="⏳ to review · ✅ approved · ❌ rejected · 📤 posted · ⚠️ has a flag")
    left, right = st.columns([2, 3])
    with left:
        photo(rid)
    with right:
        edit_form(rid, flags[rid])
