"""Step 2: check each drafted receipt against its photo, then approve it or leave it out of the books."""
from __future__ import annotations

import html
import time
from decimal import Decimal

import pandas as pd
import streamlit as st

from treasurer.checks import Severity, can_approve, run_checks, suspect_box
from treasurer.images import pdf_pages
from treasurer.models import LineItem, Status
from ui import club
from ui.common import FLAG_ICON, ICON, STATUS_CHIP, dec, guide, is_demo, md, next_step, payers, plural, reviewed, ss, step_bar, usd

FLAG_LOOK = {"math_error": (":material/calculate:", "The math doesn't add up"),
             "missing_payer": (":material/person_alert:", "Who paid for this?"),
             "missing_receipt": (":material/hide_image:", "No photo attached"),
             "unusual_tax": (":material/percent:", "Tax looks high"),
             "returned_item": (":material/undo:", "Left out of the books"),
             "not_final": (":material/receipt_long:", "Not a final receipt"),
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
    if not ss.next_pick:
        ss.scroll_to = ".st-key-to-summary"


@st.dialog("Approve these?", on_dismiss=lambda: ss.pop("check_all", None))
def check_all(rids: list[str]) -> None:
    """Grouped by who gets paid back, like Who's owed, so "$51.19 for Kevin?" is what you check. The biggest receipt
    is marked, and each person opens to their photos."""
    people: dict[str, list[str]] = {}
    for x in rids:
        people.setdefault(ss.receipts[x].payer or "No payer", []).append(x)
    big = max(rids, key=lambda x: ss.receipts[x].posted_amount)
    for who, mine in people.items():
        total = sum((ss.receipts[x].posted_amount for x in mine), Decimal("0"))
        with st.expander(f"**{who}**  {usd(total)}", key=f"check-{who}"):
            lines = "".join(f'<li{" class=big" if x == big and len(rids) > 1 else ""}><span>{html.escape(ss.receipts[x].place)}'
                            f'<small>{plural(len(ss.receipts[x].items), "item")}</small></span>'
                            f"<b>{usd(ss.receipts[x].posted_amount)}</b></li>" for x in mine)
            st.markdown(f'<ul class="tly-check-all">{lines}</ul>', unsafe_allow_html=True)
            shots = [ss.images[x][0] for x in mine if ss.images.get(x) and ss.images[x][1] != "application/pdf"]
            for row in range(0, len(shots), 4):
                for col, img in zip(st.columns(4), shots[row:row + 4], strict=False):
                    col.image(img, width="stretch")
    st.markdown('<p class="tly-confirm-note">Anything the club didn\'t pay for? Go back and tick it under '
                "<b>Leave out</b>.</p>", unsafe_allow_html=True)
    c = st.columns(2)
    if c[0].button("Go back", key="check-all-no", width="stretch"):
        ss.pop("check_all", None)
        st.rerun()
    if c[1].button(f"Approve all {len(rids)}", type="primary", key="check-all-yes", width="stretch"):
        ss.pop("check_all", None)
        approve_all(rids)
        st.rerun()


def approve_clean(flags: dict) -> None:
    """One click for every receipt with nothing to fix, so a big event goes fast. Flagged ones stay one by one."""
    clean = [x for x, rec in ss.receipts.items() if rec.status is Status.DRAFTED and not needs_look(x, flags)]
    if not clean:
        return
    n = len(clean)
    with st.container(border=True, key="clean-card"):
        c = st.columns([3.2, 1.4], vertical_alignment="center")
        c[0].markdown(f'<p class="tly-done-title">{plural(n, "receipt")} {"has" if n == 1 else "have"} no problems</p>'
                      '<p class="tly-done-sub">Their totals match the photos. Approve them all, or open one to check.</p>',
                      unsafe_allow_html=True)
        # The demo's fake receipts go straight through, so the tour isn't covered by the check.
        go = approve_all if is_demo() else lambda c: ss.update(check_all=c)
        c[1].button(f"Approve all {n}" if n > 1 else "Approve it", type="primary", icon=":material/done_all:",
                    key="approve-clean", width="stretch", on_click=go, args=(clean,))
    if ss.get("check_all"):
        check_all(ss.check_all)


def photo(rid: str) -> None:
    image = ss.images.get(rid)
    if not image:
        st.warning("No photo for this receipt.")
        return
    if image[1] != "application/pdf":
        st.image(image[0], width="stretch", alt=f"Receipt photo for {rid}")
        return
    for n, page in enumerate(pdf_pages(image[0]), start=1):
        st.image(page, width="stretch", alt=f"Receipt {rid}, page {n}")
    st.download_button("Open the PDF", image[0], file_name=f"{rid}.pdf", mime="application/pdf", type="tertiary")


def look_card(rid: str, flags: list) -> None:
    """Everything to check on one receipt in ONE card: what must be fixed first, then the smaller notes
    (blurry photo, what the reader couldn't see). The card takes the colour of its worst flag."""
    notes = ss.notes.get(rid, [])
    if not flags and not notes:
        return
    flags = sorted(flags, key=lambda f: list(FLAG_TONE).index(f.severity))
    tone = FLAG_TONE[flags[0].severity][0] if flags else "note"
    with st.container(key=f"flag-{tone}-{rid}"):
        for f in flags:
            icon, title = FLAG_LOOK.get(f.code, (":material/flag:", "Check this"))
            st.markdown(f"{icon} **{title}** <span class='tly-flagpill {FLAG_TONE[f.severity][0]}'>{FLAG_TONE[f.severity][1]}"
                        f"</span>\n\n<span class='tly-flagmsg'>{md(html.escape(f.message))}</span>", unsafe_allow_html=True)
        if notes:
            lines = "".join(f"<li>{html.escape(n)}</li>" for n in notes)
            st.markdown(f"<ul class='tly-notes'>{lines}</ul>", unsafe_allow_html=True)


COLUMNS = ["unit", "item", "printed", "price", "category", "returned", "taxed", "for_item_above"]


def frame(items: list[LineItem]) -> pd.DataFrame:
    return pd.DataFrame([{c: float(i.price) if c == "price" else getattr(i, c) for c in COLUMNS} for i in items],
                        columns=COLUMNS)


def lines(edited: pd.DataFrame) -> list[LineItem]:
    """The table's rows back as line items; a row with no item name yet is skipped."""
    return [LineItem(category=row.category, item=str(row.item), printed=row.printed if isinstance(row.printed, str) else None,
                     unit=int(row.unit),
                     price=Decimal(f"{row.price:.2f}"), returned=bool(row.returned),
                     taxed=None if pd.isna(row.taxed) else bool(row.taxed),
                     for_item_above=bool(row.for_item_above) if pd.notna(row.for_item_above) else False)
            for row in edited.itertuples() if pd.notna(row.item) and str(row.item).strip()]


def split_savings(items: list[LineItem]) -> tuple[list[LineItem], list[LineItem], list[int]]:
    """Things bought, the savings (negative lines), and for each saving how many bought lines come before it,
    so merge_savings can put it back where the receipt printed it."""
    bought, savings, after = [], [], []
    for i in items:
        if i.price >= 0:
            bought.append(i)
            continue
        savings.append(i)
        after.append(len(bought))
    return bought, savings, after


def merge_savings(bought: list[LineItem], savings: list[LineItem], after: list[int]) -> list[LineItem]:
    """Each saving back under the line it was printed under. A new saving, or one whose line was deleted,
    goes last as a saving on the whole order."""
    items = []
    for n, i in enumerate(bought, 1):
        items += [i, *(s for s, a in zip(savings, after, strict=False) if a == n)]
    loose = [s for k, s in enumerate(savings) if k >= len(after) or not 1 <= after[k] <= len(bought)]
    return items + [s.model_copy(update={"for_item_above": False}) for s in loose]


def savings_box(rid: str, savings: list[LineItem], on: list[str]) -> pd.DataFrame | None:
    """Member savings, coupons and promos in their own green box under the items (Kevin's pick B),
    each saying which item it comes off. None when the receipt has none."""
    if not savings:
        return None
    total = sum((s.amount for s in savings), Decimal("0"))
    with st.container(key=f"savings-box-{rid}"):
        st.html(f'<p class="tly-savings-head"><span>Savings</span><b>{usd(total)}</b></p>')
        return st.data_editor(frame(savings).assign(on=on), key=f"savings-{rid}", width="stretch", hide_index=True,
                              column_order=["item", "on", "price"], disabled=["on"],
                              column_config={"item": st.column_config.TextColumn("Saving", width=188),
                                             "on": st.column_config.TextColumn("Comes off"),
                                             "price": st.column_config.NumberColumn("Price", format="%.2f", width=72)})


def add_line(rid: str) -> None:
    """Button callback: a blank line at the end of the receipt to fill in."""
    r = ss.receipts[rid]
    ss.receipts[rid] = r.model_copy(update={"items": [*r.items, LineItem(category="Other", item="New item", unit=1,
                                                                         price=Decimal("0"))]})
    ss.pop(f"items-{rid}", None)


def edit_form(rid: str, flags: list) -> None:
    """The receipt's fields, line items, and the Approve / Leave out / Reopen buttons."""
    r = ss.receipts[rid]
    if r.status is not Status.DRAFTED:  # decided: one card says what happened, the flags are done with
        label, tone = STATUS_CHIP[r.status]
        why = f" · {html.escape(r.review_note)}" if r.review_note else ""
        undo = ("<br><small>Spot a mistake? Hit Reopen, fix it, then Push again.</small>" if r.status is Status.POSTED
                else "<br><small>Changed your mind? Hit Reopen.</small>")
        st.markdown(f'<div class="tly-decided {tone}"><b>{label.capitalize()}</b>{why}{undo}</div>',
                    unsafe_allow_html=True)
    # Left-out lines get a small chip by the table instead of a card: the ticks already say which ones.
    look_card(rid, [f for f in flags if f.code != "returned_item"] if r.status is Status.DRAFTED else [])
    st.markdown('<p class="tly-edit-hint"><i class="ms">edit</i>Got something wrong? Click any box or cell to fix it.</p>',
                unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    place = c1.text_input("Place", r.place, key=f"place-{rid}")
    d = c2.date_input("Date", r.date, key=f"date-{rid}")
    options = payers() if (r.payer or "") in payers() else [*payers(), r.payer]
    payer = c3.selectbox("Payer", options, index=options.index(r.payer or ""), key=f"payer-{rid}",
                         format_func=lambda x: x or "Who paid?")
    bought, savings, after = split_savings(r.items)
    comes_off = [o.item if o is not i else "Whole order" for i, o in zip(r.items, r.owners, strict=True) if i.price < 0]
    # Qty, item, price side by side like a printed receipt, with set widths so a long name can't push Price off screen.
    columns = {"unit": st.column_config.NumberColumn("Qty", width=56),
               "item": st.column_config.TextColumn("Item", width=184, help="Clear a name to take that line off"),
               "printed": st.column_config.TextColumn("On receipt", width=104, help="Exactly as the receipt prints it"),
               "price": st.column_config.NumberColumn("Price", format="%.2f", width=72),
               "category": st.column_config.SelectboxColumn("Category", options=["Food", "Drink", "Other"], width=88),
               "returned": st.column_config.CheckboxColumn("Not club's", width=92,
                                                           help="A personal buy, or returned")}
    if r.status is Status.DRAFTED and not all(i.returned for i in r.items) and len(r.items) > 2:
        # A grocery run where only a line or two was for the club: leave everything out, then untick the club's.
        if st.button("Not a club expense? Leave out this receipt", key=f"all-out-{rid}", type="tertiary"):
            ss.receipts[rid] = r.model_copy(update={"items": [i.model_copy(update={"returned": True}) for i in r.items]})
            ss.pop(f"items-{rid}", None)
            st.rerun()
    out = [i for i in r.items if i.returned]
    if out:
        st.markdown(f'<span class="tly-left-out">↺ {len(out)} left out '
                    f'<em>({r.left_out_why})</em><b>&minus;{usd(r.returned_amount)}</b></span>', unsafe_allow_html=True)
    # Tax marks and discount links ride along hidden, so an edit never drops them.
    # The receipt's own wording is shaded: it's there to check against the photo, not to edit.
    table = frame(bought).assign(printed=[i.printed or i.item for i in bought]).style.set_properties(
        subset=["printed"], **{"color": "#6B6A60", "background-color": "#F2ECD3"})
    # A fixed table, so only the header is green (Kevin): the add/delete row and side strip took the header color.
    edited = st.data_editor(table, key=f"items-{rid}", width="stretch", hide_index=True,
                            column_config=columns, column_order=list(columns), disabled=["printed"])
    st.button("Add a line", icon=":material/add:", type="tertiary", key=f"add-line-{rid}", on_click=add_line, args=(rid,))
    saved = savings_box(rid, savings, comes_off)
    why = r.left_out_why
    if any(i.returned for i in r.items):
        why = st.segmented_control("Left out because", ["personal", "returned"], default=r.left_out_why,
                                   format_func={"personal": "Personal", "returned": "Returned"}.get,
                                   key=f"why-{rid}") or r.left_out_why
    c1, c2, c3 = st.columns(3)
    tax = c1.text_input("Tax", str(r.tax), key=f"tax-{rid}")
    tip = c2.text_input("Tip", str(r.tip), key=f"tip-{rid}")
    total = c3.text_input("Total", str(r.total), key=f"total-{rid}")
    if box := suspect_box(r):  # the math is off: outline the box that's most likely wrong, so it isn't a guess
        (c1 if box == "tax" else c3).caption(":red[Check this one]")
        st.html(f'<style>.st-key-{box}-{rid} [data-testid="stTextInputRootElement"] '
                "{ border: 2px solid var(--tly-berry); }</style>")

    try:
        items = merge_savings(lines(edited), lines(saved) if saved is not None else [], after)
        new = r.model_copy(update=dict(place=place, date=d, payer=payer or None, items=items, left_out_why=why,
                                       tax=dec(tax), tip=dec(tip), total=dec(total)))
    except (ValueError, TypeError):
        st.error("Something's off in the line items! Each line needs an item, a qty and a price.")
    else:
        if new != r:
            ss.edits += 1
            ss.receipts[rid] = new
            # A line can hop between the two tables (a price turned negative), so both redraw from the receipt.
            ss.pop(f"items-{rid}", None)
            ss.pop(f"savings-{rid}", None)
            st.rerun()  # re-run checks on the edited values

    st.caption(md(f"Goes in the books as {usd(r.posted_amount)}" if out else
                  f"Items + tax + tip = {usd(r.computed_total)} · goes in the books as {usd(r.posted_amount)}"))
    decided = r.status is not Status.DRAFTED
    blocked = not decided and not can_approve(flags)
    note = st.text_input("Note", r.review_note or "", key=f"note-{rid}",
                         placeholder="Why you're leaving this out (duplicate, personal...), or anything to remember",
                         help="Needed to leave a receipt out. It's saved with the receipt.")
    # One row, each button as wide as its label, so Leave out sits right beside Approve whatever the label says.
    b1 = b2 = b3 = st.container(horizontal=True, key="decide")
    # With a red flag open, the button says what it will do: the receipt's own total goes in the books.
    # No payer is the one flag that can't be booked past: nobody would get paid back.
    no_payer = any(f.code == "missing_payer" for f in flags)
    # Booking past a red flag is the way out, not the way forward: fixing the box is, so it isn't the green button.
    approve = b1.button(f"Book {usd(r.posted_amount)} anyway" if blocked else "Approve", type="secondary" if blocked else "primary",
                        key=f"approve-{rid}", disabled=decided or no_payer,
                        help="Pick who paid first." if no_payer and not decided else None)
    leave_out = b2.container(key="leave-out").button("Leave out", disabled=decided or not note.strip(),
                          help="Not a club expense (a duplicate, a personal buy, another event). "
                               "Write why in the note first.")
    if approve or leave_out:
        set_status(rid, Status.APPROVED if approve else Status.REJECTED, review_note=note.strip() or None)
        ss.next_pick = next_drafted(rid)
        if not ss.next_pick:  # the last one: Go to Summary sits at the top, out of sight on a long receipt
            ss.scroll_to = ".st-key-to-summary"
        st.rerun()
    if b3.button("Reopen", disabled=not decided, help="Undo an approve or leave out, or fix one that's already in the books"):
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
    flags = run_checks(list(ss.receipts.values()), club.earlier_receipts())
    checked = reviewed()
    st.progress(checked / len(ss.receipts), text=f"{checked} of {len(ss.receipts)} reviewed")
    approve_clean(flags)
    if checked == len(ss.receipts):
        ok = sum(1 for x in ss.receipts.values() if x.counts)
        next_step(f"**That's all {checked}!** {ok} approved, {checked - ok} left out. "
                  "Now let's add the money that came in.",
                  "Go to Summary →", "3. Summary", "to-summary")

    show_only = st.sidebar.selectbox("Show", ["All", "Not reviewed yet", "Needs attention"], key="review-filter")
    ids = [x for x, rec in ss.receipts.items()
           if show_only == "All" or (show_only == "Not reviewed yet" and rec.status is Status.DRAFTED)
           or (show_only == "Needs attention" and needs_look(x, flags))]
    if not ids:
        st.success("You've cleared everything here.")
        return
    labels = {x: f"{ICON[ss.receipts[x].status]} {x} · {ss.receipts[x].place}" + (f" {FLAG_ICON}" if needs_look(x, flags) else "")
              for x in ids}
    # next_pick is set by "Approve" so the next receipt opens by itself. The pick is written back on every run:
    # the labels change as you edit (place, status), and Streamlit then forgets a pick it wasn't just handed.
    pick = ss.pop("next_pick") if ss.get("next_pick") in ids else ss.get("review-pick")
    ss["review-pick"] = pick if pick in ids else ids[0]
    rid = st.sidebar.radio("Receipts", ids, format_func=labels.get, key="review-pick",
                           help=f"{ICON[Status.DRAFTED]} to review · {ICON[Status.APPROVED]} approved · "
                                f"{ICON[Status.REJECTED]} left out · {ICON[Status.POSTED]} posted · {FLAG_ICON} has a flag")
    left, right = st.columns([2, 3])
    with left:
        # Back and forward through the same list as the sidebar, so an approved receipt is one click away.
        i = ids.index(rid)
        with st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center", key="review-nav"):
            st.button("", icon=":material/arrow_back:", key="review-prev", help="Previous receipt", disabled=i == 0,
                      on_click=ss.__setitem__, args=("review-pick", ids[i - 1]))
            st.markdown(f'<p class="tly-nav-count">{i + 1} of {len(ids)}</p>', unsafe_allow_html=True)
            st.button("", icon=":material/arrow_forward:", key="review-next", help="Next receipt", disabled=i == len(ids) - 1,
                      on_click=ss.__setitem__, args=("review-pick", ids[(i + 1) % len(ids)]))
        photo(rid)
    with right:
        edit_form(rid, flags[rid])
