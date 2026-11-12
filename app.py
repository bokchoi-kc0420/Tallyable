"""Streamlit app: Upload -> Review -> Summary -> Close out. Run with `streamlit run app.py`.

Theme lives in .streamlit/config.toml, the rest of the look in ui/*.css. Reads receipts
with Claude when ANTHROPIC_API_KEY is in .env, otherwise with the stub (fake answer key plus
planted misreads). Each step's screen is its own file in ui/.
"""
from __future__ import annotations

import hmac
import os
import time

import streamlit as st

from treasurer import session_store
from ui import close_out, club, club_home, finish, home, review, sidebar, start, summary, upload
from ui.common import ART, ROOT, is_demo, out, ss

st.set_page_config(page_title="Tallyable", page_icon=str(ART / "mascot.png"), layout="wide")
st.markdown("<style>" + "".join(p.read_text(encoding="utf-8") for p in sorted((ROOT / "ui").glob("*.css")))
            + "</style>", unsafe_allow_html=True)

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

if "event" not in ss and (saved := session_store.load(out() / "session.json")):  # a new tab: back where you left off
    ss.update(saved)
ss.setdefault("receipts", {})   # receipt_id -> Receipt
ss.setdefault("images", {})     # receipt_id -> (bytes, media type) as sent to the reader
ss.setdefault("notes", {})      # receipt_id -> photo warnings (blurry, rotated)
ss.setdefault("failed", {})     # file name -> (bytes, reason) for files that could not be read
ss.setdefault("skipped", {})    # file name -> receipt id it repeats, so a photo uploaded twice is read once
ss.setdefault("joins", {})      # screenshot file name -> the file it was joined to on Upload (one receipt)
ss.setdefault("started", time.time())
ss.setdefault("edits", 0)
ss.setdefault("drafted_at", None)    # first Draft click, for the run log
ss.setdefault("review_started", None)
ss.setdefault("income", {})

st.logo(str(ART / "logo.png"), size="large", link=sidebar.HOME_URL)
if "event" in ss:
    club.seed(ss.event)  # events from before clubs existed start "My club"
if is_demo() and not club.clubs():  # a new install: the sample club is ready to play with
    home.switch_mode(True)
if home.needs_picking():
    home.picker()
    st.stop()
home.menu()
page, event = sidebar.show()
if ss.get("view") == "club":
    club_home.show()
elif page == "1. Upload" and start.needed():
    start.show()
elif page == "1. Upload":
    upload.show(event)
elif page == "2. Review":
    review.show()
elif page == "3. Summary":
    summary.show(event)
elif ss.event.get("finished"):
    finish.show(event)
else:
    close_out.show(event)
screen = (ss.get("view"), page, ss.event.get("finished"))
if ss.get("last_screen", screen) != screen:  # Streamlit keeps the scroll spot: a new step should open at its top.
    # Last on the page, so its empty block adds no gap above the header.
    st.html("<script>document.querySelector('[data-testid=\"stMain\"]')?.scrollTo(0, 0)</script>",
            unsafe_allow_javascript=True)
ss.last_screen = screen
sidebar.save_session()
