"""Streamlit app: Upload -> Review -> Summary. Run with `streamlit run app.py`.

Core workflow only, no styling. The AI step is the stub until week 2.
"""
from __future__ import annotations

import time
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
import streamlit as st

from treasurer.checks import Severity, can_approve, run_checks
from treasurer.extract import ExtractionError, StubExtractor
from treasurer.models import LineItem, Receipt, Status
from treasurer.post import LocalCsvSink, event_totals

ROOT = Path(__file__).parent
FAKE = ROOT / "fake_event"
EVENT_ID = "EVT-FAKE-01"
PAYERS = ["", "Member A", "Member B", "Member C", "Member D"]
SINK = LocalCsvSink(ROOT / "output" / "transactions.csv")
ICON = {Status.DRAFTED: "⏳ drafted", Status.APPROVED: "✅ approved", Status.REJECTED: "❌ rejected",
        Status.POSTED: "📤 posted"}

st.set_page_config(page_title="Tallyable", layout="wide")
ss = st.session_state
ss.setdefault("receipts", {})   # receipt_id -> Receipt
ss.setdefault("images", {})     # receipt_id -> bytes
ss.setdefault("started", time.time())
ss.setdefault("edits", 0)


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


def md(text: str) -> str:
    """Escape $ so Streamlit does not render dollar amounts as LaTeX."""
    return text.replace("$", "\\$")


page = st.sidebar.radio("Step", ["1. Upload", "2. Review", "3. Summary"])
st.sidebar.caption(f"Event: Fall Mentor Mixer (FAKE) · {len(ss.receipts)} receipts")

# ---------------- Screen 1: Upload ----------------
if page == "1. Upload":
    st.header("Upload receipts")
    files = st.file_uploader("Receipt photos", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
    if st.button("Use the fake event's 14 receipts instead"):
        files = None
        ss.demo = sorted((FAKE / "receipts").glob("*.jpg"))
    sources = [(f.name, f.getvalue()) for f in files] if files else [(p.name, p.read_bytes()) for p in ss.get("demo", [])]

    payers = {}
    for name, _ in sources:
        payers[name] = st.selectbox(f"Payer for {name}", PAYERS, key=f"payer-{name}")

    if sources and st.button("Draft rows", type="primary"):
        ex = StubExtractor(FAKE / "answer_key.csv")
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
        st.success("Drafted. Go to Review.")

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
else:
    st.header("Summary and push")
    receipts = list(ss.receipts.values())
    st.subheader("Income")
    c = st.columns(4)
    income = {k: dec(c[n].text_input(k, "0.00")) for n, k in
              enumerate(["Zelle", "Venmo", "Cash", "National KSEA funding"])}
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
    if st.button("Push (local CSV until Sheets is wired up)", type="primary", disabled=bool(waiting) or not receipts):
        written = SINK.post(receipts)
        for rid in written:
            ss.receipts[rid] = ss.receipts[rid].model_copy(update={"status": Status.POSTED})
        st.success(f"Posted {len(written)} receipts to {SINK.path.name}" if written else "Nothing new to post.")

    st.subheader("Run stats")
    s = st.columns(3)
    s[0].metric("Minutes in tool", f"{(time.time() - ss.started) / 60:.1f}")
    s[1].metric("Edits to drafts", ss.edits)
    s[2].metric("Flags open", sum(1 for fl in run_checks(receipts).values() for f in fl if f.severity is Severity.BLOCK)
                if receipts else 0)
