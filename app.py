"""Streamlit app: Upload -> Review -> Summary. Run with `streamlit run app.py`.

Core workflow only, no styling. Reads receipts with Claude when ANTHROPIC_API_KEY
is in .env, otherwise with the stub (fake answer key plus planted misreads).
"""
from __future__ import annotations

import hmac
import os
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
import streamlit as st

from treasurer import closeout as co
from treasurer import session_store
from treasurer.checks import Severity, can_approve, run_checks
from treasurer.extract import ExtractionError
from treasurer.images import UPLOAD_TYPES, UnsupportedFile, prepare
from treasurer.models import LineItem, Receipt, Status
from treasurer.post import LocalCsvSink, event_totals
from treasurer.reader import make_extractor
from treasurer.reimburse import METHODS, Reimbursement, totals_by_payer, validate
from treasurer.runlog import log_run, minutes, read_runs
from treasurer.sheets import EventInfo, GoogleSheetsSink, grid_to_csv, local_views

ROOT = Path(__file__).parent
OUT = Path(os.getenv("TALLYABLE_OUTPUT_DIR") or ROOT / "output")
FAKE = ROOT / "fake_event"
DEFAULT_EVENT = {"event_id": "EVT-FAKE-01", "name": "Fall Mentor Mixer (FAKE)", "date": date(2026, 11, 14),
                 "attendees": 45, "members": "Member A, Member B, Member C, Member D"}
ICON = {Status.DRAFTED: "⏳ drafted", Status.APPROVED: "✅ approved", Status.REJECTED: "❌ rejected",
        Status.POSTED: "📤 posted"}

st.set_page_config(page_title="Tallyable", layout="wide")
ss = st.session_state


def load_cloud_secrets() -> dict | None:
    """On Streamlit Cloud, settings live in st.secrets instead of .env. Copy the plain
    ones into the environment so the rest of the code reads them the same way, and
    return the Google key table if there is one. Locally, with no secrets file, this
    does nothing."""
    try:
        for k, v in st.secrets.items():
            if isinstance(v, str):
                os.environ.setdefault(k, v)
        return dict(st.secrets["gcp_service_account"]) if "gcp_service_account" in st.secrets else None
    except Exception:  # no secrets.toml: running locally with .env
        return None


GCP_KEY = load_cloud_secrets()

# Password gate. Only on when APP_PASSWORD is set (always set it before deploying:
# the app can spend API credit). compare_digest avoids leaking the password by timing.
if os.getenv("APP_PASSWORD") and not ss.get("authed"):
    st.header("Tallyable")
    pw = st.text_input("Password", type="password")
    if pw and hmac.compare_digest(pw.encode(), os.environ["APP_PASSWORD"].encode()):
        ss.authed = True
        st.rerun()
    if pw:
        st.error("Wrong password.")
    st.stop()

ss.setdefault("receipts", {})   # receipt_id -> Receipt
ss.setdefault("images", {})     # receipt_id -> (bytes, media type) as sent to the reader
ss.setdefault("notes", {})      # receipt_id -> photo warnings (blurry, rotated)
ss.setdefault("failed", {})     # file name -> (bytes, reason) for files that could not be read
ss.setdefault("started", time.time())
ss.setdefault("edits", 0)
ss.setdefault("drafted_at", None)    # first Draft click, for the run log
ss.setdefault("review_started", None)
ss.setdefault("income", {})
RUN_LOG = OUT / "run_log.csv"
SESSION_FILE = OUT / "session.json"
SAVED_KEYS = ("event", "receipts", "images", "notes", "edits", "income", "drafted_at", "review_started", "started")


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
        return GoogleSheetsSink.from_env(ROOT, GCP_KEY) or LocalCsvSink(OUT / "transactions.csv"), None
    except Exception as e:  # bad key file, sheet not shared, no network
        return LocalCsvSink(OUT / "transactions.csv"), f"Could not open the Google Sheet, so using local CSV instead: {e}"


def manual_form(key: str, image_file: str | None = None, data: tuple[bytes, str] | None = None) -> None:
    """Type a one-item receipt by hand. Used for lost receipts and for photos the
    reader could not handle. With `image_file`, the photo stays attached as evidence."""
    with st.form(key):
        c = st.columns(3)
        place = c[0].text_input("Place")
        d = c[1].date_input("Date", value=EVENT.date)
        payer = c[2].selectbox("Payer", PAYERS)
        c = st.columns(3)
        item = c[0].text_input("Item")
        cat = c[1].selectbox("Category", ["Food", "Drink", "Other"])
        unit = c[2].number_input("Unit", min_value=1, value=1)
        c = st.columns(4)
        price = c[0].text_input("Price per unit", "0.00")
        tax = c[1].text_input("Tax", "0.00")
        tip = c[2].text_input("Tip", "0.00")
        total = c[3].text_input("Total", "0.00")
        st.caption("One line here; add more lines on the Review screen.")
        if st.form_submit_button("Add") and place and item:
            rid = next_id(image_file)
            ss.receipts[rid] = Receipt(receipt_id=rid, event_id=EVENT_ID, place=place, date=d,
                                       payer=payer or None, tax=dec(tax), tip=dec(tip), total=dec(total),
                                       image_file=image_file,
                                       items=[LineItem(category=cat, item=item, unit=int(unit), price=dec(price))])
            if data:
                ss.images[rid] = data
            if image_file:
                ss.failed.pop(image_file, None)
            st.success(f"Added {rid}. Check it on Review.")
            st.rerun()


