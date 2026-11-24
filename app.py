"""Streamlit app: Upload -> Review -> Summary -> Close out. Run with `streamlit run app.py`.

Theme lives in .streamlit/config.toml, the rest of the look in ui/*.css. Reads receipts
with Claude when ANTHROPIC_API_KEY is in .env, otherwise with the stub (fake answer key plus
planted misreads). Each step's screen is its own file in ui/.
"""
from __future__ import annotations

import hmac
import html
import os
import time

import streamlit as st

from treasurer import backup, session_store
from ui import close_out, club, club_home, finish, home, review, sidebar, start, summary, tour, upload, welcome
from ui.common import ART, DATA, DEMO_RECEIPTS, LANDING, PRIVACY, ROOT, base, hosted, is_demo, out, signed_in_email, ss

st.set_page_config(page_title="Tallyable", page_icon=str(ART / "mascot.png"), layout="wide")
first_load = "loaded" not in ss  # the page settles after a first run: the loading bar and blur play out (style.css)
ss.loaded = True
settle = "[data-testid=stApp]{--tly-load-in:tly-load-in;--tly-bar-in:tly-bar-in}" if first_load else ""
st.markdown("<style>" + "".join(p.read_text(encoding="utf-8") for p in sorted((ROOT / "ui").glob("*.css")))
            + settle + "</style>", unsafe_allow_html=True)

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

# The hosted link: each treasurer signs in with Google, so their clubs, events and sheets stay theirs.
if hosted() and not st.user.is_logged_in:
    st.header("Tallyable")
    st.button("Sign in with Google", type="primary", icon=":material/login:", on_click=st.login)
    st.stop()

if backup.on():  # the host wipes its disk on restart: put this account's folder back, then save the last run's changes
    ss.backed_up = backup.push(base(), DATA, ss.get("backed_up") or backup.restore(base(), DATA))
welcome.start_demo_from_link()  # the intro's Skip / "Try it with these receipts" link
if "event" not in ss and (saved := session_store.load(out() / "session.json")):  # a new tab: back where you left off
    ss.update(saved)
if is_demo() and "tour" not in ss and (out() / "tour.txt").exists():  # a refresh mid-demo: same tour, same receipts
    ss.tour = (out() / "tour.txt").read_text()
    if not ss.get("receipts"):
        ss.demo = list(DEMO_RECEIPTS)
if "opened" not in ss and "view" not in ss and not is_demo():  # every launch opens on club home, not where
    home.go_home()                                             # the last visit stopped (after the password page too)
ss.opened = True
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

if ss.get("view") == "intro":
    welcome.intro()
    st.stop()
st.logo(str(ART / "logo.png"), size="large")
if "event" in ss:
    club.seed(ss.event)  # events from before clubs existed start "My club"
if is_demo() and not club.clubs():  # a new install: the sample club is ready to play with
    home.switch_mode(True)
if home.needs_picking():
    home.picker()
    st.stop()
# Clicking the logo opens the landing site in this tab: a see-through link on top of it (style.css), since
# st.logo's own link opens a new tab. After the picker, so the welcome page gets no sidebar.
with st.sidebar.container(key="logo-home"):
    st.markdown(f'<a href="{LANDING}" target="_top" aria-label="Tallyable website"></a>', unsafe_allow_html=True)
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
with st.sidebar.container(key="account"):  # the hosted link: whose books these are, and a way out on a shared laptop
    if email := signed_in_email():
        st.html(f'<p class="tly-account">Signed in as {html.escape(email)}</p>')  # text, not a mailto link
        st.button("Sign out", type="tertiary", icon=":material/logout:", key="sign-out", on_click=st.logout)
    st.html(f'<p class="tly-account"><a href="{PRIVACY}" target="_blank">Privacy</a></p>')
screen = (ss.get("view"), page, ss.event.get("finished"))
# Last on the page, so its empty block adds no gap above the header.
if ss.get("last_screen", screen) != screen and page == "4. Close out" and not screen[2] and screen[0] != "club":
    # Close out opens on Who's owed: the cheer at the top pushed it under the fold, so it looked empty (Kevin).
    st.html("<script>setTimeout(() => document.querySelector('.st-key-whos-owed')?.scrollIntoView({block: 'start'}), 300)"
            "</script>", unsafe_allow_javascript=True)
elif ss.get("last_screen", screen) != screen:  # Streamlit keeps the scroll spot: a new step should open at its top.
    st.html("<script>document.querySelector('[data-testid=\"stMain\"]')?.scrollTo(0, 0)</script>",
            unsafe_allow_javascript=True)
elif target := ss.pop("scroll_to", None):  # a section just finished: bring up what comes next
    st.html(f"<script>setTimeout(() => document.querySelector('{target}')?.scrollIntoView("
            "{behavior: 'smooth', block: 'center'}), 300)</script>", unsafe_allow_javascript=True)
ss.last_screen = screen
tour.show()
sidebar.save_session()
if backup.on():
    ss.backed_up = backup.push(base(), DATA, ss.backed_up)
