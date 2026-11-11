"""Paths, small formatters and the drawing pieces every screen shares (Tally's bubble, the
walker bar, tables, the money bars)."""
from __future__ import annotations

import base64
import html
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path

import streamlit as st

from treasurer.models import Receipt, Status
from treasurer.post import LocalCsvSink, event_totals
from treasurer.sheets import GoogleSheetsSink

ROOT = Path(__file__).parent.parent
OUT = Path(os.getenv("TALLYABLE_OUTPUT_DIR") or ROOT / "output")
FAKE = ROOT / "fake_event"
ART = ROOT / "assets"
RUN_LOG = OUT / "run_log.csv"
SESSION_FILE = OUT / "session.json"
PAST = OUT / "events"  # one saved file per event, so a closed event can be reopened later
STEPS = ["1. Upload", "2. Review", "3. Summary", "4. Close out"]
# Drawn (Material) icons, never emoji: they match the rest of the UI and take the theme colors.
ICON = {Status.DRAFTED: ":material/schedule:", Status.APPROVED: ":green[:material/check_circle:]",
        Status.REJECTED: ":gray[:material/remove_circle:]", Status.POSTED: ":green[:material/cloud_done:]"}
FLAG_ICON = ":orange[:material/flag:]"
STATUS_CHIP = {Status.DRAFTED: ("drafted", "wait"), Status.APPROVED: ("approved", "ok"),
               Status.REJECTED: ("left out", "no"), Status.POSTED: ("in the books", "post")}
# Tally's pose on the walker bar for each step (Kevin's picks), one per step.
TALLY = {"1. Upload": "tally-upload-small.png", "2. Review": "tally-review-small.png",
         "3. Summary": "tally-summary-small.png", "4. Close out": "tally-calculator.png"}
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


def dec(text: str, default: str = "0") -> Decimal:
    """Read a typed amount. Accepts "$1,234.50"; anything unreadable (or NaN) becomes the default."""
    cleaned = str(text).replace("$", "").replace(",", "").strip()
    try:
        value = Decimal(cleaned or default)
    except InvalidOperation:
        return Decimal(default)
    return value if value.is_finite() else Decimal(default)


def md(text: str) -> str:
    """Escape $ so Streamlit does not render dollar amounts as LaTeX."""
    return text.replace("$", "\\$")


def usd(amount: Decimal) -> str:
    """$1,212.50 with cents always shown, or -$12.50 for a loss (not $-12.50)."""
    return f"-${-amount:,.2f}" if amount < 0 else f"${amount:,.2f}"


def payers() -> list[str]:
    """The event's members, with a blank first for "not picked yet"."""
    return ["", *[m.strip() for m in ss.event["members"].split(",") if m.strip()]]


def step_label(step: str) -> str:
    """"2. Review" -> "Review"."""
    return step.split(". ", 1)[1]


def reviewed() -> int:
    """How many receipts have been approved, left out or posted."""
    return sum(1 for r in ss.receipts.values() if r.status is not Status.DRAFTED)


def go(step: str) -> None:
    """Button callback: switch the sidebar step (runs before the sidebar is drawn)."""
    ss.step = step


@st.cache_resource(show_spinner=False)
def sheets_sink(book: str | None, ledger: str | None):
    """Signing in and opening the sheets takes a few round trips to Google, so it happens once per
    linked pair, not on every click (a Mark paid used to redo it twice). Errors aren't cached."""
    return GoogleSheetsSink.from_env(ROOT, GCP_KEY, {"book": book, "ledger": ledger} if book else None)


def get_sink():
    """Google Sheets if it is set up, else CSV files on this computer. Returns (sink, error)."""
    try:
        from ui.connect import linked
        link = linked() or {}
        return sheets_sink(link.get("book"), link.get("ledger")) or LocalCsvSink(OUT / "transactions.csv"), None
    except Exception as e:  # bad key file, sheet not shared, no network
        return LocalCsvSink(OUT / "transactions.csv"), ("Couldn't open the Google Sheet, so the books are saved on "
                                                        f"this computer for now. ({e})")


def saved_reimbursements(sink) -> list[dict]:
    try:
        return sink.reimbursements()
    except Exception as e:
        st.error(f"Could not read paybacks from {sink.label}: {e}")
        return []


@st.cache_data
def mascot_uri(file: str = "mascot-small.png") -> str:
    return "data:image/png;base64," + base64.b64encode((ART / file).read_bytes()).decode()


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
                st.button(f"Go to {step_label(to)}", key=f"go-{key}", type="primary",
                          icon=":material/arrow_forward:", icon_position="right", on_click=go, args=(to,))
    return bubble


