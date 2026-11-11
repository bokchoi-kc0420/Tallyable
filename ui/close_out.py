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
from ui import finish
from ui.common import ART, dec, get_sink, guide, html_table, md, money_panel, saved_reimbursements, ss, step_bar, usd

EXAMPLES = {"Example: event grant (up to $2,500)": co.CFC, "Example: yearly grant ($250)": co.ORG}


def save_payback(sink, payback: Reimbursement) -> bool:
    try:
        with st.spinner(f"Saving the payback to {payback.payer}..."):
            sink.record_reimbursement(payback)
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


# Six coins fly up and out of the Paid cell; --x/--y is where each lands, --w its delay (style.css).
COINS = '<span class="tly-coins" aria-hidden="true">' + "".join(
    f'<i style="--x:{x}px;--y:{y}px;--w:{w}s">$</i>'
    for x, y, w in [(-56, -64, 0), (-24, -88, .05), (8, -96, .1), (40, -80, .03), (64, -56, .08), (-8, -48, .12)]) + "</span>"
LEDGER = [1.6, 0.9, 1.1, 1.1, 1.1, 1.5, 1.3]  # Person, Receipts, Fronted, Paid back, Still owed, Paid with, button


def cell(col, text: str, cls: str = "") -> None:
    col.markdown(f'<p class="tly-led {cls}">{text}</p>', unsafe_allow_html=True)


def paid_with(col, payer: str) -> tuple[str, str] | None:
    """Method (and a note for Other) for one row's Mark paid. None while Other has no note yet."""
    method = col.selectbox("Paid with", METHODS, key=f"method-{payer}", label_visibility="collapsed")
    if method != "Other":
        return method, ""
    note = col.text_input("How?", key=f"note-{payer}", placeholder="How? e.g. club card",
                          label_visibility="collapsed").strip()
    return (method, note) if note else None


def whos_owed(sink, done: list[Receipt], lines: list, event_id: str, paybacks: list[dict]) -> None:
    """The payback ledger: one line per payer with what they fronted, got back and are still owed,
    how they were paid, and Mark paid. A total line under it, like the books."""
    st.subheader("Who's owed")
    counts = Counter((r.payer or "").strip() or "(no payer)" for r in done)
    last = {str(p["payer"]): p for p in paybacks}
    head = st.columns(LEDGER, vertical_alignment="bottom")
    for col, (label, cls) in zip(head, [("Person", ""), ("Receipts", "num"), ("Fronted", "num"), ("Paid back", "num"),
                                        ("Still owed", "num"), ("Paid with", ""), ("", "")], strict=True):
        cell(col, label, f"head {cls}")
    for x in lines:  # rows never move: Mark paid leaves the person where they were
        row = st.columns(LEDGER, vertical_alignment="center")
        cell(row[0], f"<b>{html.escape(x.payer)}</b>")
        cell(row[1], str(counts[x.payer]), "num")
        cell(row[2], usd(x.fronted), "num")
        cell(row[3], usd(x.reimbursed), "num")
        cell(row[4], f'<b data-payer="{html.escape(x.payer)}">{usd(x.owed)}</b>', "num")
        if x.owed <= 0:
            p = last.get(x.payer)
            cell(row[5], html.escape(f"{p['method']}, {date.fromisoformat(str(p['date'])):%b} "
                                     f"{date.fromisoformat(str(p['date'])).day}") if p else "", "soft")
            pop = ss.get("just_paid") == x.payer  # coins burst out once, right after Mark paid
            # data-for makes each payer's burst its own markup, so it plays for every payer, not just the first.
            coins = COINS.replace('class="tly-coins"', f'class="tly-coins" data-for="{html.escape(x.payer)}"')
            cell(row[6], f'<span class="tly-paid-pop">✓ Paid</span>{coins}' if pop else "✓ Paid", "paid")
            continue
        if x.payer == "(no payer)":
            cell(row[5], "Set a payer in Review", "soft")
            continue
        how = paid_with(row[5], x.payer)
        if not row[6].button("Mark paid", key=f"paid-{x.payer}", type="primary", width="stretch", disabled=not how,
                             help=f"Records {md('$' + str(x.owed))} paid back to {x.payer} today."):
            continue
        if save_payback(sink, Reimbursement(event_id, x.payer, date.today(), x.owed, *how)):
            ss.just_paid = x.payer
            st.rerun()
    ss.pop("just_paid", None)
    tot = st.columns(LEDGER, vertical_alignment="center")
    cell(tot[0], "Total", "total")
    cell(tot[1], str(sum(counts[x.payer] for x in lines)), "total num")
    for col, field in zip(tot[2:5], ["fronted", "reimbursed", "owed"], strict=True):
        cell(col, usd(sum((getattr(x, field) for x in lines), Decimal("0"))), "total num")
    for col in tot[5:]:
        cell(col, "", "total")
    st.caption(f"Each Mark paid is saved to {sink.label}.")
    if paybacks:
        undo_last(sink, paybacks[-1], event_id)


