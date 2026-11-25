"""Step 4: pay back whoever fronted money, and check the event against a funder's rules."""
from __future__ import annotations

import html
from collections import Counter
from datetime import date
from decimal import Decimal

import streamlit as st

from treasurer import closeout as co
from treasurer.checks import Severity
from treasurer.models import Receipt, Status
from treasurer.photo_pdf import receipts_pdf
from treasurer.reimburse import METHODS, Reimbursement, totals_by_payer, validate
from treasurer.sheets import EventInfo
from ui import club, finish
from ui.common import ART, dec, get_sink, guide, html_table, md, money_panel, now, plural, saved_reimbursements, ss, step_bar, usd

EXAMPLES = {"Example: event grant (up to $2,500)": co.CFC, "Example: yearly grant ($250)": co.ORG}


def save_paybacks(sink, paybacks: list[Reimbursement]) -> bool:
    who = paybacks[0].payer if len(paybacks) == 1 else f"{len(paybacks)} people"
    try:
        with st.spinner(f"Saving the payback to {who}..."):
            sink.record_reimbursements(paybacks)
    except Exception as e:
        st.error(f"Payback not saved: {e}. Try again.")
        return False
    return True


def undo_last(sink, last: dict, event_id: str) -> None:
    """Take back this event's latest payback, for a misclicked Mark paid."""
    label = f"Undo last payback: {usd(dec(str(last['amount'])))} to {last['payer']}"
    if not st.button(label, key="undo-paid", icon=":material/undo:"):
        return
    try:
        sink.undo_reimbursement(event_id)
    except Exception as e:
        st.error(f"Couldn't undo the payback: {e}. Try again.")
        return
    st.rerun()


# Six coins fly up and out of the Paid line; --x/--y is where each lands, --w its delay (style.css).
COINS = '<span class="tly-coins" aria-hidden="true">' + "".join(
    f'<i style="--x:{x}px;--y:{y}px;--w:{w}s">$</i>'
    for x, y, w in [(-56, -64, 0), (-24, -88, .05), (8, -96, .1), (40, -80, .03), (64, -56, .08), (-8, -48, .12)]) + "</span>"
CARD = [2.4, 1.0, 1.1, 1.3]  # who, Paying now, Paid with, Mark as paid


def paid_with(col, payer: str) -> tuple[str, str] | None:
    """Method (and a note for Other) for one card's Mark as paid. None while Other has no note yet."""
    method = col.selectbox("Paid with", METHODS, key=f"method-{payer}")
    if method != "Other":
        return method, ""
    note = col.text_input("How?", key=f"note-{payer}", placeholder="How? e.g. club card",
                          label_visibility="collapsed").strip()
    return (method, note) if note else None


def bar(x) -> str:
    """How much of what they fronted is back, as a bar along the bottom of the card."""
    pct = int(100 * x.reimbursed / x.fronted) if x.fronted > 0 else 100
    return (f'<div class="tly-owe-bar"><span><b>{pct}%</b> reimbursed</span><span>{usd(x.reimbursed)} of {usd(x.fronted)}</span>'
            f'<div class="track"><div style="width:{min(pct, 100)}%"></div></div></div>')


def person_card(n: int, x, receipts: int, last: dict | None, event_id: str) -> tuple[Reimbursement | None, bool] | None:
    """One person's card (Kevin's pick D1): who, what's left to pay back in a box you can type less into,
    how, and Mark as paid. Returns (the payback its card would make, Mark as paid clicked), or None with nothing to pay."""
    color = club.AVATARS[n % len(club.AVATARS)]
    done = x.owed <= 0
    with st.container(border=True, key=f"owe-{'done-' if done else ''}{n}"):
        st.html(f"<style>.st-key-owe-{'done-' if done else ''}{n} {{ border-left: 8px solid {color}; }}</style>")
        # A paid card has no labeled boxes, so its line sits level with the name
        c = st.columns([CARD[0], sum(CARD[1:])] if done else CARD, gap="small", vertical_alignment="center" if done else "bottom")
        part = '<span class="tly-owe-part">Partly reimbursed</span>' if x.reimbursed > 0 and not done else ""
        c[0].markdown(f'<div class="tly-owe-who"><span class="tly-owe-avatar" style="background:{color}">'
                      f'{html.escape(club.initials(x.payer) or "?")}</span><div>'
                      f'<p class="tly-owe-name"><b data-payer="{html.escape(x.payer)}">{html.escape(x.payer)}</b>{part}</p>'
                      f'<p class="tly-owe-sub">{plural(receipts, "receipt")}, fronted {usd(x.fronted)}</p></div></div>',
                      unsafe_allow_html=True)
        if done:
            pop = x.payer in ss.get("just_paid", ())  # coins burst out once, right after Mark as paid
            coins = COINS.replace('class="tly-coins"', f'class="tly-coins" data-for="{html.escape(x.payer)}"') if pop else ""
            day = date.fromisoformat(str(last["date"])) if last else None
            how = f"by {last['method']} on {day:%b} {day.day}" if last else ""
            c[1].html(f'<p class="tly-owe-done{" pop" if pop else ""}"><i class="ms">check_circle</i>Fully reimbursed'
                    f'<small>{html.escape(how)}</small>{coins}</p>')
            st.html(bar(x))
            return None
        if x.payer == "(no payer)":
            c[1].caption("Set a payer in Review")
            st.html(bar(x))
            return None
        # owed in the key: the box refills after a payback
        amount = c[1].text_input("Paying now", str(x.owed), key=f"amount-{x.payer}-{x.owed}")
        how = paid_with(c[2], x.payer)
        amt, problem = validate(x.payer, amount, x.owed)
        if problem:
            st.caption(f":red[{problem}]")
        pay = Reimbursement(event_id, x.payer, now().date(), amt, *how) if how and amt else None
        clicked = c[3].button("Mark as paid", key=f"paid-{x.payer}", type="primary", width="stretch", disabled=not pay)
        st.html(bar(x))
    return pay, clicked


