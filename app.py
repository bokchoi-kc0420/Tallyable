"""Streamlit app: Upload -> Review -> Summary. Run with `streamlit run app.py`.

Core workflow only, no styling. Reads receipts with Claude when ANTHROPIC_API_KEY
is in .env, otherwise with the stub (fake answer key plus planted misreads).
"""
from __future__ import annotations

import os
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
import streamlit as st

from treasurer import closeout as co
from treasurer.checks import Severity, can_approve, run_checks
from treasurer.extract import ExtractionError
from treasurer.models import LineItem, Receipt, Status
from treasurer.post import LocalCsvSink, event_totals
from treasurer.reader import make_extractor
from treasurer.reimburse import METHODS, Reimbursement, totals_by_payer, validate
from treasurer.runlog import log_run, minutes, read_runs
from treasurer.sheets import EventInfo, GoogleSheetsSink

ROOT = Path(__file__).parent
OUT = Path(os.getenv("TALLYABLE_OUTPUT_DIR") or ROOT / "output")
FAKE = ROOT / "fake_event"
EVENT_ID = "EVT-FAKE-01"
PAYERS = ["", "Member A", "Member B", "Member C", "Member D"]
EVENT = EventInfo(EVENT_ID, "Fall Mentor Mixer (FAKE)", date(2026, 11, 14))
ICON = {Status.DRAFTED: "⏳ drafted", Status.APPROVED: "✅ approved", Status.REJECTED: "❌ rejected",
        Status.POSTED: "📤 posted"}

st.set_page_config(page_title="Tallyable", layout="wide")
ss = st.session_state
ss.setdefault("receipts", {})   # receipt_id -> Receipt
ss.setdefault("images", {})     # receipt_id -> bytes
ss.setdefault("started", time.time())
ss.setdefault("edits", 0)
ss.setdefault("drafted_at", None)    # first Draft click, for the run log
ss.setdefault("review_started", None)
ss.setdefault("income", {})
RUN_LOG = OUT / "run_log.csv"


def dec(text: str, default: str = "0") -> Decimal:
    try:
        return Decimal(str(text).strip() or default)
    except InvalidOperation:
        return Decimal(default)


def next_id(filename: str | None = None) -> str:
    """Use the file name (R03.jpg -> R03) when free, so ids match the answer key."""
    stem = Path(filename).stem.upper() if filename else ""
    if stem and stem not in ss.receipts:
        return stem
    n = len(ss.receipts) + 1
    while f"R{n:02d}" in ss.receipts:
        n += 1
    return f"R{n:02d}"


def get_sink():
    """Google Sheets if it is set up, else the local CSV. Returns (sink, error)."""
    try:
        return GoogleSheetsSink.from_env(ROOT) or LocalCsvSink(OUT / "transactions.csv"), None
    except Exception as e:  # bad key file, sheet not shared, no network
        return LocalCsvSink(OUT / "transactions.csv"), f"Could not open the Google Sheet, so using local CSV instead: {e}"


def md(text: str) -> str:
    """Escape $ so Streamlit does not render dollar amounts as LaTeX."""
    return text.replace("$", "\\$")


page = st.sidebar.radio("Step", ["1. Upload", "2. Review", "3. Summary", "4. Close out"])
st.sidebar.caption(f"Event: {EVENT.name} · {len(ss.receipts)} receipts")

