"""Streamlit app: Upload -> Review -> Summary. Run with `streamlit run app.py`.

Theme lives in .streamlit/config.toml. Reads receipts with Claude when ANTHROPIC_API_KEY
is in .env, otherwise with the stub (fake answer key plus planted misreads).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
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
from treasurer.post import TX_FIELDS, LocalCsvSink, event_totals
from treasurer.reader import make_extractor
from treasurer.reimburse import METHODS, Reimbursement, totals_by_payer, validate
from treasurer.runlog import log_run, minutes, read_runs
from treasurer.sheets import DEFAULT_SOURCES, EventInfo, GoogleSheetsSink, grid_to_csv, local_transactions, local_views
from treasurer.xlsx_export import book_xlsx

ROOT = Path(__file__).parent
OUT = Path(os.getenv("TALLYABLE_OUTPUT_DIR") or ROOT / "output")
FAKE = ROOT / "fake_event"
DEFAULT_EVENT = {"event_id": "EVT-FAKE-01", "name": "Fall Mentor Mixer (FAKE)", "date": date(2026, 11, 14),
                 "attendees": 45, "members": "Member A, Member B, Member C, Member D",
                 "sources": ", ".join(DEFAULT_SOURCES)}
ICON = {Status.DRAFTED: "⏳ drafted", Status.APPROVED: "✅ approved", Status.REJECTED: "❌ rejected",
        Status.POSTED: "📤 posted"}

ART = ROOT / "assets"
st.set_page_config(page_title="Tallyable", page_icon=str(ART / "mascot.png"), layout="wide")
ss = st.session_state

# Prototype 1 look on top of the theme in .streamlit/config.toml: sticker-style hover lifts
# on buttons and cards, a numbered step bar, and the mascot. Motion is off for reduced-motion users.
st.markdown("""<style>
.stButton button, .stDownloadButton button, .stFormSubmitButton button, .stLinkButton a {
  transition: transform .16s cubic-bezier(.2,.8,.2,1), box-shadow .16s, filter .16s; }
.stButton button:hover:not(:disabled), .stDownloadButton button:hover:not(:disabled),
.stFormSubmitButton button:hover:not(:disabled), .stLinkButton a:hover {
  transform: translateY(-2px); box-shadow: 0 4px 0 rgba(20,70,42,.35); }