def whos_owed(sink, done: list[Receipt], lines: list, event_id: str, paybacks: list[dict]) -> None:
    """One card per person who fronted money: what's left to pay them back, how, and Mark as paid.
    Cards never move: Mark as paid leaves the person where they were."""
    counts = Counter((r.payer or "").strip() or "(no payer)" for r in done)
    last = {str(p["payer"]): p for p in paybacks}
    left = sum((x.owed for x in lines if x.owed > 0), Decimal("0"))
    c = st.columns(2, vertical_alignment="center")
    c[0].subheader("Who's owed")
    if left > 0:
        c[1].markdown(f'<p class="tly-owe-left"><span>{usd(left)} left to reimburse</span></p>', unsafe_allow_html=True)
    unpaid: list[Reimbursement | None] = []  # one per card that can be paid; None while its box isn't ready
    for n, x in enumerate(lines):
        card = person_card(n, x, counts[x.payer], last.get(x.payer), event_id)
        if card is None:
            continue
        pay, clicked = card
        if clicked and save_paybacks(sink, [pay]):
            ss.just_paid = [x.payer]
            st.rerun()
        unpaid.append(pay)
    ss.pop("just_paid", None)
    with st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center", key="owe-foot"):
        if unpaid:
            st.html('<p class="tly-edit-hint"><i class="ms">edit</i>Only paying back some of it? Type that amount in first.</p>')
        # One save for everyone: each Mark as paid is its own trip to the books, which is the slow part.
        if len(unpaid) > 1 and st.button("Mark everyone as paid", key="paid-all", disabled=None in unpaid,
                                         help=f"Records all {len(unpaid)} paybacks today, each the way their card says."):
            if save_paybacks(sink, unpaid):
                ss.just_paid = [p.payer for p in unpaid]
                st.rerun()
    st.caption(f"Each payback is saved to {sink.label}.")
    if paybacks:
        undo_last(sink, paybacks[-1], event_id)


def my_funder() -> co.RulePack:
    """A form for the club's own funder rules. Saved with the event so it's filled in next time."""
    saved = ss.event.get("funder", {})
    with st.container(border=True, key="my-funder"):
        st.caption("Fill in whatever your funder asks for. If they don't have a rule, leave it blank.")
        f1 = st.columns(3)
        fname = f1[0].text_input("Funder name", saved.get("name", ""), placeholder="e.g. Student Government")
        fmax = f1[1].text_input("Biggest grant ($)", saved.get("max", ""), placeholder="no limit")
        ffood = f1[2].text_input("Food cap per person ($)", saved.get("food", ""), placeholder="no cap")
        f2 = st.columns(3)
        fshare = f2[0].text_input("Club must pay at least (%)", saved.get("share", ""), placeholder="0")
        fdue = f2[1].text_input("Report due (days after event)", saved.get("due", ""), placeholder="no deadline")
        fban = f2[2].multiselect("Can't be paid for", ["Food", "Drink", "Other"], saved.get("ban", []))
    ss.event = {**ss.event, "funder": {"name": fname, "max": fmax, "food": ffood, "share": fshare, "due": fdue,
                                       "ban": fban}}
    due_days = int(dec(fdue)) if fdue.strip() and dec(fdue) > 0 else None
    return co.RulePack(name=fname.strip() or "Your funder",
                       max_award=dec(fmax) if fmax.strip() else None,
                       food_cap_per_person_day=dec(ffood) if ffood.strip() else None,
                       min_club_share=dec(fshare) / 100 if fshare.strip() else None,
                       report_due_days_after_event=due_days, banned_categories=frozenset(fban))


