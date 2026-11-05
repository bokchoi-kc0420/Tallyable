"""Streamlit app: Upload -> Review -> Summary -> Close out. Run with `streamlit run app.py`.

Theme lives in .streamlit/config.toml, the rest of the look in ui/style.css. Reads receipts
with Claude when ANTHROPIC_API_KEY is in .env, otherwise with the stub (fake answer key plus
planted misreads). Each step's screen is its own file in ui/.
"""
from __future__ import annotations

import hmac
import os
import time

import streamlit as st

from ui import close_out, review, sidebar, summary, upload
from ui.common import ART, ROOT, ss

st.set_page_config(page_title="Tallyable", page_icon=str(ART / "mascot.png"), layout="wide")
st.markdown(f"<style>{(ROOT / 'ui' / 'style.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

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

page, event = sidebar.show()
if page == "1. Upload":
    upload.show(event)
elif page == "2. Review":
    review.show()
elif page == "3. Summary":
    summary.show(event)
else:
    close_out.show(event)
sidebar.save_session()