def md(text: str) -> str:
    """Escape $ so Streamlit does not render dollar amounts as LaTeX."""
    return text.replace("$", "\\$")


def event_id_for(name: str, d: date) -> str:
    slug = "".join(ch for ch in name.upper() if ch.isalnum())[:12] or "EVENT"
    return f"EVT-{d.isoformat()}-{slug}"


def start_new_event() -> None:
    for k in ("receipts", "images", "notes", "failed"):
        ss[k] = {}
    ss.edits, ss.drafted_at, ss.review_started, ss.income = 0, None, None, {}
    ss.started = time.time()
    session_store.clear(SESSION_FILE)


def save_session() -> None:
    """Write the session to disk when it changed since the last save."""
    if not ss.receipts:
        return
    state = {k: ss[k] for k in SAVED_KEYS}
    text = session_store.dump(state)
    if text != ss.get("_saved"):
        session_store.save(SESSION_FILE, state)
        ss._saved = text


ss.setdefault("event", dict(DEFAULT_EVENT))
page = st.sidebar.radio("Step", ["1. Upload", "2. Review", "3. Summary", "4. Close out"])
with st.sidebar.expander("Event", expanded=not ss.receipts and ss.event == DEFAULT_EVENT):
    locked = bool(ss.receipts)
    name = st.text_input("Event name", ss.event["name"], disabled=locked)
    d = st.date_input("Event date", ss.event["date"], disabled=locked)
    attendees = int(st.number_input("Attendees", min_value=1, value=ss.event["attendees"]))
    members = st.text_input("Members who might pay", ss.event["members"], help="Comma separated")
    changed = name != ss.event["name"] or d != ss.event["date"]
    ss.event.update(name=name, date=d, attendees=attendees, members=members,
                    event_id=event_id_for(name, d) if changed else ss.event["event_id"])
    if locked:
        st.caption("Name and date are locked once receipts are drafted.")
        if st.checkbox("I'm done with this event") and st.button("Start a new event"):
            start_new_event()
            st.rerun()
EVENT_ID = ss.event["event_id"]
EVENT = EventInfo(EVENT_ID, ss.event["name"], ss.event["date"], ss.event["attendees"])
PAYERS = ["", *[m.strip() for m in ss.event["members"].split(",") if m.strip()]]
st.sidebar.caption(f"Event: {EVENT.name} · {len(ss.receipts)} receipts")

# ---------------- Screen 1: Upload ----------------
if page == "1. Upload":
    st.header("Upload receipts")
    if not ss.receipts and SESSION_FILE.exists():
        saved = session_store.load(SESSION_FILE)
        if saved and saved["receipts"]:
            n = len(saved["receipts"])
            done = sum(1 for r in saved["receipts"].values() if r.status is not Status.DRAFTED)
            st.info(f"You have a saved session for {saved['event']['name']}: {n} receipts, {done} reviewed.")
            if st.button("Resume where I left off"):
                for k, v in saved.items():
                    ss[k] = v
                st.rerun()
    ex, reader = make_extractor()
    if reader == "claude":
        st.success(f"Reading receipts with Claude ({ex.model}).")
    else:
        st.warning("No API key found, so receipts are read by the stub, which only knows the fake event's "
                   "answer key. Add ANTHROPIC_API_KEY to .env and restart to use Claude.")
    files = st.file_uploader("Receipt photos or PDFs", type=UPLOAD_TYPES, accept_multiple_files=True)
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
                f = prepare(data, name)
                r = ex.extract(f.data, f.filename, EVENT_ID, rid)
                ss.receipts[rid] = r.model_copy(update={"payer": payers[name] or None, "image_file": name})
                ss.images[rid] = (f.data, f.media_type)
                notes = f.warnings + ([f"Reader's note: {r.review_note}"] if r.review_note else [])
                if notes:
                    ss.notes[rid] = notes
                ss.failed.pop(name, None)
            except UnsupportedFile as e:
                ss.failed[name] = (None, str(e))
            except ExtractionError as e:
                ss.failed[name] = ((f.data, f.media_type), f"{e} You can type it in by hand below.")
            bar.progress((n + 1) / len(sources))
        ss.demo = []
        ss.drafted_at = ss.drafted_at or time.time()
        cost = f" · about ${ex.cost():.3f} in API calls" if reader == "claude" else ""
        st.success(md(f"Drafted. Go to Review.{cost}"))

    for name, (data, reason) in list(ss.failed.items()):
        st.error(md(f"{name}: {reason}"))
        with st.expander(f"Enter {name} by hand"):
            if data and data[1].startswith("image/"):
                st.image(data[0], width=360)
            manual_form(f"manual-{name}", image_file=name, data=data)

    with st.expander("Add a purchase with no photo (cash, lost receipt)"):
        manual_form("manual")