def funder_rules(info: EventInfo, done: list[Receipt], reimbursed: dict) -> None:
    st.subheader("Funder rules")
    if ss.event.get("late"):
        st.info("A receipt added after closing out changes the totals. If you already sent your funder a report, "
                "send the new numbers.")
    funder = st.selectbox("Funder", ["No funder", "My funder's rules", *EXAMPLES], key="funder",
                          help="Rules from whoever funds your event: student government, a department, a sponsor. "
                               "The examples are real rules from one student government, to show how it works.")
    if funder == "No funder":
        st.caption("No funder? Then paying people back is all that's left.")
        return
    pack = my_funder() if funder == "My funder's rules" else EXAMPLES[funder]
    c = st.columns(3)
    attendees = int(c[0].number_input("Attendees", min_value=1, value=ss.event["attendees"]))
    req_text = c[1].text_input("Requested ($, optional)", "")
    applied_on = c[2].date_input("Applying on", value=now().date())
    requested = dec(req_text) if req_text.strip() else None
    event = co.Event(info.event_id, info.name, info.date, attendees=attendees)
    flags = co.check_funder_rules(event, done, pack, requested, applied_on)
    most, steps = co.max_request(event, done, pack)
    st.metric("Most you can request", usd(most), border=True)
    with st.expander("How that was worked out"):
        for s in steps:
            st.write(md(s))
    due = co.report_due(event, pack)
    if due:
        st.caption(f"{pack.name}: report due {due.isoformat()}")
    if not flags:
        st.success(f"No {pack.name} rules broken.")
    for f in flags:
        {Severity.BLOCK: st.error, Severity.WARN: st.warning, Severity.INFO: st.info}[f.severity](md(f.message))
    for note in pack.notes:
        st.caption(note)

    st.divider()
    st.markdown("**Last step:** attach the funder report to your request, then **Finish event**.")
    st.download_button("Download funder report (CSV)", type="primary", icon=":material/download:",
                       file_name=f"{info.event_id}_funder_report.csv",
                       data=co.funder_report_csv(event, done, pack, requested, applied_on, reimbursed),
                       mime="text/csv")


def show(event: EventInfo) -> None:
    st.header("Close out the event")
    step_bar("4. Close out")
    done = [r for r in ss.receipts.values() if r.counts]
    if not done:
        guide("Nothing to close out yet!", "Approve some receipts on Review, then I'll show who's owed.",
              key="close-empty", to="2. Review")
        return
    waiting = [r.receipt_id for r in ss.receipts.values() if r.status is Status.DRAFTED]
    if waiting:
        st.warning(f"Still need a look, so they're not counted yet: {', '.join(waiting)}")
    else:
        with st.container(key="mascot-cheer"):
            st.image(str(ART / "tally-thumbs-up.png"), width=170)  # the finish page has the flag
        left_out = len(ss.receipts) - len(done)
        cheer = f"All {len(done)} receipts approved!" if not left_out else f"All reviewed! {len(done)} approved, {left_out} left out."
        st.markdown(f'<p class="tly-cheer">{cheer}</p>', unsafe_allow_html=True)

    sink, err = get_sink()
    if err:
        st.error(err)
    paybacks = [p for p in saved_reimbursements(sink) if str(p["event_id"]) == event.event_id]
    reimbursed = totals_by_payer(paybacks, event.event_id)
    lines = co.payer_summary(done, reimbursed)
    owing = [x for x in lines if x.owed > 0]
    if ss.get("just_paid") and not owing:  # the last Mark paid: Who's owed is done, on to the next part
        ss.scroll_to = ".st-key-money-box"
    with st.container(border=True, key="whos-owed"):
        whos_owed(sink, done, lines, event.event_id, paybacks)
    with st.container(border=True, key="money-box"):
        st.subheader("Money in vs out")
        money_panel(done, {k: dec(v) for k, v in ss.income.items()})
    left_out = [r for r in ss.receipts.values() if r.status is Status.REJECTED]
    if left_out:
        with st.expander(f"Left out of the books ({len(left_out)})"):
            st.caption("These don't count in the books.")
            html_table([{"Receipt": r.receipt_id, "Place": r.place, "Payer": r.payer or "(none)",
                         "Total": usd(r.total), "Why": r.review_note or ""} for r in left_out], numeric=("Total",))
    if not owing:
        st.success("Everyone's been paid back!")
    funder_rules(event, done, reimbursed)
    photos(event, done, lines)
    finish.finish_button(lines)


def photos(event: EventInfo, done: list[Receipt], lines) -> None:
    """Every receipt photo, labeled, in one PDF: for the funder, or to check prices against."""
    st.subheader("Receipt photos")
    st.caption("Every receipt photo in one labeled PDF, for your funder or your records.")
    owed = {x.payer: x.owed for x in lines}
    paid = {r.receipt_id: ("Not yet" if owed.get(r.payer or "(no payer)", 0) > 0 else "Yes") if r.payer else ""
            for r in done}
    images = ss.images  # the PDF is built when the button is clicked, not on every visit (0.7s with phone photos)
    st.download_button("Download receipt photos (PDF)", icon=":material/photo_library:", key="dl-photos",
                       file_name=f"{event.event_id}_receipt_photos.pdf", mime="application/pdf", on_click="ignore",
                       data=lambda: receipts_pdf(done, images, paid))