def payback_form(sink, owing: list, event_id: str) -> None:
    """Pay back part of what's owed, on another date or by another method."""
    with st.expander("Pay back part of it, or by another method"), st.form("payback"):
        st.caption(f"Paid back only part, or on another day? Log it here and it's saved to {sink.label}!")
        c = st.columns(4)
        who = c[0].selectbox("Payer", [x.payer for x in owing])
        amount = c[1].text_input("Amount", "", help="Leave blank to pay back everything owed")
        method = c[2].selectbox("Method", METHODS)
        when = c[3].date_input("Date", value=date.today())
        note = st.text_input("Note (optional)")
        if not st.form_submit_button("Mark paid back"):
            return
        if method == "Other" and not note.strip():
            st.error("Paid some other way? Add a note on how, so the books say where the money went.")
            return
        owed = next(x.owed for x in owing if x.payer == who)
        amt, problem = validate(who, amount or str(owed), owed)
        if problem:
            st.error(md(problem))
            return
        if save_payback(sink, Reimbursement(event_id, who, when, amt, method, note)):
            st.success(md(f"Recorded {usd(amt)} paid back to {who}."))
            st.rerun()


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
    funder = st.selectbox("Funder", ["No funder", "My funder's rules", *EXAMPLES], key="funder",
                          help="Rules from whoever funds your event: student government, a department, a sponsor. "
                               "The examples are real rules from one student government, to show how it works.")
    if funder == "No funder":
        st.caption("No funder? No problem! Paying people back is all that's left.")
        return
    pack = my_funder() if funder == "My funder's rules" else EXAMPLES[funder]
    c = st.columns(3)
    attendees = int(c[0].number_input("Attendees", min_value=1, value=ss.event["attendees"]))
    req_text = c[1].text_input("Requested ($, optional)", "")
    applied_on = c[2].date_input("Applying on", value=date.today())
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
    st.markdown("**Last step:** download the funder report and attach it to your reimbursement request. "
                "Then hit **Finish event** at the bottom!")
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
    with st.container(border=True, key="whos-owed"):
        whos_owed(sink, done, lines, event.event_id, paybacks)
    with st.container(border=True, key="money-box"):
        st.subheader("Money in vs out")
        money_panel(done, {k: dec(v) for k, v in ss.income.items()})
    left_out = [r for r in ss.receipts.values() if r.status is Status.REJECTED]
    if left_out:
        with st.expander(f"Left out of the books ({len(left_out)})"):
            st.caption("These don't count anywhere! Not in expenses, who's owed, or the funder report.")
            html_table([{"Receipt": r.receipt_id, "Place": r.place, "Payer": r.payer or "(none)",
                         "Total": usd(r.total), "Why": r.review_note or ""} for r in left_out], numeric=("Total",))
    if owing:
        payback_form(sink, owing, event.event_id)
    else:
        st.success("Everyone's been paid back!")
    funder_rules(event, done, reimbursed)
    photos(event, done, lines)
    finish.finish_button(lines)


def photos(event: EventInfo, done: list[Receipt], lines) -> None:
    """Every receipt photo, labeled, in one PDF: for the funder, or to check prices against."""
    st.subheader("Receipt photos")
    st.caption("Every receipt photo in one PDF, all labeled. Handy for funders or your records!")
    owed = {x.payer: x.owed for x in lines}
    paid = {r.receipt_id: ("Not yet" if owed.get(r.payer or "(no payer)", 0) > 0 else "Yes") if r.payer else ""
            for r in done}
    images = ss.images  # the PDF is built when the button is clicked, not on every visit (0.7s with phone photos)
    st.download_button("Download receipt photos (PDF)", icon=":material/photo_library:", key="dl-photos",
                       file_name=f"{event.event_id}_receipt_photos.pdf", mime="application/pdf", on_click="ignore",
                       data=lambda: receipts_pdf(done, images, paid))