def loading(slot, title: str, detail: str, frac: float | None, rows: list[str | None] = ()) -> None:
    """Tally's loading card, drawn into an st.empty() slot. frac None = a bar that just runs.
    rows: one line per item being read, a finished one as text and a waiting one (None) as a skeleton."""
    bar = (f'<div class="bar"><i style="width:{max(frac, 0.04) * 100:.0f}%"></i></div>' if frac is not None
           else '<div class="bar run"><i></i></div>')
    lines = "".join(f"<li>{html.escape(r)}</li>" if r else '<li class="sk"></li>' for r in rows)
    slot.markdown(f'<div class="tly-loading" role="status"><img src="{mascot_uri("tally-magnify.png")}" alt="">'
                  f'<div><b>{html.escape(title)}</b><small>{html.escape(detail)}</small>{bar}'
                  f'{f"<ul>{lines}</ul>" if lines else ""}</div></div>', unsafe_allow_html=True)


def next_step(message: str, label: str, target: str, key: str) -> None:
    """A box that says what to do next, with one button that goes there."""
    with st.container(border=True):
        c = st.columns([4, 1], vertical_alignment="center")
        c[0].markdown(md(message))
        c[1].button(label, type="primary", on_click=go, args=(target,), key=key, width="stretch")


def step_status() -> tuple[dict[str, bool], dict[str, str]]:
    """Which steps are finished, plus a short progress note (Review · 3/14)."""
    rs, checked = list(ss.receipts.values()), reviewed()
    posted = bool(rs) and all(r.status in (Status.POSTED, Status.REJECTED) for r in rs) \
        and any(r.status is Status.POSTED for r in rs)
    done = {"1. Upload": bool(rs), "2. Review": bool(rs) and checked == len(rs), "3. Summary": posted,
            "4. Close out": bool(ss.event.get("finished"))}
    return done, {"2. Review": f" · {checked}/{len(rs)}" if rs else ""}


def step_bar(current: str) -> None:
    """Mascot walker: a track with a dot per step. Finished dots get a check, and the mascot
    stands where you are, inching along Review as receipts get checked."""
    done, detail = step_status()
    i = STEPS.index(current)
    pos = i / (len(STEPS) - 1)
    if current == "2. Review" and ss.receipts:
        pos += reviewed() / len(ss.receipts) / (len(STEPS) - 1) * 0.9  # stop just short of the next dot
    pct = round(pos * 100, 2)
    dots, labels = [], []
    for n, name in enumerate(STEPS):
        left = round(n / (len(STEPS) - 1) * 100, 2)
        state = "done" if done[name] and name != current else "now" if name == current else ""
        dots.append(f'<span class="dot {state}" style="left:{left}%">{"✓" if state == "done" else ""}</span>')
        label = step_label(name) + detail.get(name, "")
        align = "start" if n == 0 else "end" if n == len(STEPS) - 1 else "mid"
        labels.append(f'<span class="{state} {align}" style="left:{left}%">{"✓ " if state == "done" else ""}{label}</span>')
    st.markdown(f'<div class="tly-walk" role="img" aria-label="Step {i + 1} of {len(STEPS)}: {step_label(current)}">'
                f'<div class="track"><div class="fill" style="width:{pct}%"></div>{"".join(dots)}'
                f'<img src="{mascot_uri(TALLY[current])}" alt="" style="left:{pct}%"></div>'
                f'<div class="stops">{"".join(labels)}</div></div>', unsafe_allow_html=True)


def html_table(rows: list[dict], numeric: tuple[str, ...] = ()) -> None:
    """A small read-only table in the app's own fonts (st.dataframe draws on a canvas in the body font)."""
    if not rows:
        return
    cols = list(rows[0])
    head = "".join(f'<th class="{"num" if c in numeric else ""}">{html.escape(c)}</th>' for c in cols)
    body = []
    for r in rows:
        cells = []
        for c in cols:
            v = r[c]
            if isinstance(v, Status):
                label, tone = STATUS_CHIP[v]
                cells.append(f'<td><span class="tly-status {tone}">{label}</span></td>')
                continue
            cells.append(f'<td class="{"num" if c in numeric else ""}">{html.escape(str(v))}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    st.markdown(f'<div class="tly-table-wrap"><table class="tly-table"><thead><tr>{head}</tr></thead>'
                f'<tbody>{"".join(body)}</tbody></table></div>', unsafe_allow_html=True)


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
    cats: dict[str, Decimal] = {}
    for i in (i for r in receipts if r.counts for i in r.items if not i.returned):
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
        legend = "".join(f'<span class="item"><i style="background:{shades[n % len(shades)]}"></i>'
                         f'<span class="name">{html.escape(k)}</span><span class="val">{usd(v)}</span></span>'
                         for n, (k, v) in enumerate(parts.items()))
        return row, legend

    in_row, in_leg = bar("in", "In", t["income"], ins, in_shades)
    out_row, out_leg = bar("out", "Out", t["expenses"], cats, out_shades)
    st.markdown(f'<div class="tly-money">{pill}{in_row}{out_row}'
                f'<div class="tly-legend">{in_leg}</div><div class="tly-legend">{out_leg}</div></div>',
                unsafe_allow_html=True)
    if t["income"] <= 0:
        st.caption("No income entered yet. Add it on the Summary step.")
