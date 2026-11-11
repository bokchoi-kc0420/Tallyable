"""Step 1: drop receipts, tag who paid, and have Tally read them into receipts to check."""
from __future__ import annotations

import hashlib
import html
import io
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import streamlit as st

from treasurer.extract import ExtractionError
from treasurer.images import UPLOAD_TYPES, Prepared, UnsupportedFile, prepare, stack
from treasurer.models import LineItem, Receipt, Status
from treasurer.reader import make_extractor
from treasurer.sheets import EventInfo
from ui import start
from ui.common import ART, FAKE, dec, guide, is_demo, loading, md, next_step, payers, plural, ss, step_bar

READERS = 4  # receipts read at once: each one mostly waits on Claude, so 4 at a time take about as long as 1


def next_id(filename: str | None = None, taken: tuple | list = ()) -> str:
    """Use the file name (R03.jpg -> R03) when free, so ids match the answer key. `taken`: ids handed out
    for this batch already."""
    stem = Path(filename).stem.upper() if filename else ""
    if stem and stem not in ss.receipts and stem not in taken:
        return stem
    n = len(ss.receipts) + 1
    while f"R{n:02d}" in ss.receipts or f"R{n:02d}" in taken:
        n += 1
    return f"R{n:02d}"


def manual_form(key: str, event: EventInfo, image_file: str | None = None, data: tuple[bytes, str] | None = None) -> None:
    """Type a one-item receipt by hand. Used for lost receipts and for photos the
    reader could not handle. With `image_file`, the photo stays attached as evidence."""
    with st.form(key, enter_to_submit=False):  # a stray Enter used to add a half-typed $0 receipt
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
        st.caption("Just one line for now. You can add more on Review.")
        if not st.form_submit_button("Add"):
            return
        if not place.strip() or not item.strip():
            st.error("Fill in Place and Item, then click Add.")
            return
        if dec(total) <= 0:
            st.error("Type the Total from the receipt, then click Add.")
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


def read_one(ex, parts: list[tuple[str, bytes]], event_id: str, rid: str, seen: dict) -> tuple:
    """One receipt, on a worker thread (so no Streamlit calls here): (photo, receipt, problem, repeat).
    `repeat` is the id of the receipt a photo already read became: it isn't read (or paid for) twice.
    Several screenshots are read together as one receipt, and kept as one tall photo."""
    try:
        fs = [prepare(data, name) for name, data in parts]
    except UnsupportedFile as e:
        return None, None, str(e), None
    f = fs[0]
    if len(fs) > 1:
        f = Prepared(stack([x.data for x in fs]), f.filename, "image/jpeg", [w for x in fs for w in x.warnings])
    repeat = seen.get(hashlib.sha256(f.data).hexdigest())
    if repeat:
        return f, None, None, repeat
    try:
        more = [(x.data, x.filename) for x in fs[1:]]
        return f, ex.extract(fs[0].data, fs[0].filename, event_id, rid, more), None, None
    except ExtractionError as e:
        return f, None, f"{e} You can type it in by hand below.", None


def bundles(todo: list[tuple[str, bytes]]) -> list[list[tuple[str, bytes]]]:
    """Unread uploads as receipts: screenshots joined on the page go with their first file, in upload order."""
    out = {name: [(name, data)] for name, data in todo if ss.joins.get(name) not in dict(todo)}
    for name, data in todo:
        if name not in out:
            out[ss.joins[name]].append((name, data))
    return list(out.values())


