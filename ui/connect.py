"""Connect your own Google Sheets: paste the link, share it with Tallyable's bot, done.
The links are saved with the open club (output/clubs.json), so each club has its own books."""
from __future__ import annotations

import streamlit as st

from treasurer.sheets import bot_client, bot_email, sheet_id
from ui import club
from ui.common import GCP_KEY, ROOT, signed_in_email


def linked() -> dict:
    return club.load()["sheets"]


def check(ids: dict, email: str | None = None) -> str | None:
    """None if the bot can open every linked sheet, else what to tell the treasurer. On the hosted
    link (`email` = the signed-in account) the sheet must also be one that account can edit, so a
    club can't push into another club's books just by pasting their link."""
    client = bot_client(ROOT, GCP_KEY)
    for name, sid in ids.items():
        what = "ledger" if name == "ledger" else "event"
        try:
            book = client.open_by_key(sid)
        except Exception:
            return f"Tally can't open your {what} sheet yet. In Share, paste the email above into Add people as Editor!"
        try:  # rewrite the title as it is: harmless, but only an Editor may do it
            book.batch_update({"requests": [{"updateSpreadsheetProperties": {
                "properties": {"title": book.title}, "fields": "title"}}]})
        except Exception:
            return f"Tally can see your {what} sheet but can't edit it. In Share, add the email above as Editor!"
        if open_to_anyone(client, sid):
            return (f"Anyone with the link can edit your {what} sheet right now. In Share, add the email above "
                    "under Add people, then set General access back to Restricted.")
        if email and not can_edit(client, sid, email):
            return (f"{email} isn't an editor on that {what} sheet, so Tally won't link it. "
                    "Use a sheet your Google account owns or can edit.")
    return None


def can_edit(client, sid: str, email: str) -> bool:
    """The signed-in person is named as an editor or owner of the sheet. False when Google won't say:
    on the hosted link, an unknown owner is never good enough."""
    try:
        return any(p.get("emailAddress", "").lower() == email and p.get("role") in ("writer", "owner")
                   for p in client.list_permissions(sid))
    except Exception:
        return False


def open_to_anyone(client, sid: str) -> bool:
    """The sheet's link lets anyone edit it: the club's books would be open to whoever the link reaches.
    False when Google won't say, so a sheet never gets stuck on this check."""
    try:
        return any(p.get("type") == "anyone" and p.get("role") in ("writer", "owner") for p in client.list_permissions(sid))
    except Exception:
        return False


@st.dialog("Connect your Google Sheets", width="large")
def dialog() -> None:
    box("dialog")


def box(key: str) -> None:
    """The connect form. `key` keeps widget keys apart where it's drawn twice."""
    email = bot_email(ROOT, GCP_KEY)
    if not email:
        st.caption("Google Sheets isn't set up on this copy of Tallyable, so your books come out as an Excel file.")
        return
    saved = linked()
    st.markdown("**1. Share your sheets with Tally:** hit Share in Google Sheets, paste this into **Add people**, "
                "and pick Editor.")
    st.code(email, language=None, width="content")  # Copy sits right by the email
    st.caption("Leave General access on Restricted, so only Tally and the people you add can open your books.")
    st.markdown("**2. Paste the links here.**")
    book = st.text_input("Event books (balance sheet, expenses, receipts)", key=f"{key}-book",
                         value=f"https://docs.google.com/spreadsheets/d/{saved['book']}" if saved.get("book") else "",
                         placeholder="https://docs.google.com/spreadsheets/d/...")
    ledger = st.text_input("General Ledger (optional: leave blank to keep it in the same sheet)", key=f"{key}-ledger",
                           value=f"https://docs.google.com/spreadsheets/d/{saved['ledger']}" if saved.get("ledger") else "",
                           placeholder="https://docs.google.com/spreadsheets/d/...")
    if not st.button("Connect!", type="primary" if key == "dialog" else "secondary", icon=":material/link:",
                     key=f"{key}-go"):  # on Summary, Push stays the one filled button
        return
    ids = {"book": sheet_id(book), "ledger": sheet_id(ledger)} if ledger.strip() else {"book": sheet_id(book)}
    if not all(ids.values()):
        st.error("That doesn't look like a Google Sheets link. Copy it from your browser's address bar!")
        return
    with st.spinner("Checking Tally can open it..."):
        problem = check(ids, signed_in_email())
    if problem:
        st.error(problem + " Then hit Connect again.")
        return
    club.save(sheets=ids)
    st.toast("Connected! Push sends your books there now.", icon=":material/celebration:")
    st.rerun()