# ---------------- Screen 1: Upload ----------------
if page == "1. Upload":
    st.header("Upload receipts")
    ex, reader = make_extractor()
    if reader == "claude":
        st.success(f"Reading receipts with Claude ({ex.model}).")
    else:
        st.warning("No API key found, so receipts are read by the stub, which only knows the fake event's "
                   "answer key. Add ANTHROPIC_API_KEY to .env and restart to use Claude.")
    files = st.file_uploader("Receipt photos", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
    if st.button("Use the fake event's 14 receipts instead"):
        files = None
        ss.demo = sorted((FAKE / "receipts").glob("*.jpg"))
    sources = [(f.name, f.getvalue()) for f in files] if files else [(p.name, p.read_bytes()) for p in ss.get("demo", [])]

    payers = {}
    for name, _ in sources:
        payers[name] = st.selectbox(f"Payer for {name}", PAYERS, key=f"payer-{name}")

    if sources and st.button("Draft rows", type="primary"):
        bar = st.progress(0.0)
        for n, (name, data) in enumerate(sources):
            rid = next_id(name)
            try:
                r = ex.extract(data, name, EVENT_ID, rid)
                ss.receipts[rid] = r.model_copy(update={"payer": payers[name] or None, "image_file": name})
                ss.images[rid] = data
            except ExtractionError as e:
                st.error(str(e))
            bar.progress((n + 1) / len(sources))
        ss.demo = []
        ss.drafted_at = ss.drafted_at or time.time()
        cost = f" · about ${ex.cost():.3f} in API calls" if reader == "claude" else ""
        st.success(md(f"Drafted. Go to Review.{cost}"))

    with st.expander("Add a purchase with no photo (cash, lost receipt)"):
        with st.form("manual"):
            place = st.text_input("Place")
            d = st.date_input("Date", value=date(2026, 11, 14))
            payer = st.selectbox("Payer", PAYERS)
            item = st.text_input("Item")
            cat = st.selectbox("Category", ["Food", "Drink", "Other"])
            unit = st.number_input("Unit", min_value=1, value=1)
            price = st.text_input("Price per unit", "0.00")
            total = st.text_input("Total", "0.00")
            if st.form_submit_button("Add") and place and item:
                rid = next_id()
                ss.receipts[rid] = Receipt(receipt_id=rid, event_id=EVENT_ID, place=place, date=d,
                                           payer=payer or None, total=dec(total),
                                           items=[LineItem(category=cat, item=item, unit=int(unit), price=dec(price))])
                st.success(f"Added {rid}")

# ---------------- Screen 2: Review ----------------
elif page == "2. Review":
    st.header("Review")
    if not ss.receipts:
        st.info("Nothing to review yet. Upload receipts first.")
        st.stop()
    ss.review_started = ss.review_started or time.time()
    flags = run_checks(list(ss.receipts.values()))
    labels = {rid: f"{rid} · {r.place} · {ICON[r.status]}" + (" ⚠️" if flags[rid] else "")
              for rid, r in ss.receipts.items()}
    rid = st.sidebar.radio("Receipts", list(labels), format_func=labels.get)
    r = ss.receipts[rid]

    left, right = st.columns([2, 3])
    with left:
        if rid in ss.images:
            st.image(ss.images[rid], width="stretch")
        else:
            st.warning("No photo for this receipt.")
    with right:
        for f in flags[rid]:
            {Severity.BLOCK: st.error, Severity.WARN: st.warning, Severity.INFO: st.info}[f.severity](md(f.message))
        c1, c2, c3 = st.columns(3)
        place = c1.text_input("Place", r.place, key=f"place-{rid}")
        d = c2.date_input("Date", r.date, key=f"date-{rid}")
        payer = c3.selectbox("Payer", PAYERS, index=PAYERS.index(r.payer or ""), key=f"payer-{rid}")
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
            if new != r:
                ss.edits += 1
                ss.receipts[rid] = new
                st.rerun()  # re-run checks on the edited values
        except (ValueError, TypeError) as e:
            st.error(f"Fix the line items: {e}")

        st.caption(md(f"Items + tax + tip = ${r.computed_total} · posts ${r.posted_amount}"))
        note = st.text_input("Override note (needed to approve with a red flag)", r.review_note or "",
                             key=f"note-{rid}")
        b1, b2 = st.columns(2)
        locked = r.status is Status.POSTED
        if b1.button("Approve", type="primary", disabled=locked or not can_approve(flags[rid], note)):
            ss.receipts[rid] = r.model_copy(update={"status": Status.APPROVED, "review_note": note or None})
            st.rerun()
        if b2.button("Reject", disabled=locked):
            ss.receipts[rid] = r.model_copy(update={"status": Status.REJECTED, "review_note": note or None})
            st.rerun()

# ---------------- Screen 3: Summary ----------------
elif page == "3. Summary":
    st.header("Summary and push")
    receipts = list(ss.receipts.values())
    st.subheader("Income")
    c = st.columns(4)
    income = {k: dec(c[n].text_input(k, ss.income.get(k, "0.00"), key=f"income-{k}")) for n, k in
              enumerate(["Zelle", "Venmo", "Cash", "National KSEA funding"])}
    ss.income = {k: str(v) for k, v in income.items()}
    t = event_totals(receipts, income)
    m = st.columns(4)
    m[0].metric("Income", f"${t['income']}")
    m[1].metric("Expenses (approved)", f"${t['expenses']}")
    m[2].metric("Net", f"${t['net']}")
    m[3].metric("Margin", f"{t['margin_pct']}%", help="Target: 10% or more")

    rows = [{"receipt": r.receipt_id, "place": r.place, "payer": r.payer, "status": r.status.value,
             "posts": str(r.posted_amount) if r.status in (Status.APPROVED, Status.POSTED) else "",
             "note": r.review_note or ""} for r in receipts]
    st.dataframe(pd.DataFrame(rows), width="stretch")

    waiting = [r.receipt_id for r in receipts if r.status is Status.DRAFTED]
    if waiting:
        st.warning(f"Review these first: {', '.join(waiting)}")
    sink, err = get_sink()
    if err:
        st.error(err)
    if sink.label != "Google Sheets":
        st.caption("Google Sheets is not set up (see docs/google_sheets_setup.md), so Push writes a local CSV.")
    if st.button(f"Push to {sink.label}", type="primary", disabled=bool(waiting) or not receipts):
        written = sink.post(receipts, EVENT, income)
        for rid in written:
            ss.receipts[rid] = ss.receipts[rid].model_copy(update={"status": Status.POSTED})
        if written:
            now, flags = time.time(), run_checks(receipts)
            ex, reader = make_extractor()
            log_run(RUN_LOG, {
                "event_id": EVENT_ID, "reader": reader, "model": getattr(ex, "model", "stub"),
                "receipts": len(receipts), "posted": len(written), "edits": ss.edits,
                "overrides": sum(1 for r in receipts if r.review_note and r.status is not Status.REJECTED
                                 and any(f.severity is Severity.BLOCK for f in flags[r.receipt_id])),
                "minutes_draft_to_push": minutes(ss.drafted_at, now),
                "minutes_review_to_push": minutes(ss.review_started, now),
            })
        st.success(f"Posted {len(written)} receipts to {sink.label}" if written else "Nothing new to post.")

    st.subheader("Run stats")
    s = st.columns(3)
    s[0].metric("Minutes in tool", f"{(time.time() - ss.started) / 60:.1f}")
    s[1].metric("Edits to drafts", ss.edits)
    s[2].metric("Flags open", sum(1 for fl in run_checks(receipts).values() for f in fl if f.severity is Severity.BLOCK)
                if receipts else 0)
    runs = read_runs(RUN_LOG)
    if runs:
        st.caption(f"Past runs, from {RUN_LOG}")
        st.dataframe(pd.DataFrame(runs), width="stretch")

# ---------------- Screen 4: Close out ----------------
else:
    st.header("Close out the event")
    done = [r for r in ss.receipts.values() if r.status in (Status.APPROVED, Status.POSTED)]
    if not done:
        st.info("Approve some receipts first.")
        st.stop()
    waiting = [r.receipt_id for r in ss.receipts.values() if r.status is Status.DRAFTED]
    if waiting:
        st.warning(f"Still drafted, so left out below: {', '.join(waiting)}")

    st.subheader("Who is owed")
    sink, err = get_sink()
    if err:
        st.error(err)
    reimbursed = totals_by_payer(sink.reimbursements(), EVENT_ID)
    lines = co.payer_summary(done, reimbursed)
    st.dataframe(pd.DataFrame([{"payer": x.payer, "fronted": str(x.fronted), "reimbursed": str(x.reimbursed),
                                "owed": str(x.owed)} for x in lines]), width="stretch")
    owing = [x for x in lines if x.owed > 0]
    if owing:
        with st.form("payback"):
            st.caption(f"Mark a payback. It is saved to {sink.label} and shows in the ledger.")
            c = st.columns(4)
            who = c[0].selectbox("Payer", [x.payer for x in owing])
            amount = c[1].text_input("Amount", "", help="Leave blank to pay back everything owed")
            method = c[2].selectbox("Method", METHODS)
            when = c[3].date_input("Date", value=date.today())
            note = st.text_input("Note (optional)")
            if st.form_submit_button("Mark paid back"):
                owed = next(x.owed for x in owing if x.payer == who)
                amt, problem = validate(who, amount or str(owed), owed)
                if problem:
                    st.error(md(problem))
                else:
                    sink.record_reimbursement(Reimbursement(EVENT_ID, who, when, amt, method, note))
                    st.success(md(f"Recorded ${amt} paid back to {who}."))
                    st.rerun()
    else:
        st.success("Everyone has been paid back.")

    st.subheader("Funder rules")
    c = st.columns(4)
    pack = {"CFC": co.CFC, "ORG": co.ORG}[c[0].selectbox("Funder", ["CFC", "ORG"])]
    attendees = int(c[1].number_input("Attendees", min_value=1, value=45))
    req_text = c[2].text_input("Requested ($, optional)", "")
    applied_on = c[3].date_input("Applying on", value=date.today())
    requested = dec(req_text) if req_text.strip() else None
    event = co.Event(EVENT_ID, EVENT.name, EVENT.date, attendees=attendees)
    flags = co.check_funder_rules(event, done, pack, requested, applied_on)
    due = co.report_due(event, pack)
    if due:
        st.caption(f"{pack.name}: report due {due.isoformat()}")
    if not flags:
        st.success(f"No {pack.name} rule flags.")
    for f in flags:
        {Severity.BLOCK: st.error, Severity.WARN: st.warning, Severity.INFO: st.info}[f.severity](md(f.message))
    for note in pack.notes:
        st.caption(note)

    st.download_button("Download funder report (CSV)", file_name=f"{EVENT_ID}_{pack.name.split()[-1]}_report.csv",
                       data=co.funder_report_csv(event, done, pack, requested, applied_on, reimbursed),
                       mime="text/csv")