def draft(sources: list[list[tuple[str, bytes]]], ex, reader: str, event_id: str) -> None:
    """Read the uploads into drafted receipts, a few at a time, with Tally's loading card while it works."""
    bar = st.empty()
    loading(bar, "Tally is reading your receipts", f"Starting on {plural(len(sources), 'receipt')}...", 0.0)
    seen = {hashlib.sha256(b).hexdigest(): rid for rid, (b, _) in ss.images.items()}
    rids: list[str] = []
    for parts in sources:
        rids.append(next_id(parts[0][0], rids))
    done: list[str] = []  # the last few read show as lines, the ones still waiting as skeleton lines
    with ThreadPoolExecutor(READERS) as pool:
        jobs = [pool.submit(read_one, ex, parts, event_id, rid, seen) for parts, rid in zip(sources, rids, strict=True)]
        for n, job in enumerate(as_completed(jobs), start=1):
            r = job.result()[1]
            if r:
                done.append(f"{r.receipt_id} · {r.place} · ${r.total:,.2f}")
            loading(bar, "Tally is reading your receipts", f"{n} of {len(sources)} read", n / len(sources),
                    done[-3:] + [None] * min(len(sources) - n, 3))
    skipped = 0
    for parts, rid, job in zip(sources, rids, jobs, strict=True):  # in upload order, so R01 stays first
        name = parts[0][0]
        f, r, problem, repeat = job.result()
        if problem:
            ss.failed[name] = ((f.data, f.media_type) if f else None, problem)
            continue
        if repeat:
            skipped += 1
            ss.skipped[name] = repeat
            continue
        ss.receipts[rid] = r.model_copy(update={"payer": ss.get(f"payer-{name}") or None, "image_file": name, "review_note": None})
        ss.images[rid] = (f.data, f.media_type)
        notes = f.warnings + (r.review_note.splitlines() if r.review_note else [])  # one line each on Review
        if len(parts) > 1:
            notes.append(f"Read from {len(parts)} screenshots as one receipt - check nothing is counted twice.")
        for part, _ in parts[1:]:
            ss.skipped[part] = rid  # read as part of this receipt, so it isn't read again on its own
        if notes:
            ss.notes[rid] = notes
        ss.failed.pop(name, None)
    bar.empty()
    ss.demo = []
    ss.drafted_at = ss.drafted_at or time.time()
    cost = f" (about ${ex.cost():.3f} in API calls)" if reader == "claude" else ""
    n = len(ss.receipts)
    what, them = (f"all {n} receipts", "them") if n > 1 else ("your receipt", "it")
    ss.last_draft = f"**Done! I read {what}{cost}.** Now make sure I got {them} right."
    if skipped:
        ss.last_draft += f" (Skipped {skipped} I'd already read.)"


def retag(names: list[str]) -> None:
    """Callback: a payer picked on Upload after drafting also goes on the drafted receipt,
    so Review stops saying "No payer tagged". Posted receipts stay as they are."""
    for rid, r in ss.receipts.items():
        if r.image_file in names and r.status is not Status.POSTED:
            ss.receipts[rid] = r.model_copy(update={"payer": ss.get(f"payer-{r.image_file}") or None})


def tagged_with() -> None:
    """The members picked on the Start page, with a way back there to change them."""
    c = st.columns([5, 1], vertical_alignment="center")
    c[0].markdown(md(f"**Who's in:** {', '.join(payers()[1:])}"))
    c[1].button("Edit", icon=":material/edit:", key="edit-members", width="stretch", on_click=start.reopen)


def who_paid(sources: list[tuple[str, bytes]]) -> None:
    """Step 2 of the page: set everyone at once, then fix the odd one on its photo.
    An order that came as several screenshots is joined here into one card, before it's read."""
    st.subheader("Who paid")
    c = st.columns([3, 1, 2], vertical_alignment="bottom")
    everyone = c[0].selectbox("Set every payer to", payers()[1:])  # no key: resets to the first name when members change
    if c[1].button("Apply to all"):
        for name, _ in sources:
            ss[f"payer-{name}"] = everyone
        retag([name for name, _ in sources])
        st.rerun()
    todo = unread(sources)
    joinable = [name for name, _ in todo if not name.lower().endswith(".pdf")]  # a PDF already holds every page
    with st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"):
        st.caption("Peek at the photos so you know which is which!")
        if len(joinable) > 1 and not ss.get("joining"):
            st.button("One receipt, several screenshots? Join them", type="tertiary", key="join-start",
                      on_click=ss.update, kwargs={"joining": True})
    groups = {parts[0][0]: parts for parts in bundles(sources)}  # read ones too: a joined card stays one card
    joined = {name for parts in groups.values() for name, _ in parts[1:]}
    unread_names = {name for name, _ in todo}
    with st.container(key="photo-grid"):
        for n, (name, _) in enumerate(sources):
            if name not in joined:
                photo_card(n, groups[name], pick=ss.get("joining") and name in joinable, unread=name in unread_names)