.stButton button:active:not(:disabled), .stDownloadButton button:active:not(:disabled),
.stFormSubmitButton button:active:not(:disabled) { transform: translateY(1px); box-shadow: none; }
[data-testid="stVerticalBlockBorderWrapper"], [data-testid="stMetric"] { transition: transform .2s, box-shadow .2s; }
[data-testid="stMetric"]:hover { transform: translateY(-2px); box-shadow: 0 4px 0 rgba(20,70,42,.18); }
[data-testid="stFileUploaderDropzone"] { border: 2px dashed #9DB8A4; transition: background-color .2s, border-color .2s; }
[data-testid="stFileUploaderDropzone"]:hover { border-color: #1C5C36; background-color: rgba(247,190,63,.12); }
[data-testid="stSidebar"] label[data-baseweb="radio"] { border-radius: 999px; padding: 2px 8px; transition: background-color .15s; }
[data-testid="stSidebar"] label[data-baseweb="radio"]:hover { background-color: rgba(247,190,63,.22); }
.tly-walk { position: relative; padding: 58px 14px 0; margin: 0 0 1.4rem; }
.tly-walk img { position: absolute; bottom: 14px; height: 55px; width: auto; transform: translateX(-50%); z-index: 2;
  animation: tly-bob 2.4s ease-in-out infinite; filter: drop-shadow(0 2px 0 rgba(0,0,0,.08)); }
@keyframes tly-bob { 0%, 100% { translate: 0 0; } 50% { translate: 0 -4px; } }
.tly-walk .track { position: relative; height: 12px; border-radius: 999px; background: #EEE7CC; }
.tly-walk .fill { position: absolute; inset: 0 auto 0 0; border-radius: 999px; background: linear-gradient(90deg, #1C5C36, #3F8A5A); }
.tly-walk .dot { position: absolute; top: 50%; width: 24px; height: 24px; transform: translate(-50%, -50%); border-radius: 50%;
  background: #fff; border: 3px solid #C9C2A6; display: grid; place-items: center; color: #fff; font-size: .75rem; font-weight: 800; }
.tly-walk .dot.done { background: #1C5C36; border-color: #1C5C36; }
.tly-walk .dot.now { border-color: #1C5C36; box-shadow: 0 0 0 4px rgba(247,190,63,.45); }
.tly-walk .stops { position: relative; height: 1.6rem; margin-top: 10px; font-weight: 600; font-size: .92rem; }
.tly-walk .stops span { position: absolute; white-space: nowrap; color: #8A877A; transform: translateX(-50%); }
.tly-walk .stops span.start { transform: translateX(-14px); } .tly-walk .stops span.end { transform: translateX(calc(-100% + 14px)); }
.st-key-mascot-empty [data-testid="stImage"], .st-key-mascot-cheer [data-testid="stImage"] { margin: 0 auto; }
.st-key-mascot-empty, .st-key-mascot-cheer { align-items: center; }
@media (max-width: 640px) { .tly-walk .stops span:not(.now) { display: none; }
  .tly-walk .stops span.now { transform: translateX(-50%); } .tly-walk .stops span.now.start { transform: translateX(-14px); }
  .tly-walk .stops span.now.end { transform: translateX(calc(-100% + 14px)); } }
.tly-walk .stops .done { color: #1C5C36; } .tly-walk .stops .now { color: #1F2A22; font-weight: 700; }
.tly-steps { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 4px; margin: .2rem 0 1rem; font-size: .9rem; }
.tly-step { display: inline-flex; align-items: center; gap: 6px; color: #6B6A60; font-weight: 500; }
.tly-step b { display: inline-grid; place-items: center; width: 24px; height: 24px; border-radius: 50%;
  border: 2px solid #C9C2A6; font-size: .78rem; }
.tly-step.done { color: #1C5C36; } .tly-step.done b { background: #DDEBD9; border-color: #1C5C36; }
.tly-step.now { color: #1F2A22; font-weight: 700; } .tly-step.now b { background: #1C5C36; border-color: #1C5C36; color: #fff; }
.tly-rule { width: 28px; border-top: 2px dotted #C9C2A6; margin: 0 4px; }
.tly-cheer { text-align: center; font-family: Fredoka, sans-serif; font-size: 1.5rem; font-weight: 600;
  color: #1C5C36; margin: .4rem 0 .6rem; }
.tly-hint { text-align: center; font-weight: 600; margin: .25rem 0 .5rem; }
.tly-owed { font-size: 1.15rem; font-weight: 700; font-variant-numeric: tabular-nums; }
.tly-avatar { display: inline-grid; place-items: center; width: 38px; height: 38px; border-radius: 50%;
  background: #FCE7A8; font-family: Fredoka, sans-serif; font-weight: 600; color: #1F2A22; }
.tly-bar { height: 12px; border-radius: 999px; background: #E3D9B6; overflow: hidden; }
.tly-bar > div { height: 100%; border-radius: 999px; background: #1C5C36; }
:root { --tly-forest: #1C5C36; --tly-done: #DDEBD9; --tly-sun: #F7BE3F; --tly-sun-soft: #FCE7A8; --tly-berry: #C44536;
  --tly-card: #FFFFFF; --tly-line: #E3D9B6; --tly-soft: #6B6A60; }
/* Sidebar: event card, then the stepper. */
.tly-event { display: grid; grid-template-columns: 62px 1fr; margin: 4px 0 0; border: 2px solid var(--tly-forest);
  border-radius: 14px; overflow: hidden; background: var(--tly-card); }
.tly-event .stub { display: grid; place-content: center; text-align: center; line-height: 1; padding: 10px 0;
  background: var(--tly-forest); color: #fff; font-family: Fredoka, sans-serif; border-right: 2px dashed #FAF7E7; }
.tly-event .stub span { font-size: .72rem; letter-spacing: .1em; } .tly-event .stub b { font-size: 1.7rem; margin: 2px 0; }
.tly-event .info { padding: 10px 12px; display: grid; gap: 2px; align-content: center; }
.tly-event .info b { font-family: Fredoka, sans-serif; font-size: 1.08rem; line-height: 1.2; color: #1F2A22; }
.tly-event .info small { color: var(--tly-soft); }
.st-key-edit-event [data-testid="stExpander"] details { border: 2px solid var(--tly-forest); border-radius: 14px;
  background: #E6F0E2; }
.st-key-edit-event [data-testid="stExpander"] summary { color: var(--tly-forest); font-weight: 700; }
.st-key-edit-event [data-testid="stExpander"] summary:hover { background: #D3E6CD; }
.st-key-step { margin-top: .5rem; }
.st-key-event-group { background: var(--tly-card); border: 2px solid var(--tly-line) !important; border-radius: 18px !important;
  padding: 12px 12px 16px !important; }
.st-key-edit-event { margin-top: -12px; }
.st-key-step [data-testid="stWidgetLabel"] { display: none; }
.st-key-step [role="radiogroup"] { gap: 4px; position: relative; padding: 4px 0; }
.st-key-step [role="radiogroup"]::before, .st-key-step [role="radiogroup"]::after { content: ""; position: absolute;
  left: 23px; top: 22px; width: 4px; border-radius: 4px; }
.st-key-step [role="radiogroup"]::before { bottom: 30px; background: #E6DEC0; }
.st-key-step [role="radiogroup"]::after { background: var(--tly-forest); height: var(--tly-fill, 0%); max-height: calc(100% - 52px); }
.st-key-step label { position: relative; display: flex; align-items: flex-start; gap: 12px; width: 100%; margin: 0;
  padding: 6px 10px 10px 10px !important; border-radius: 14px; cursor: pointer; transition: background-color .15s; }
.st-key-step label:hover { background: rgba(247,190,63,.22); }
.st-key-step label > div > div:first-child { display: none; }  /* the radio circle */
.st-key-step label::before { position: relative; z-index: 1; display: inline-grid; place-items: center; flex: none;
  width: 30px; height: 30px; border-radius: 50%; border: 3px solid #C9C2A6; background: var(--tly-card);
  font-size: .8rem; font-weight: 700; color: var(--tly-soft); box-sizing: border-box; }
.st-key-step label p { font-size: 1rem; font-weight: 600; line-height: 1.25; margin-top: 4px; white-space: pre-line; }
.st-key-step label p::after { display: block; font-size: .8rem; font-weight: 400; color: var(--tly-soft); margin-top: 1px; }
/* Money in vs out */
.tly-money { display: grid; gap: 10px; }
.tly-money .row { display: grid; grid-template-columns: 44px 1fr auto; align-items: center; gap: 10px; }
.tly-money .lbl { font-size: .8rem; font-weight: 600; color: var(--tly-soft); }
.tly-money .track { height: 22px; border-radius: 8px; background: rgba(227,217,182,.45); overflow: hidden; }
.tly-money .fill { height: 100%; border-radius: 8px; }
.tly-money .in .fill { background: var(--tly-forest); } .tly-money .out .fill { background: var(--tly-sun); }
.tly-money .amt { font-weight: 700; font-variant-numeric: tabular-nums; }
.tly-net { justify-self: start; display: inline-flex; gap: 6px;
  align-items: baseline; padding: 6px 12px; border-radius: 999px; font-weight: 600; }
.tly-net.good { background: var(--tly-done); color: var(--tly-forest); }
.tly-net.bad { background: #F6D5CF; color: #8E2A1E; }
.tly-net b { font-family: Fredoka, sans-serif; font-size: 1.15rem; }
/* Summary: tinted metric tiles */
.st-key-sum-metrics [data-testid="stMetric"] { border-width: 2px !important; }
.st-key-sum-metrics [data-testid="stColumn"]:nth-child(1) [data-testid="stMetric"] {
    background: #E6F0E2; border-color: #B9D3B2 !important; }
.st-key-sum-metrics [data-testid="stColumn"]:nth-child(2) [data-testid="stMetric"] {
    background: #FDF0C8; border-color: #F2D88A !important; }
.st-key-sum-metrics [data-testid="stColumn"]:nth-child(3) [data-testid="stMetric"] { background: var(--tly-card); }
.st-key-sum-metrics [data-testid="stColumn"]:nth-child(4) [data-testid="stMetric"] { background: var(--tly-card); }
.st-key-income-box { background: var(--tly-card); }
.tly-chip { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .8rem; font-weight: 600; margin-right: 4px; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }

/* Guide boxes: mascot speech bubble (Kevin's pick 1) */
.tly-guide-mascot { display: block; }
[class*="st-key-bubble-"] { position: relative; background: #FFFFFF; border: 2px solid #1C5C36;
  border-radius: 16px; padding: 12px 16px; gap: .4rem; flex: 1 1 0; min-width: 0; }
[class*="st-key-bubble-"]::before { content: ""; position: absolute; left: -10px; top: 24px; width: 16px; height: 16px;
  background: #FFFFFF; border-left: 2px solid #1C5C36; border-bottom: 2px solid #1C5C36; transform: rotate(45deg); }
[class*="st-key-bubble-tip-"] { padding: 8px 14px; }
[class*="st-key-bubble-tip-"]::before { top: 50%; margin-top: -8px; }
[class*="st-key-guide-"] > .stElementContainer:first-child { flex: 0 0 auto !important; width: auto !important; }
[class*="st-key-bubble-"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
[class*="st-key-bubble-"] [data-testid="stMarkdownContainer"] p { font-family: Inter, sans-serif; font-size: .95rem;
  line-height: 1.45; color: #3F4A42; margin: 0 !important; }
[class*="st-key-bubble-"] [data-testid="stMarkdownContainer"] p strong { color: #1F2A22; }
[class*="st-key-bubble-"] [data-testid="stMarkdownContainer"] p.tly-bubble-title {
  font-family: Fredoka, sans-serif; font-weight: 600; font-size: 1.15rem;
  color: #1F2A22; line-height: 1.25; }
[class*="st-key-guide-"] { margin: .25rem 0 .5rem; }
[class*="st-key-bubble-"] [data-testid="stBaseButton-primary"] p { color: #FFFFFF !important; font-weight: 600; }
</style>""", unsafe_allow_html=True)


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
PAST = OUT / "events"  # one saved file per event, so a closed event can be reopened later
SAVED_KEYS = ("event", "receipts", "images", "notes", "edits", "income", "drafted_at", "review_started", "started")


def dec(text: str, default: str = "0") -> Decimal:
    """Read a typed amount. Accepts "$1,234.50"; anything unreadable (or NaN) becomes the default."""
    cleaned = str(text).replace("$", "").replace(",", "").strip()
    try:
        value = Decimal(cleaned or default)
    except InvalidOperation:
        return Decimal(default)
    return value if value.is_finite() else Decimal(default)


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
        if not st.form_submit_button("Add"):
            return
        if not place.strip() or not item.strip():
            st.error("Fill in Place and Item, then click Add.")
            return
        rid = next_id(image_file)
        try:
            ss.receipts[rid] = Receipt(receipt_id=rid, event_id=EVENT_ID, place=place.strip(), date=d,
                                       payer=payer or None, tax=dec(tax), tip=dec(tip), total=dec(total),
                                       image_file=image_file,
                                       items=[LineItem(category=cat, item=item.strip(), unit=int(unit), price=dec(price))])
        except ValueError as e:
            st.error(f"Not added: {e}")
            return
        if data:
            ss.images[rid] = data
        if image_file:
            ss.failed.pop(image_file, None)
        st.toast(f"Added {rid}. Check it on Review.", icon=":material/check:")
        st.rerun()


def saved_reimbursements(sink) -> list[dict]:
    try:
        return sink.reimbursements()
    except Exception as e:
        st.error(f"Could not read paybacks from {sink.label}: {e}")
        return []


def usd(amount: Decimal) -> str:
    """$12.50, or -$12.50 for a loss (not $-12.50)."""
    return f"-${-amount}" if amount < 0 else f"${amount}"


def money_panel(receipts: list[Receipt], income: dict[str, Decimal]) -> None:
    """Money in vs out as two bars on one scale. In is split by source, out by category
    (Food, Drink, Other, then Tax & tip), with a net pill on top."""
    t = event_totals(receipts, income)
    if t["income"] <= 0 and t["expenses"] <= 0:
        st.caption("Nothing in or out yet.")
        return
    net = t["net"]
    if net >= 0:
        pill = f'<span class="tly-net good"><b>{usd(net)}</b> left over</span>'
    else:
        pill = f'<span class="tly-net bad"><b>{usd(-net)}</b> more out than in</span>'
    approved = [r for r in receipts if r.status in (Status.APPROVED, Status.POSTED)]
    cats: dict[str, Decimal] = {}
    for r in approved:
        for i in r.items:
            if not i.returned:
                cats[i.category] = cats.get(i.category, Decimal("0")) + i.amount
    cats = {k: v for k, v in cats.items() if v > 0}
    rest = t["expenses"] - sum(cats.values(), Decimal("0"))
    if rest > 0:
        cats["Tax & tip"] = rest
    ins = {k: v for k, v in income.items() if v > 0}
    top = max(t["income"], t["expenses"], Decimal("0.01"))
    in_shades, out_shades = ["#1C5C36", "#3F8A5A", "#7DB88F", "#B4D8BD"], ["#A8322A", "#C44536", "#DE7A6E", "#EFAFA6"]

    def bar(cls: str, label: str, total: Decimal, parts: dict[str, Decimal], shades: list[str]) -> tuple[str, str]:
        whole = sum(parts.values(), Decimal("0")) or Decimal("1")
        width = float(total / top * 100) if total > 0 else 0
        segs = "".join(f'<div class="fill" title="{html.escape(k)}: {usd(v)}" style="width:{float(v / whole * 100):.2f}%;'
                       f'background:{shades[n % len(shades)]};border-radius:0"></div>' for n, (k, v) in enumerate(parts.items()))
        row = (f'<div class="row {cls}"><span class="lbl">{label}</span><div class="track">'
               f'<div style="display:flex;height:100%;width:{width:.2f}%;border-radius:8px;overflow:hidden">{segs}</div></div>'
               f'<span class="amt">{usd(total)}</span></div>')
        legend = " ".join(f'<span class="tly-chip" style="background:{shades[n % len(shades)]}33">'
                          f'<span style="color:{shades[n % len(shades)]}">●</span> {html.escape(k)} {usd(v)}</span>'
                          for n, (k, v) in enumerate(parts.items()))
        return row, legend

    in_row, in_leg = bar("in", "In", t["income"], ins, in_shades)
    out_row, out_leg = bar("out", "Out", t["expenses"], cats, out_shades)
    st.markdown(f'<div class="tly-money">{pill}{in_row}{out_row}'
                f'<div style="line-height:2">{in_leg}</div><div style="line-height:2">{out_leg}</div></div>',
                unsafe_allow_html=True)
    if t["income"] <= 0:
        st.caption("No income entered yet. Add it on the Summary step.")


def md(text: str) -> str:
    """Escape $ so Streamlit does not render dollar amounts as LaTeX."""
    return text.replace("$", "\\$")


STEPS = ["1. Upload", "2. Review", "3. Summary", "4. Close out"]


def go(step: str) -> None:
    """Button callback: switch the sidebar step (runs before the sidebar is drawn)."""
    ss.step = step


def step_status() -> tuple[dict[str, bool], dict[str, str]]:
    """Which steps are finished, plus a short progress note (Review · 3/14)."""
    rs = list(ss.receipts.values())
    reviewed = sum(1 for r in rs if r.status is not Status.DRAFTED)
    posted = bool(rs) and all(r.status in (Status.POSTED, Status.REJECTED) for r in rs) \
        and any(r.status is Status.POSTED for r in rs)
    done = {"1. Upload": bool(rs), "2. Review": bool(rs) and reviewed == len(rs), "3. Summary": posted,
            "4. Close out": False}
    return done, {"2. Review": f" · {reviewed}/{len(rs)}" if rs else ""}


def sidebar_stepper(current: str) -> None:
    """Timeline stepper in the sidebar (prototype B). The radio's labels stay fixed so the widget
    keeps its state; this run's CSS adds each step's status line, the checks, and how far the
    green line has filled (down to this step, plus Review's progress)."""
    done, _ = step_status()
    rs = list(ss.receipts.values())
    reviewed = sum(1 for r in rs if r.status is not Status.DRAFTED)
    sub = {"1. Upload": f"{len(rs)} receipt{'s' if len(rs) != 1 else ''} in" if rs else "Photos, screenshots, PDFs",
           "2. Review": f"{reviewed} of {len(rs)} checked" if rs else "Check each one",
           "3. Summary": "In the books" if done["3. Summary"] else "Add income, push",
           "4. Close out": "Who's owed, report"}
    i = STEPS.index(current)
    frac = i / (len(STEPS) - 1)
    if current == "2. Review" and rs:
        frac += reviewed / len(rs) / (len(STEPS) - 1) * 0.8
    rules = [f'.st-key-step [role="radiogroup"] {{ --tly-fill: {frac * 100:.1f}%; }}']
    for n, name in enumerate(STEPS, start=1):
        row = f'.st-key-step [role="radiogroup"] > div:nth-child({n}) label'
        rules.append(f'{row} p::after {{ content: "{sub[name]}"; }}')
        if name == current:
            rules.append(f'{row}::before {{ content: "{n}"; border-color: var(--tly-forest); color: var(--tly-forest); '
                         "box-shadow: 0 0 0 4px rgba(247,190,63,.5); }" f" {row} p {{ font-weight: 700; }}")
            if name == "2. Review" and rs:
                pct = reviewed / len(rs) * 100
                rules.append(f'{row}::after {{ content: ""; position: absolute; left: 52px; right: 12px; bottom: 4px; '
                             f"height: 6px; border-radius: 9px; background: linear-gradient(90deg, var(--tly-sun) {pct:.0f}%, "
                             f"#E6DEC0 {pct:.0f}%); }}")
        elif done[name]:
            rules.append(f'{row}::before {{ content: "✓"; background: var(--tly-forest); border-color: var(--tly-forest); '
                         "color: #fff; }")
        else:
            rules.append(f'{row}::before {{ content: "{n}"; }}')
    st.html("<style>" + "\n".join(rules) + "</style>")


@st.cache_data
def mascot_uri(file: str = "mascot-small.png") -> str:
    return "data:image/png;base64," + base64.b64encode((ART / file).read_bytes()).decode()


# Tally's pose on the walker bar for each step (Kevin's picks). Close out keeps the original.
TALLY = {"1. Upload": "tally-upload-small.png", "2. Review": "tally-review-small.png",
         "3. Summary": "tally-summary-small.png", "4. Close out": "mascot-small.png"}


def guide(title: str, body: str, *, key: str, tip: bool = False, to: str | None = None):
    """Mascot speech bubble for empty states and tips. Returns the bubble so callers can add buttons."""
    row = st.container(key=f"guide-{key}", horizontal=True, vertical_alignment="center", gap="small")
    with row:
        size = 44 if tip else 86
        st.html(f'<img class="tly-guide-mascot" src="{mascot_uri()}" width="{size}" alt="">')
        bubble = st.container(key=f"bubble-{'tip' if tip else 'big'}-{key}")
        with bubble:
            text = (f"**{title}** " if title and tip else "") + body
            if title and not tip:
                st.markdown(f'<p class="tly-bubble-title">{html.escape(title)}</p>', unsafe_allow_html=True)
            st.markdown(text)
            if to:
                st.button(f"Go to {to.split('. ', 1)[1]}", key=f"go-{key}", type="primary",
                          icon=":material/arrow_forward:", icon_position="right", on_click=go, args=(to,))
    return bubble


def step_bar(current: str) -> None:
    """Mascot walker: a track with a dot per step. Finished dots get a check, and the mascot
    stands where you are, inching along Review as receipts get checked."""
    done, detail = step_status()
    i = STEPS.index(current)
    pos = i / (len(STEPS) - 1)
    rs = list(ss.receipts.values())
    if current == "2. Review" and rs:
        reviewed = sum(1 for r in rs if r.status is not Status.DRAFTED)
        pos += reviewed / len(rs) / (len(STEPS) - 1) * 0.9  # stop just short of the next dot
    pct = round(pos * 100, 2)
    dots, labels = [], []
    for n, name in enumerate(STEPS):
        left = round(n / (len(STEPS) - 1) * 100, 2)
        state = "done" if done[name] and name != current else "now" if name == current else ""
        dots.append(f'<span class="dot {state}" style="left:{left}%">{"✓" if state == "done" else ""}</span>')
        label = name.split(". ", 1)[1] + detail.get(name, "")
        align = "start" if n == 0 else "end" if n == len(STEPS) - 1 else "mid"
        labels.append(f'<span class="{state} {align}" style="left:{left}%">{"✓ " if state == "done" else ""}{label}</span>')
    st.markdown(f'<div class="tly-walk" role="img" aria-label="Step {i + 1} of {len(STEPS)}: {current.split(". ", 1)[1]}">'
                f'<div class="track"><div class="fill" style="width:{pct}%"></div>{"".join(dots)}'
                f'<img src="{mascot_uri(TALLY[current])}" alt="" style="left:{pct}%"></div>'
                f'<div class="stops">{"".join(labels)}</div></div>', unsafe_allow_html=True)


def next_step(message: str, label: str, target: str, key: str) -> None:
    """A box that says what to do next, with one button that goes there."""
    with st.container(border=True):
        c = st.columns([4, 1], vertical_alignment="center")
        c[0].markdown(md(message))
        c[1].button(label, type="primary", on_click=go, args=(target,), key=key, width="stretch")


def event_id_for(name: str, d: date) -> str:
    slug = "".join(ch for ch in name.upper() if ch.isalnum())[:12] or "EVENT"
    return f"EVT-{d.isoformat()}-{slug}"


def start_new_event() -> None:
    """Clear the screen for the next event. The finished one stays under Past events.
    Club settings (members, income sources) carry over."""
    ss.event = {**ss.event, "name": "New event", "date": date.today(),
                "event_id": event_id_for("New event", date.today())}
    for k in ("receipts", "images", "notes", "failed"):
        ss[k] = {}
    ss.edits, ss.drafted_at, ss.review_started, ss.income = 0, None, None, {}
    ss.pop("last_draft", None)
    ss.pop("last_push", None)
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
        session_store.save(PAST / f"{ss.event['event_id']}.json", state)
        ss._saved = text


def open_past(path: Path) -> None:
    """Button callback: switch to a saved event. The current one is already saved."""
    saved = session_store.load(path)
    if not saved:
        ss.past_error = f"Could not open {path.name}."
        return
    for k, v in saved.items():
        ss[k] = v
    ss.failed = {}
    ss.pop("last_draft", None)
    ss.pop("last_push", None)
    ss.pop("_saved", None)
    ss.step = "4. Close out"


ss.setdefault("event", dict(DEFAULT_EVENT))
st.logo(str(ART / "logo.png"), size="large")
st.sidebar.caption("Close out a club event: receipts in, checked books out.")
if st.sidebar.button("New event", icon=":material/add:", key="new-event", type="primary", width="stretch",
                     help="Starts a blank event. This one stays saved under Past events."):
    start_new_event()
    st.rerun()
event_group = st.sidebar.container(border=True, key="event-group")  # ticket, steps and Edit event in one box
event_card = event_group.empty()  # filled below, once the event fields are read
steps_slot = event_group.container()  # the stepper sits under the ticket; Edit event goes below it
with event_group.container(key="edit-event"), st.expander("Edit event", icon=":material/edit:",
                                                         expanded=not ss.receipts and ss.event == DEFAULT_EVENT):
    locked = bool(ss.receipts)
    name = st.text_input("Event name", ss.event["name"], disabled=locked)
    d = st.date_input("Event date", ss.event["date"], disabled=locked)
    attendees = int(st.number_input("Attendees", min_value=1, value=ss.event["attendees"]))
    members = st.text_input("Members who might pay", ss.event["members"], help="Comma separated")
    sources = st.text_input("Where money comes in", ss.event.get("sources", ", ".join(DEFAULT_SOURCES)),
                            help="Comma separated, e.g. Venmo, Cash, Ticket sales, Sponsor, Student government grant")
    changed = name != ss.event["name"] or d != ss.event["date"]
    ss.event.update(name=name, date=d, attendees=attendees, members=members, sources=sources,
                    event_id=event_id_for(name, d) if changed else ss.event["event_id"])
    if locked:
        st.caption("Name and date are locked once receipts are drafted.")
EVENT_ID = ss.event["event_id"]
EVENT = EventInfo(EVENT_ID, ss.event["name"], ss.event["date"], ss.event["attendees"])
PAYERS = ["", *[m.strip() for m in ss.event["members"].split(",") if m.strip()]]
SOURCES = list(dict.fromkeys(x.strip() for x in ss.event.get("sources", ", ".join(DEFAULT_SOURCES)).split(",")
                             if x.strip())) or list(DEFAULT_SOURCES)
n_rec = len(ss.receipts)
event_card.markdown(f'<div class="tly-event"><div class="stub"><span>{EVENT.date.strftime("%b").upper()}'
                    f'</span><b>{EVENT.date.day}</b><span>{EVENT.date.year}</span></div><div class="info">'
                    f'<b>{html.escape(EVENT.name)}</b><small>{n_rec} receipt{"s" if n_rec != 1 else ""}</small></div></div>',
                    unsafe_allow_html=True)
page = steps_slot.radio("Steps", STEPS, key="step", format_func=lambda n: n.split(". ", 1)[1])
sidebar_stepper(page)
past = [e for e in session_store.past_events(PAST) if e["event_id"] != ss.event["event_id"]]
if past:
    with st.sidebar.expander(f"Past events ({len(past)})"):
        pick = st.selectbox("Event", past, format_func=lambda e: f"{e['date']} · {e['name']} ({e['receipts']} receipts)",
                            key="past-pick")
        st.button("Open this event", on_click=open_past, args=(pick["path"],), width="stretch",
                  help="Your current event is saved first, so you can come back to it here.")
if ss.get("past_error"):
    st.sidebar.error(ss.pop("past_error"))

# ---------------- Screen 1: Upload ----------------
if page == "1. Upload":
    st.header("Upload receipts")
    step_bar(page)
    if not ss.receipts and SESSION_FILE.exists():
        saved = session_store.load(SESSION_FILE)
        if saved and saved["receipts"]:
            n = len(saved["receipts"])
            done = sum(1 for r in saved["receipts"].values() if r.status is not Status.DRAFTED)
            with guide("Welcome back!", f"You have a saved session for {saved['event']['name']}: "
                       f"{n} receipts, {done} reviewed.", key="resume", tip=True):
                resume = st.button("Resume where I left off")
            if resume:
                for k, v in saved.items():
                    ss[k] = v
                st.rerun()
    ex, reader = make_extractor()
    if reader == "claude":
        st.success(f"Reading receipts with Claude ({ex.model}).")
    else:
        guide("Demo mode:", "I can only read the fake event's receipts (with a few planted misreads to catch). "
              "Add ANTHROPIC_API_KEY to .env and restart to read real receipts with Claude.", key="demo", tip=True)
    if not ss.receipts and not ss.get("demo") and not ss.get("uploads"):
        with st.container(key="mascot-empty"):
            st.image(str(ART / "mascot-empty.png"), width=190)
        st.markdown('<p class="tly-hint">Drop receipts, screenshots or PDFs here</p>', unsafe_allow_html=True)
    files = st.file_uploader("Receipt photos or PDFs", type=UPLOAD_TYPES, accept_multiple_files=True, key="uploads")
    if st.button("Use the fake event's 14 receipts instead"):
        files = None
        ss.demo = sorted((FAKE / "receipts").glob("*.jpg"))
    sources = [(f.name, f.getvalue()) for f in files] if files else [(p.name, p.read_bytes()) for p in ss.get("demo", [])]

    if sources:
        untagged = sum(1 for name, _ in sources if not ss.get(f"payer-{name}"))
        guide(f"{len(sources)} receipts loaded.", md("Pick who paid for each (below), then click **Draft rows**. "
              + (f"{untagged} still have no payer; those get flagged in Review." if untagged else "Every receipt has a payer.")),
              key="loaded", tip=True)
        c = st.columns([3, 1, 2], vertical_alignment="bottom")
        everyone = c[0].selectbox("Set every payer to", PAYERS[1:], key="payer-all")
        if c[1].button("Apply to all"):
            for name, _ in sources:
                ss[f"payer-{name}"] = everyone
            st.rerun()
        draft_clicked = c[2].button("Draft rows", type="primary")
    else:
        draft_clicked = False

    if draft_clicked:
        bar = st.progress(0.0, text=f"Starting to read {len(sources)} receipts...")
        seen = {hashlib.sha256(b).hexdigest() for b, _ in ss.images.values()}
        skipped = []
        for n, (name, data) in enumerate(sources):
            bar.progress(n / len(sources), text=f"Reading {name} ({n + 1} of {len(sources)})...")
            try:
                f = prepare(data, name)
                if hashlib.sha256(f.data).hexdigest() in seen:  # already drafted: don't read (or pay) twice
                    skipped.append(name)
                    continue
                rid = next_id(name)
                r = ex.extract(f.data, f.filename, EVENT_ID, rid)
                ss.receipts[rid] = r.model_copy(update={"payer": ss.get(f"payer-{name}") or None, "image_file": name})
                ss.images[rid] = (f.data, f.media_type)
                notes = f.warnings + ([f"Reader's note: {r.review_note}"] if r.review_note else [])
                if notes:
                    ss.notes[rid] = notes
                ss.failed.pop(name, None)
            except UnsupportedFile as e:
                ss.failed[name] = (None, str(e))
            except ExtractionError as e:
                ss.failed[name] = ((f.data, f.media_type), f"{e} You can type it in by hand below.")
        bar.progress(1.0, text=f"Read {len(sources) - len(skipped)} receipts.")
        ss.demo = []
        ss.drafted_at = ss.drafted_at or time.time()
        cost = f" (about ${ex.cost():.3f} in API calls)" if reader == "claude" else ""
        ss.last_draft = f"**Drafted {len(ss.receipts)} receipts{cost}.** Next, check each one against its photo."
        if skipped:
            ss.last_draft += f" Skipped {len(skipped)} already drafted: {', '.join(skipped)}."
    if ss.get("last_draft") and ss.receipts:
        next_step(ss.last_draft, "Go to Review →", "2. Review", "to-review")

    if sources:
        st.subheader("Who paid")
        grid = st.columns(4)
        for n, (name, _) in enumerate(sources):
            grid[n % 4].selectbox(name, PAYERS, key=f"payer-{name}")

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
    step_bar(page)
    if not ss.receipts:
        guide("Nothing to review yet!", "Drop your receipts on the Upload step and I'll read them for you.",
              key="review-empty", to="1. Upload")
        st.stop()
    ss.review_started = ss.review_started or time.time()
    flags = run_checks(list(ss.receipts.values()))
    reviewed = sum(1 for x in ss.receipts.values() if x.status is not Status.DRAFTED)
    st.progress(reviewed / len(ss.receipts), text=f"{reviewed} of {len(ss.receipts)} reviewed")
    if reviewed == len(ss.receipts):
        ok = sum(1 for x in ss.receipts.values() if x.status in (Status.APPROVED, Status.POSTED))
        next_step(f"**All {reviewed} receipts reviewed:** {ok} approved, {reviewed - ok} rejected. "
                  "Next, add the event's income and push the approved rows to the books.",
                  "Go to Summary →", "3. Summary", "to-summary")

    def attention(x_rid: str) -> bool:
        return any(f.severity is not Severity.INFO for f in flags[x_rid]) or bool(ss.notes.get(x_rid))

    show = st.sidebar.selectbox("Show", ["All", "Not reviewed yet", "Needs attention"])
    ids = [x for x, rec in ss.receipts.items()
           if show == "All" or (show == "Not reviewed yet" and rec.status is Status.DRAFTED)
           or (show == "Needs attention" and attention(x))]
    if not ids:
        st.success("Nothing left in this view.")
        st.stop()
    labels = {x: f"{ICON[ss.receipts[x].status].split()[0]} {x} · {ss.receipts[x].place}" + (" ⚠️" if attention(x) else "")
              for x in ids}
    if ss.get("next_pick") in ids:  # set by "Approve" so the next receipt opens by itself
        ss["review-pick"] = ss.pop("next_pick")
    elif ss.get("review-pick") not in ids:
        ss["review-pick"] = ids[0]
    rid = st.sidebar.radio("Receipts", ids, format_func=labels.get, key="review-pick",
                           help="⏳ to review · ✅ approved · ❌ rejected · 📤 posted · ⚠️ has a flag")
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
    step_bar(page)
    receipts = list(ss.receipts.values())
    if not receipts:
        guide("Nothing to sum up yet!", "Upload and check your receipts first, then I'll add them up here.",
              key="summary-empty", to="1. Upload")
        st.stop()
    st.subheader("Income")
    st.caption("Money that came in for this event. Expenses come from the receipts you approved.")
    st.caption("Change the list of sources in the sidebar, under Edit event.")
    with st.container(border=True, key="income-box"):
        c = st.columns(min(len(SOURCES), 4))
        income = {k: dec(c[n % len(c)].text_input(k, ss.income.get(k, "0.00"), key=f"income-{k}")) for n, k in
                  enumerate(SOURCES)}
    ss.income = {k: str(v) for k, v in income.items()}
    for k in SOURCES:
        typed = str(ss.get(f"income-{k}", "")).strip()
        if typed and dec(typed, "-1") != dec(typed, "1"):  # unreadable: dec fell back to its default
            st.warning(md(f"{k}: '{typed}' isn't an amount, so it counts as $0. Type a number like 120.00."))
        elif income[k] < 0:
            st.warning(md(f"{k} is negative ({usd(income[k])}). Refunds you paid out belong on a receipt, not in income."))
    t = event_totals(receipts, income)
    with st.container(key="sum-metrics"):
        m = st.columns(4)
        m[0].metric("Income", f"${t['income']}", border=True)
        m[1].metric("Expenses (approved)", f"${t['expenses']}", border=True)
        m[2].metric("Net", usd(t["net"]), border=True,
                    delta=("left over" if t["net"] >= 0 else "short") if t["income"] or t["expenses"] else None,
                    delta_color="normal" if t["net"] >= 0 else "inverse", delta_arrow="off")
        hit = t["margin_pct"] >= 10
        m[3].metric("Margin", f"{t['margin_pct']}%", help="Target: 10% or more", border=True,
                    delta="on target" if hit else "under 10% target", delta_color="normal" if hit else "inverse",
                    delta_arrow="off")
    with st.container(border=True):
        st.markdown("**Money in vs out**")
        money_panel(receipts, income)

    rows = [{"receipt": r.receipt_id, "place": r.place, "payer": r.payer or "(none)", "status": ICON[r.status],
             "posts": str(r.posted_amount) if r.status in (Status.APPROVED, Status.POSTED) else "",
             "note": r.review_note or ""} for r in receipts]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    waiting = [r.receipt_id for r in receipts if r.status is Status.DRAFTED]
    if waiting:
        st.warning(f"Review these first: {', '.join(waiting)}")
    sink, err = get_sink()
    if err:
        st.error(err)
    if sink.label != "Google Sheets":
        st.caption("Google Sheets is not set up (see docs/google_sheets_setup.md), so Push writes a local CSV.")
    pushed = st.button(f"Push to {sink.label}", type="primary", disabled=bool(waiting) or not receipts,
                       icon=":material/upload:")
    try:
        written = sink.post(receipts, EVENT, income) if pushed else None
    except Exception as e:  # network drop, sheet unshared mid-push, quota
        st.error(f"The push stopped partway: {e}. Nothing is double-counted: click Push again and "
                 "receipts already written are skipped.")
        written = None
    if written is not None:
        # Every approved receipt is in the books now: just written, or already there from an
        # earlier push (a resumed session, or a second browser tab).
        for rid, rec in list(ss.receipts.items()):
            if rec.status is Status.APPROVED:
                ss.receipts[rid] = rec.model_copy(update={"status": Status.POSTED})
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
        ss.last_push = (f"**Posted {len(written)} receipts to {sink.label}.**" if written
                        else "**Already up to date:** every approved receipt is in the books.")
        st.rerun()  # redraw the table and step bar with the posted status
    if ss.get("last_push") and not any(r.status is Status.APPROVED for r in ss.receipts.values()):
        url = getattr(sink, "url", None)
        link = f" [Open the sheet]({url})." if url else ""
        next_step(ss.last_push + link + " Next, see who's owed money and check the funder's rules.",
                  "Go to Close out →", "4. Close out", "to-closeout")

    if any(r.status in (Status.APPROVED, Status.POSTED) for r in receipts):
        st.subheader("Download the books")
        st.caption("Every report in one formatted Excel file, for approved receipts. Open it in Excel, or bring it "
                   "into your own Google Sheet with File > Import. No sharing needed.")
        views = local_views(receipts, EVENT, income, saved_reimbursements(sink))
        st.download_button("Download the whole book (Excel)", type="primary", icon=":material/download:",
                           data=book_xlsx(views, local_transactions(receipts), TX_FIELDS),
                           file_name=f"{EVENT_ID}_books.xlsx", key="dl-xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with st.expander("Or one report at a time (CSV)"):
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
        st.dataframe(pd.DataFrame(runs), width="stretch", hide_index=True)

# ---------------- Screen 4: Close out ----------------
else:
    st.header("Close out the event")
    step_bar(page)
    done = [r for r in ss.receipts.values() if r.status in (Status.APPROVED, Status.POSTED)]
    if not done:
        guide("Nothing to close out yet!", "Approve some receipts on Review, then I'll show who's owed.",
              key="close-empty", to="2. Review")
        st.stop()
    waiting = [r.receipt_id for r in ss.receipts.values() if r.status is Status.DRAFTED]
    if waiting:
        st.warning(f"Still drafted, so left out below: {', '.join(waiting)}")
    else:
        with st.container(key="mascot-cheer"):
            st.image(str(ART / "mascot-cheer.png"), width=190)
        rejected = len(ss.receipts) - len(done)
        cheer = f"All {len(done)} receipts approved!" if not rejected else f"All reviewed! {len(done)} approved, {rejected} rejected."
        st.markdown(f'<p class="tly-cheer">{cheer}</p>', unsafe_allow_html=True)

    sink, err = get_sink()
    if err:
        st.error(err)
    reimbursed = totals_by_payer(saved_reimbursements(sink), EVENT_ID)
    lines = co.payer_summary(done, reimbursed)
    owing = [x for x in lines if x.owed > 0]
    left, right = st.columns([5, 3], gap="medium")
    with left.container(border=True):
        st.subheader("Who's owed")
        cap = st.columns([3, 2], vertical_alignment="bottom")
        cap[0].caption(f"Mark paid saves the payback to {sink.label}. It shows in the ledger.")
        quick = cap[1].selectbox("Paid back with", METHODS, key="quick-method") if owing else METHODS[0]
        counts: dict[str, int] = {}
        for r in done:
            counts[(r.payer or "").strip() or "(no payer)"] = counts.get((r.payer or "").strip() or "(no payer)", 0) + 1
        for x in lines:
            row = st.columns([0.5, 2, 1.1, 1.5], vertical_alignment="center")
            initials = "".join(w[0] for w in x.payer.split()[:2] if w[0].isalnum()).upper() or "?"
            row[0].markdown(f'<span class="tly-avatar">{html.escape(initials)}</span>', unsafe_allow_html=True)
            n = counts.get(x.payer, 0)
            row[1].markdown(md(f"**{x.payer}**  \n:gray[{n} receipt{'s' if n != 1 else ''} · fronted ${x.fronted}]"))
            row[2].markdown(f'<span class="tly-owed">{md("$" + str(x.owed))}</span>', unsafe_allow_html=True)
            if x.owed <= 0:
                row[3].markdown(":green-badge[✓ Paid]")
            elif x.payer == "(no payer)":
                row[3].caption("Set a payer in Review")
            elif row[3].button("Mark paid", key=f"paid-{x.payer}", icon=":material/check:", width="stretch",
                               help=f"Records {md('$' + str(x.owed))} paid back to {x.payer} today."):
                try:
                    sink.record_reimbursement(Reimbursement(EVENT_ID, x.payer, date.today(), x.owed, quick, ""))
                except Exception as e:
                    st.error(f"Payback not saved: {e}. Try again.")
                else:
                    st.rerun()
    with right.container(border=True):
        st.subheader("Money in vs out")
        money_panel(done, {k: dec(v) for k, v in ss.income.items()})
    with st.expander("Payback details"):
        st.dataframe(pd.DataFrame([{"payer": x.payer, "fronted": str(x.fronted), "reimbursed": str(x.reimbursed),
                                    "owed": str(x.owed)} for x in lines]), width="stretch", hide_index=True)
    if owing:
        with st.expander("Pay back part of it, or by another method"), st.form("payback"):
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
                    try:
                        sink.record_reimbursement(Reimbursement(EVENT_ID, who, when, amt, method, note))
                    except Exception as e:
                        st.error(f"Payback not saved: {e}. Try again.")
                    else:
                        st.success(md(f"Recorded ${amt} paid back to {who}."))
                        st.rerun()
    else:
        st.success("Everyone has been paid back.")

    st.subheader("Funder rules")
    funder = st.selectbox("Funder", ["UC Davis CFC", "UC Davis ORG", "No funder"],
                          help="Rules for the UC Davis club funding boards. Pick No funder if your club isn't applying.")
    if funder == "No funder":
        st.caption("No funder rules checked. Who is owed (above) and the books from Summary are all you need. "
                   "This event stays saved: reopen it anytime under Past events.")
    else:
        c = st.columns(3)
        pack = {"UC Davis CFC": co.CFC, "UC Davis ORG": co.ORG}[funder]
        attendees = int(c[0].number_input("Attendees", min_value=1, value=ss.event["attendees"]))
        req_text = c[1].text_input("Requested ($, optional)", "")
        applied_on = c[2].date_input("Applying on", value=date.today())
        requested = dec(req_text) if req_text.strip() else None
        event = co.Event(EVENT_ID, EVENT.name, EVENT.date, attendees=attendees)
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
                           file_name=f"{EVENT_ID}_{pack.name.split()[-1]}_report.csv",
                           data=co.funder_report_csv(event, done, pack, requested, applied_on, reimbursed),
                           mime="text/csv")


save_session()
