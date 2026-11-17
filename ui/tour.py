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
# `until` shows up (done another way). info = done at "Got it"; quiet = ring only (Tally would sit on the boxes);
# pose = which Tally (static/poses); rise = he pops up from the bottom of the screen.
# Copy is Kevin's call: casual, no filler.
STOPS = [
    {"spot": ".st-key-event-group", "info": True, "pose": "hello",
     "explain": "This ticket is your Boba Social. 4 steps and it's closed - I'll show you around, then it's your turn!"},
    {"spot": ".st-key-tag-all", "hand": ".st-key-tag-all [data-testid=stSelectbox]", "pose": "clipboard",
     "until": ".st-key-read button:not([disabled])",
     "explain": "First up: who paid? Set everyone at once up here, or pick a name under each photo. Try it!",
     "hint": "Pick who paid for these."},
    {"spot": ".st-key-apply-all", "until": ".st-key-read button:not([disabled])", "pose": "thumbs-up",
     "hint": "Nice! Now hit Apply to all."},
    {"spot": ".st-key-read", "pose": "magnify", "hint": "Everyone's tagged! Hit Read - I'll type them all up."},
    {"spot": ".st-key-to-review", "pose": "flag", "hint": "All read! Hit Go to Review."},
    {"spot": ".st-key-approve-clean", "pose": "calculator",
     "explain": "Here's what I read. Flip through with the arrows, open a photo, fix any box you want. Then approve!",
     "hint": "Looks right? Hit Approve all!"},
    {"spot": "[class*='st-key-flag-']", "hand": "[class*='st-key-approve-R']", "quiet": True, "pose": "magnify",
     "explain": "Hmm, this one doesn't add up. Check it against the photo, fix the box that's off, then hit Approve. "
                "Same deal for the other flagged ones!"},
    {"spot": ".st-key-to-summary", "pose": "tickets", "hint": "All checked! Hit Go to Summary."},
    {"spot": ".st-key-income-box", "hand": ".st-key-push-sheets, .st-key-push-excel", "until": ".st-key-books-in",
     "pose": "coin-jar", "explain": "Add what came in - try $200 in dues and watch the money bar move!", "push": True},
    {"spot": ".st-key-to-closeout", "pose": "cheer", "hint": "Books are in! Hit Next: Close out."},
    {"spot": ".st-key-whos-owed", "hand": "[class*='st-key-paid-']", "pose": "high-five",
     "explain": "Here's who's owed what. Change how you paid them back if you want.",
     "hint": "Paid them back? Hit Mark paid!"},
    {"spot": ".st-key-finish-event", "pose": "ledger", "hint": "Last one! Hit Finish event to close it out."},
    {"spot": ".st-key-next-event", "rise": True, "pose": "party", "hint": "That's it! Ready to start your next event?"},
]
PUSH = {"sheets": "Done adding? Hit Push to Google Sheets - every row goes in your club's sheet.",
        "excel": "Done adding? Hit Save and get Excel - your whole book in one file!"}


def push_line() -> str:
    """The push stop names the button that's really there (the sink is only looked up on Summary)."""
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