def photo_card(n: int, parts: list[tuple[str, bytes]], pick: bool, unread: bool) -> None:
    """One receipt on Upload: its photo (or its screenshots side by side) and who paid."""
    name = parts[0][0]
    with st.container(border=True, key=f"who-wide-{n}" if len(parts) > 1 else f"who-{n}"):
        if pick:
            st.checkbox(f"Join {name}", key=f"pick-{name}", label_visibility="collapsed")
        for col, (part, data) in zip(st.columns(len(parts)), parts, strict=True):
            pic = thumbnail(data, part)
            if pic:
                col.image(pic, width="stretch", alt=f"Receipt photo {part}")
            else:
                col.markdown('<div class="tly-nothumb">PDF</div>', unsafe_allow_html=True)
        if len(parts) > 1:
            with st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"):
                st.markdown(f'<b>{html.escape(name)}</b> <span class="tly-joined">{len(parts)} screenshots · 1 receipt</span>',
                            unsafe_allow_html=True)
                if unread:  # once read it's one receipt in the books: Leave out on Review is the way back
                    st.button("Split", type="tertiary", key=f"split-{name}", on_click=split, args=(name,))
        st.selectbox(name, payers(), key=f"payer-{name}", on_change=retag, args=([name],),
                     label_visibility="collapsed" if len(parts) > 1 else "visible")


def picked(sources: list[tuple[str, bytes]]) -> list[str]:
    return [name for name, _ in sources if ss.get(f"pick-{name}")]


def join(names: list[str]) -> None:
    """Callback: the ticked screenshots become one receipt, under the first one's name and payer."""
    for part in names[1:]:
        ss.joins[part] = names[0]
        ss.joins.update({k: names[0] for k, v in ss.joins.items() if v == part})  # a joined card joins as a whole
    stop_joining()


def split(name: str) -> None:
    ss.joins = {part: first for part, first in ss.joins.items() if first != name}


def stop_joining() -> None:
    ss.joining = False
    for k in [k for k in ss if str(k).startswith("pick-")]:
        del ss[k]