# ---------------- Screen 2: Review ----------------
elif page == "2. Review":
    st.header("Review")
    if not ss.receipts:
        st.info("Nothing to review yet. Upload receipts first.")
        st.stop()
    ss.review_started = ss.review_started or time.time()
    flags = run_checks(list(ss.receipts.values()))
    reviewed = sum(1 for x in ss.receipts.values() if x.status is not Status.DRAFTED)
    st.progress(reviewed / len(ss.receipts), text=f"{reviewed} of {len(ss.receipts)} reviewed")

    def attention(x_rid: str) -> bool:
        return any(f.severity is not Severity.INFO for f in flags[x_rid]) or bool(ss.notes.get(x_rid))

    show = st.sidebar.selectbox("Show", ["All", "Not reviewed yet", "Needs attention"])
    ids = [x for x, rec in ss.receipts.items()
           if show == "All" or (show == "Not reviewed yet" and rec.status is Status.DRAFTED)
           or (show == "Needs attention" and attention(x))]
    if not ids:
        st.success("Nothing left in this view.")
        st.stop()
    labels = {x: f"{x} · {ss.receipts[x].place} · {ICON[ss.receipts[x].status]}" + (" ⚠️" if attention(x) else "")
              for x in ids}
    if ss.get("next_pick") in ids:  # set by "Approve" so the next receipt opens by itself
        ss["review-pick"] = ss.pop("next_pick")
    elif ss.get("review-pick") not in ids:
        ss["review-pick"] = ids[0]
    rid = st.sidebar.radio("Receipts", ids, format_func=labels.get, key="review-pick")
    r = ss.receipts[rid]


    def next_drafted(after: str) -> str | None:
        order = list(ss.receipts)
        rest = order[order.index(after) + 1:] + order[:order.index(after)]
        return next((x for x in rest if ss.receipts[x].status is Status.DRAFTED), None)

    left, right = st.columns([2, 3])
    with left:
        if rid in ss.images and ss.images[rid][1] == "application/pdf":
            st.info("PDF receipt.")
            st.download_button("Open the PDF", ss.images[rid][0], file_name=f"{rid}.pdf", mime="application/pdf")
        elif rid in ss.images:
            st.image(ss.images[rid][0], width="stretch")
        else:
            st.warning("No photo for this receipt.")
    with right:
        for note in ss.notes.get(rid, []):
            st.warning(md(note))
        for f in flags[rid]:
            {Severity.BLOCK: st.error, Severity.WARN: st.warning, Severity.INFO: st.info}[f.severity](md(f.message))
        c1, c2, c3 = st.columns(3)
        place = c1.text_input("Place", r.place, key=f"place-{rid}")
        d = c2.date_input("Date", r.date, key=f"date-{rid}")
        options = PAYERS if (r.payer or "") in PAYERS else [*PAYERS, r.payer]
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
            if new != r:
                ss.edits += 1
                ss.receipts[rid] = new
                st.rerun()  # re-run checks on the edited values
        except (ValueError, TypeError) as e:
            st.error(f"Fix the line items: {e}")

        st.caption(md(f"Items + tax + tip = ${r.computed_total} · posts ${r.posted_amount}"))
        note = st.text_input("Override note (needed to approve with a red flag)", r.review_note or "",
                             key=f"note-{rid}")
        b1, b2, b3 = st.columns(3)
        locked = r.status is Status.POSTED
        if locked:
            st.caption("Posted to the books, so it can't change here. Fix it in the sheet's Transactions tab.")
        if b1.button("Approve", type="primary", disabled=locked or not can_approve(flags[rid], note)):
            ss.receipts[rid] = r.model_copy(update={"status": Status.APPROVED, "review_note": note or None})
            ss.next_pick = next_drafted(rid)
            st.rerun()
        if b2.button("Reject", disabled=locked):
            ss.receipts[rid] = r.model_copy(update={"status": Status.REJECTED, "review_note": note or None})
            ss.next_pick = next_drafted(rid)
            st.rerun()
        if b3.button("Reopen", disabled=locked or r.status is Status.DRAFTED,
                     help="Undo an approve or reject"):
            ss.receipts[rid] = r.model_copy(update={"status": Status.DRAFTED})
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

    if any(r.status in (Status.APPROVED, Status.POSTED) for r in receipts):
        st.subheader("Download the books")
        st.caption("The same layouts the Google Sheet gets, for approved receipts. Opens in Excel or Sheets.")
        views = local_views(receipts, EVENT, income, sink.reimbursements())
        cols = st.columns(len(views))
        for col, (title, grid) in zip(cols, views.items(), strict=True):
            col.download_button(title, grid_to_csv(grid), file_name=f"{EVENT_ID}_{title.replace(' ', '_')}.csv",
                                mime="text/csv", key=f"dl-{title}")

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
    attendees = int(c[1].number_input("Attendees", min_value=1, value=ss.event["attendees"]))
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

save_session()
