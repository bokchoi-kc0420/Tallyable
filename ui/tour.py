"""Tally's tour of the demo: he explains a page (blurred, one spot sharp), then hands it back so it can be
tried out, nudging at the green button that does the step until it's clicked (the intro's Tally). It runs in
the browser (static/tour.js): each stop shows when its spot or button is on screen."""
from __future__ import annotations

import json

import streamlit as st

from ui.common import get_sink, is_demo, ss

# Each stop has up to two phases. Explain: the page blurs except `spot`, Tally says `explain`, and "Got it" hands
# the page back so it can be tried out. Nudge: no blur, a pulsing ring on the green button (`hand`, the spot if not
# given) with Tally peeking over it and a one-line `hint`; the stop ends when that button is clicked, or when
# `until` shows up (done another way). info = done at "Got it"; stay = clicking the button doesn't end it, only
# `until` does (the flagged receipts: one stop for all of them); dock = "top": the card starts top right;
# pose = which Tally (static/poses); end = the last one: a card in the middle
# asking what's next (their own club, or another demo event at `spot`'s button); typed = the explain moves on
# once the spot shows that text (the total, after they put the amount in).
# back = where to point when the spot is gone (the book pop-up was closed), saying `back_hint`.
# Copy is Kevin's call: casual, no filler.
STOPS = [
    {"spot": ".st-key-event-group", "info": True, "pose": "hello",
     "explain": "This is your Boba Social! It takes 4 steps to close, so I'll show you around first."},
    {"spot": ".st-key-tag-all", "hand": ".st-key-apply-all", "pose": "clipboard", "stay": True,
     "until": ".st-key-read button:not([disabled])",
     "explain": "First of all, who paid? Either pick a name here to apply to every receipt or one under each photo.",
     "hint": "Pick a name, then Apply to all."},
    {"spot": ".st-key-read", "pose": "magnify", "hint": "Everyone's tagged! Hit Read and I'll read all of them."},
    {"spot": ".st-key-to-review", "pose": "flag", "hint": "All read. On to Review!"},
    {"spot": ".st-key-approve-clean", "pose": "calculator",
     "explain": "This is what I read off each receipt. If a box looks wrong, click it and fix it.",
     "hint": "Looks right? Approve them all."},
    {"spot": "[class*='st-key-flag-']", "stay": True, "dock": "top", "pose": "magnify",
     "until": ".st-key-to-summary",
     "explain": "This one's off by 8 cents. The tax box is highlighted. Match it to the photo, then Approve."
                " The ones over $50 get a quick look too.",
     "hint": "Fix the red box and Approve shows up."},
    {"spot": ".st-key-to-summary", "pose": "tickets", "hint": "All checked. On to Summary!"},
    {"spot": ".st-key-income-box", "hand": ".st-key-push-sheets, .st-key-push-excel", "until": ".st-key-books-in",
     "pose": "coin-jar", "typed": "$700.00", "push": True,
     "explain": "That's how much money you made from the event! Let's try with $700 for now."},
    {"spot": ".st-key-sheet-peek", "hand": ".st-key-peek-ok", "until": ".st-key-books-in", "pose": "thumbs-up",
     "back": ".st-key-push-sheets", "back_hint": "Hit Push to Google Sheets to open your book again.",
     "hint": "This is your book. Flip through the tabs, then hit Looks good."},
    {"spot": ".st-key-to-closeout", "pose": "cheer", "hint": "Books are in! Next step is to pay people back."},
    {"spot": ".st-key-whos-owed", "hand": "[class*='st-key-paid-'] button", "pose": "high-five",
     "explain": "Whoever fronted the money is owed it. Pick how you paid them back.",
     "hint": "Paid them back? Mark paid."},
    {"spot": ".st-key-finish-event", "pose": "ledger", "hint": "Last step! Let's close out this event. Click Finish event."},
    {"spot": ".st-key-next-event", "end": True, "pose": "party", "title": "Boba Social's done!",
     "explain": "Ready to try it with your club?"},
]
PUSH = {"sheets": "Let's push the numbers into your club's sheet.",
        "excel": "Done adding? Hit Save and get Excel - your whole book in one file!"}


def push_line() -> str:
    """The push stop names the button that's really there (the sink is only looked up on Summary)."""
    if is_demo():  # the demo always shows Sheets (it opens a peek at the book)
        return PUSH["sheets"]
    if ss.get("step") != "3. Summary":
        return PUSH["excel"]
    return PUSH["sheets" if get_sink()[0].label == "Google Sheets" else "excel"]


def show() -> None:
    """Every run in the demo: hand the stops to the browser. tour.js keeps its place in localStorage,
    starts over when the demo does (a new token), and hides itself outside the demo."""
    if not is_demo() or not ss.get("tour"):
        return
    stops = [{**s, "hint": push_line()} if s.get("push") else s for s in STOPS]
    cfg = json.dumps({"token": ss.tour, "stops": stops, "img": "app/static/poses/"})
    st.html(f'<script>window.TLY_TOUR={cfg};window.tlyTour&&window.tlyTour.config(window.TLY_TOUR)</script>'
            '<script src="app/static/tour.js"></script>', unsafe_allow_javascript=True)