def unread(sources: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    """Uploads not read yet: not a receipt, not a failed file, not a repeat of one already read."""
    seen = {r.image_file for r in ss.receipts.values()} | set(ss.failed) | set(ss.skipped)
    return [(name, data) for name, data in sources if name not in seen]


def next_up(sources: list[tuple[str, bytes]], ex, reader: str, event: EventInfo) -> None:
    """The page's last step, pinned to the bottom of the screen: read the photos once everyone's
    tagged, then the way on to Review. Only one of the two shows, so there's one filled button."""
    todo = bundles(unread(sources))
    # Photos picked again after they were read: say so, or the page looks like nothing happened.
    read = {r.image_file for r in ss.receipts.values()}
    again = ", ".join(name for name, _ in sources if name in read)
    with st.container(key="upload-next"):
        if ss.get("joining"):
            names = picked([part for parts in todo for part in parts[:1]])
            with st.container(border=True, key="read-bar", horizontal=True, vertical_alignment="center"):
                title = f"{len(names)} picked" if names else "Tap the screenshots that go together"
                st.markdown(f'<p class="tly-done-title">{title}</p><p class="tly-done-sub">They\'ll be read together as '
                            'one receipt.</p>', unsafe_allow_html=True)
                with st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center"):
                    st.button("Cancel", type="tertiary", key="join-cancel", on_click=stop_joining)
                    st.button("Join into one receipt", type="primary", key="join", disabled=len(names) < 2,
                              on_click=join, args=(names,))
        elif todo:
            untagged = sum(1 for parts in todo if not ss.get(f"payer-{parts[0][0]}"))
            with st.container(border=True, key="read-bar", horizontal=True, vertical_alignment="center"):
                title, sub = ((f"{untagged} still need{'s' if untagged == 1 else ''} a payer",
                               "Tap who paid on each photo, or set them all at once.") if untagged else
                              ("Everyone's tagged!", "Tally will pull the numbers off each photo. You just give them a look."))
                st.markdown(f'<p class="tly-done-title">{title}</p><p class="tly-done-sub">{sub}</p>',
                            unsafe_allow_html=True)
                if st.button(f"Read {plural(len(todo), 'receipt')}", type="primary", disabled=untagged > 0, key="read",
                             help="Tag who paid for every receipt first" if untagged else None):
                    draft(todo, ex, reader, event.event_id)
                    st.rerun()
        elif ss.get("last_draft") or again:
            next_step(ss.get("last_draft") or f"**Nothing new to read.** Already in this event: {again}.",
                      "Go to Review →", "2. Review", "to-review")


def show(event: EventInfo) -> None:
    st.header("Upload receipts")
    step_bar("1. Upload")
    ex, reader = make_extractor()
    if reader == "claude":
        st.success(f"Reading receipts with Claude ({ex.model}).")
    elif not is_demo() and os.getenv("TALLYABLE_EXTRACTOR", "").lower() == "stub":  # start.bat, not the key
        st.warning("You opened the free version - close it and open start-with-claude.bat to read real receipts.")
    elif not is_demo():
        st.warning("Tally can't read real receipts yet: add your ANTHROPIC_API_KEY to .env. "
                   "Until then, add each purchase by hand at the bottom.")
    else:
        guide("Demo mode:", "I can only read the 14 sample receipts (I hid a few mistakes in them for you to find). "
              "Your own receipts need the full version.", key="demo", tip=True)
    if not ss.receipts and not ss.get("demo") and not ss.get("uploads"):
        with st.container(key="mascot-empty"):
            st.image(str(ART / "tally-camera.png"), width=190, alt="")
        st.markdown('<p class="tly-hint">Drop receipts, screenshots or PDFs here</p>', unsafe_allow_html=True)
    files = st.file_uploader("Receipt photos or PDFs", type=UPLOAD_TYPES, accept_multiple_files=True, key="uploads")
    if is_demo() and st.button("Use the fake event's 14 receipts instead"):  # fake receipts never reach real books
        files = None
        ss.demo = sorted((FAKE / "receipts").glob("*.jpg"))
    sources = [(f.name, f.getvalue()) for f in files] if files else [(p.name, p.read_bytes()) for p in ss.get("demo", [])]

    tagged_with()
    todo = bundles(unread(sources))
    if todo:
        guide(f"{plural(len(todo), 'receipt')} in!", md(f"Tag who paid for each one, then hit "
              f"**Read {plural(len(todo), 'receipt')}** at the bottom."), key="loaded", tip=True)
    if sources:
        who_paid(sources)
    next_up(sources, ex, reader, event)

    for name, (data, reason) in list(ss.failed.items()):
        st.error(md(f"{name}: {reason}"))
        with st.expander(f"Enter {name} by hand"):
            if data and data[1].startswith("image/"):
                st.image(data[0], width=360, alt=f"Receipt photo {name}")
            manual_form(f"manual-{name}", event, image_file=name, data=data)

    with st.expander("Add a purchase with no photo (cash, lost receipt)"):
        manual_form("manual", event)
