"""Step 1: drop receipts, tag who paid, and have them read into draft rows."""
from __future__ import annotations

import hashlib
import io
import time
from pathlib import Path

import streamlit as st

from treasurer import session_store
from treasurer.extract import ExtractionError
from treasurer.images import UPLOAD_TYPES, UnsupportedFile, prepare
from treasurer.models import LineItem, Receipt, Status
from treasurer.reader import make_extractor
from treasurer.sheets import EventInfo
from ui.common import ART, FAKE, SESSION_FILE, dec, guide, loading, md, next_step, payers, ss, step_bar


def next_id(filename: str | None = None) -> str:
    """Use the file name (R03.jpg -> R03) when free, so ids match the answer key."""
    stem = Path(filename).stem.upper() if filename else ""
    if stem and stem not in ss.receipts:
        return stem
    n = len(ss.receipts) + 1
    while f"R{n:02d}" in ss.receipts:
        n += 1
    return f"R{n:02d}"


def manual_form(key: str, event: EventInfo, image_file: str | None = None, data: tuple[bytes, str] | None = None) -> None:
    """Type a one-item receipt by hand. Used for lost receipts and for photos the
    reader could not handle. With `image_file`, the photo stays attached as evidence."""
    with st.form(key):
        c = st.columns(3)
        place = c[0].text_input("Place")
        d = c[1].date_input("Date", value=event.date)
        payer = c[2].selectbox("Payer", payers())
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
            ss.receipts[rid] = Receipt(receipt_id=rid, event_id=event.event_id, place=place.strip(), date=d,
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


@st.cache_data(max_entries=200, show_spinner=False)
def thumbnail(data: bytes, name: str) -> bytes | None:
    """A small JPEG of an upload for the Who paid grid; None for PDFs or files that won't open."""
    try:
        f = prepare(data, name)
        if not f.media_type.startswith("image/"):
            return None
        from PIL import Image
        im = Image.open(io.BytesIO(f.data)).convert("RGB")
        im.thumbnail((360, 260))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=80)
        return out.getvalue()
    except Exception:  # a bad file shows its error later, when it is read
        return None


def draft(sources: list[tuple[str, bytes]], ex, reader: str, event_id: str) -> None:
    """Read each upload into a drafted receipt, with Tally's loading card while it works."""
    bar = st.empty()
    loading(bar, "Tally is reading your receipts", f"Starting on {len(sources)} receipts...", 0.0)
    seen = {hashlib.sha256(b).hexdigest() for b, _ in ss.images.values()}
    skipped = []
    for n, (name, data) in enumerate(sources):
        loading(bar, "Tally is reading your receipts", f"{name} · {n + 1} of {len(sources)}", n / len(sources))
        try:
            f = prepare(data, name)
        except UnsupportedFile as e:
            ss.failed[name] = (None, str(e))
            continue
        if hashlib.sha256(f.data).hexdigest() in seen:  # already drafted: don't read (or pay) twice
            skipped.append(name)
            continue
        rid = next_id(name)
        try:
            r = ex.extract(f.data, f.filename, event_id, rid)
        except ExtractionError as e:
            ss.failed[name] = ((f.data, f.media_type), f"{e} You can type it in by hand below.")
            continue
        ss.receipts[rid] = r.model_copy(update={"payer": ss.get(f"payer-{name}") or None, "image_file": name})
        ss.images[rid] = (f.data, f.media_type)
        notes = f.warnings + ([f"Reader's note: {r.review_note}"] if r.review_note else [])
        if notes:
            ss.notes[rid] = notes
        ss.failed.pop(name, None)
    bar.empty()
    ss.demo = []
    ss.drafted_at = ss.drafted_at or time.time()
    cost = f" (about ${ex.cost():.3f} in API calls)" if reader == "claude" else ""
    ss.last_draft = f"**Drafted {len(ss.receipts)} receipts{cost}.** Next, check each one against its photo."
    if skipped:
        ss.last_draft += f" Skipped {len(skipped)} already drafted: {', '.join(skipped)}."


def offer_resume() -> None:
    """On a fresh start, offer the session saved on disk (only when it has receipts)."""
    saved = session_store.load(SESSION_FILE) if not ss.receipts and SESSION_FILE.exists() else None
    if not saved or not saved["receipts"]:
        return
    n = len(saved["receipts"])
    done = sum(1 for r in saved["receipts"].values() if r.status is not Status.DRAFTED)
    with guide("Welcome back!", f"You have a saved session for {saved['event']['name']}: "
               f"{n} receipts, {done} reviewed.", key="resume", tip=True):
        resume = st.button("Resume where I left off")
    if not resume:
        return
    for k, v in saved.items():
        ss[k] = v
    st.rerun()


def show(event: EventInfo) -> None:
    st.header("Upload receipts")
    step_bar("1. Upload")
    offer_resume()
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
        everyone = c[0].selectbox("Set every payer to", payers()[1:], key="payer-all")
        if c[1].button("Apply to all"):
            for name, _ in sources:
                ss[f"payer-{name}"] = everyone
            st.rerun()
        if c[2].button("Draft rows", type="primary"):
            draft(sources, ex, reader, event.event_id)
    if ss.get("last_draft") and ss.receipts:
        next_step(ss.last_draft, "Go to Review →", "2. Review", "to-review")

    if sources:
        st.subheader("Who paid")
        st.caption("Each receipt's photo is shown, so you can tell them apart without opening them.")
        grid = st.columns(4)
        for n, (name, data) in enumerate(sources):
            with grid[n % 4].container(border=True, key=f"who-{n}"):
                pic = thumbnail(data, name)
                if pic:
                    st.image(pic, width="stretch")
                else:
                    st.markdown('<div class="tly-nothumb">PDF</div>', unsafe_allow_html=True)
                st.selectbox(name, payers(), key=f"payer-{name}")

    for name, (data, reason) in list(ss.failed.items()):
        st.error(md(f"{name}: {reason}"))
        with st.expander(f"Enter {name} by hand"):
            if data and data[1].startswith("image/"):
                st.image(data[0], width=360)
            manual_form(f"manual-{name}", event, image_file=name, data=data)

    with st.expander("Add a purchase with no photo (cash, lost receipt)"):
        manual_form("manual", event)
