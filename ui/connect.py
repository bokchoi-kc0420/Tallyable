"""Connect your own Google Sheets: paste the link, share it with Tallyable's bot, done.
The links are saved with the open club (output/clubs.json), so each club has its own books."""
from __future__ import annotations

import streamlit as st

from treasurer.sheets import bot_client, bot_email, sheet_id
from ui import club
from ui.common import GCP_KEY, ROOT


def linked() -> dict:
    return club.load()["sheets"]


def check(ids: dict) -> str | None:
    """None if the bot can open every linked sheet, else what to tell the treasurer."""
    client = bot_client(ROOT, GCP_KEY)
    for name, sid in ids.items():
        what = "ledger" if name == "ledger" else "event"
        try:
            book = client.open_by_key(sid)
        except Exception:
            return f"Tally can't open your {what} sheet yet. Did you share it?"
        try:  # rewrite the title as it is: harmless, but only an Editor may do it
            book.batch_update({"requests": [{"updateSpreadsheetProperties": {
                "properties": {"title": book.title}, "fields": "title"}}]})
        except Exception:
            return f"Tally can see your {what} sheet but can't write to it. Share it as Editor, not Viewer!"
    return None


@st.dialog("Connect your Google Sheets", width="large")
def dialog() -> None:
    box("dialog")


def box(key: str) -> None:
    """The connect form. `key` keeps widget keys apart where it's drawn twice."""
    email = bot_email(ROOT, GCP_KEY)
    if not email:
        st.caption("Google Sheets isn't set up on this copy of Tallyable, so your books save on this computer.")
        return
    saved = linked()
    st.markdown("**1. Share your sheets with Tally** as Editor (Share button, top right in Google Sheets):")
    st.code(email, language=None)
    st.markdown("**2. Paste the links here.**")
    book = st.text_input("Event books (balance sheet, expenses, receipts)", key=f"{key}-book",
                         value=f"https://docs.google.com/spreadsheets/d/{saved['book']}" if saved.get("book") else "",
                         placeholder="https://docs.google.com/spreadsheets/d/...")
    ledger = st.text_input("General Ledger (optional: leave blank to keep it in the same sheet)", key=f"{key}-ledger",
                           value=f"https://docs.google.com/spreadsheets/d/{saved['ledger']}" if saved.get("ledger") else "",
                           placeholder="https://docs.google.com/spreadsheets/d/...")
    if not st.button("Connect!", type="primary", icon=":material/link:", key=f"{key}-go"):
        return
    ids = {"book": sheet_id(book), "ledger": sheet_id(ledger)} if ledger.strip() else {"book": sheet_id(book)}
    if not all(ids.values()):
        st.error("That doesn't look like a Google Sheets link. Copy it from your browser's address bar!")
        return
    with st.spinner("Checking Tally can open it..."):
        problem = check(ids)
    if problem:
        st.error(problem + f" Share it with {email} as Editor, then hit Connect again.")
        return
    club.save(sheets=ids)
    st.toast("Connected! Push sends your books there now.", icon=":material/celebration:")
    st.rerun()
