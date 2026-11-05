"""Step 4: pay back whoever fronted money, and check the event against a funder's rules."""
from __future__ import annotations

import html
from datetime import date

import streamlit as st

from treasurer import closeout as co
from treasurer.checks import Severity
from treasurer.models import Receipt, Status
from treasurer.reimburse import METHODS, Reimbursement, totals_by_payer, validate
from treasurer.sheets import EventInfo
from ui.common import ART, dec, get_sink, guide, html_table, md, money_panel, saved_reimbursements, ss, step_bar, usd

EXAMPLES = {"Example: UC Davis CFC": co.CFC, "Example: UC Davis ORG": co.ORG}


def save_payback(sink, payback: Reimbursement) -> bool:
    try:
        sink.record_reimbursement(payback)
    except Exception as e:
        st.error(f"Payback not saved: {e}. Try again.")
        return False
    return True


def whos_owed(sink, done: list[Receipt], lines: list, event_id: str) -> None:
    """One row per payer: initials, what they fronted, what's still owed, and Mark paid."""
    owing = [x for x in lines if x.owed > 0]
    st.subheader("Who's owed")
    cap = st.columns([3, 2], vertical_alignment="bottom")
    cap[0].caption(f"Mark paid saves the payback to {sink.label}. It shows in the ledger.")
    quick = cap[1].selectbox("Paid back with", METHODS, key="quick-method") if owing else METHODS[0]
    counts: dict[str, int] = {}
    for r in done:
        who = (r.payer or "").strip() or "(no payer)"
        counts[who] = counts.get(who, 0) + 1
    for x in lines:
        row = st.columns([0.5, 2, 1.1, 1.5], vertical_alignment="center")
        initials = "".join(w[0] for w in x.payer.split()[:2] if w[0].isalnum()).upper() or "?"
        row[0].markdown(f'<span class="tly-avatar">{html.escape(initials)}</span>', unsafe_allow_html=True)
        n = counts.get(x.payer, 0)
        row[1].markdown(md(f"**{x.payer}**  \n:gray[{n} receipt{'s' if n != 1 else ''} · fronted ${x.fronted}]"))
        row[2].markdown(f'<span class="tly-owed">{md("$" + str(x.owed))}</span>', unsafe_allow_html=True)
        if x.owed <= 0:
            row[3].markdown(":green-badge[✓ Paid]")
            continue
        if x.payer == "(no payer)":
            row[3].caption("Set a payer in Review")
            continue
        if not row[3].button("Mark paid", key=f"paid-{x.payer}", icon=":material/check:", width="stretch",
                             help=f"Records {md('$' + str(x.owed))} paid back to {x.payer} today."):
            continue
        if save_payback(sink, Reimbursement(event_id, x.payer, date.today(), x.owed, quick, "")):
            st.rerun()


def payback_form(sink, owing: list, event_id: str) -> None:
    """Pay back part of what's owed, on another date or by another method."""
    with st.expander("Pay back part of it, or by another method"), st.form("payback"):
        st.caption(f"Mark a payback. It is saved to {sink.label} and shows in the ledger.")
        c = st.columns(4)
        who = c[0].selectbox("Payer", [x.payer for x in owing])
        amount = c[1].text_input("Amount", "", help="Leave blank to pay back everything owed")
        method = c[2].selectbox("Method", METHODS)
        when = c[3].date_input("Date", value=date.today())
        note = st.text_input("Note (optional)")
        if not st.form_submit_button("Mark paid back"):
            return
        owed = next(x.owed for x in owing if x.payer == who)
        amt, problem = validate(who, amount or str(owed), owed)
        if problem:
            st.error(md(problem))
            return
        if save_payback(sink, Reimbursement(event_id, who, when, amt, method, note)):
            st.success(md(f"Recorded ${amt} paid back to {who}."))
            st.rerun()


def my_funder() -> co.RulePack:
    """A form for the club's own funder rules. Saved with the event so it's filled in next time."""
    saved = ss.event.get("funder", {})
    with st.container(border=True, key="my-funder"):
        st.caption("Fill in what your funder asks for. Leave a box empty if they don't have that rule.")
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
                               "The examples are one school's real rules, to show how it works.")
    if funder == "No funder":
        st.caption("No funder rules checked. Who is owed (above) and the books from Summary are all you need. "
                   "This event stays saved: reopen it anytime under Past events.")
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
    st.metric("Most you can request", f"${most}", border=True)
    with st.expander("How that was worked out"):
        for s in steps:
            st.write(md(s))
    due = co.report_due(event, pack)
    if due:
        st.caption(f"{pack.name}: report due {due.isoformat()}")
    if not flags:
        st.success(f"No {pack.name} rule flags.")
    for f in flags:
        {Severity.BLOCK: st.error, Severity.WARN: st.warning, Severity.INFO: st.info}[f.severity](md(f.message))
    for note in pack.notes:
        st.caption(note)

    st.divider()
    st.markdown("**Last step:** download the funder report and attach it to your reimbursement request. "
                "When everyone is paid back, start the next event from the sidebar. This event stays saved: "
                "reopen it anytime under **Past events**.")
    st.download_button("Download funder report (CSV)", type="primary", icon=":material/download:",
                       file_name=f"{info.event_id}_{pack.name.split()[-1]}_report.csv",
                       data=co.funder_report_csv(event, done, pack, requested, applied_on, reimbursed),
                       mime="text/csv")


def show(event: EventInfo) -> None:
    st.header("Close out the event")
    step_bar("4. Close out")
    done = [r for r in ss.receipts.values() if r.status in (Status.APPROVED, Status.POSTED)]
    if not done:
        guide("Nothing to close out yet!", "Approve some receipts on Review, then I'll show who's owed.",
              key="close-empty", to="2. Review")
        return
    waiting = [r.receipt_id for r in ss.receipts.values() if r.status is Status.DRAFTED]
    if waiting:
        st.warning(f"Still drafted, so left out below: {', '.join(waiting)}")
    else:
        with st.container(key="mascot-cheer"):
            st.image(str(ART / "tally-cheer.png"), width=170)
        rejected = len(ss.receipts) - len(done)
        cheer = f"All {len(done)} receipts approved!" if not rejected else f"All reviewed! {len(done)} approved, {rejected} rejected."
        st.markdown(f'<p class="tly-cheer">{cheer}</p>', unsafe_allow_html=True)

    sink, err = get_sink()
    if err:
        st.error(err)
    reimbursed = totals_by_payer(saved_reimbursements(sink), event.event_id)
    lines = co.payer_summary(done, reimbursed)
    owing = [x for x in lines if x.owed > 0]
    left, right = st.columns([5, 3], gap="medium")
    with left.container(border=True):
        whos_owed(sink, done, lines, event.event_id)
    with right.container(border=True):
        st.subheader("Money in vs out")
        money_panel(done, {k: dec(v) for k, v in ss.income.items()})
    with st.expander("Payback details"):
        html_table([{"Payer": x.payer, "Fronted": usd(x.fronted), "Paid back": usd(x.reimbursed),
                     "Owed": usd(x.owed)} for x in lines], numeric=("Fronted", "Paid back", "Owed"))
    if owing:
        payback_form(sink, owing, event.event_id)
    else:
        st.success("Everyone has been paid back.")
    funder_rules(event, done, reimbursed)
