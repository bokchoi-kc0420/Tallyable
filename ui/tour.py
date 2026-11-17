"""Tally's tour of the demo: the page blurs, one spot stays sharp, and Tally puts his hand on the green
button that does the step (the intro's Tally). It runs in the browser (static/tour.js) and waits for
the user: each stop shows when its spot is on screen, and moves on once that button is clicked."""
from __future__ import annotations

import json

import streamlit as st

from ui.common import get_sink, is_demo, ss

# Each stop: spot = what stays sharp, hand = the green button Tally points at (the spot itself if not
# given; a click on it finishes the stop), info = a "Got it" stop with no button, until = a sign the
# step got done another way, clear = no blur, so the page can be edited. Copy is Kevin's call: casual, no filler.
STOPS = [
    {"spot": ".st-key-event-group", "info": True,
     "text": "This ticket is your Boba Social. 4 steps and it's closed - just follow the green buttons!"},
    {"spot": ".st-key-tag-all", "hand": ".st-key-apply-all", "until": ".st-key-read button:not([disabled])",
     "text": "First up: who paid? Pick a name, then hit Apply to all!"},
    {"spot": ".st-key-read", "text": "Now hit Read 14 receipts - I'll type them all up!"},
    {"spot": ".st-key-to-review", "text": "All read! Hit Go to Review to check my work."},
    {"spot": ".st-key-approve-clean", "text": "These add up. Peek at a photo or two, then hit Approve all!"},
    {"spot": "[class*='st-key-flag-']", "info": True,
     "text": "I flagged this one - check it against the photo, fix the box that's off, then hit Approve. "
             "Same deal for the other flagged ones!"},
    {"spot": "[class*='st-key-approve-R']", "clear": True, "text": ""},  # just a ring: Tally would sit on the boxes
    {"spot": ".st-key-to-summary", "text": "All checked! Hit Go to Summary."},
    {"spot": ".st-key-push-sheets, .st-key-push-excel", "until": ".st-key-books-in", "push": True, "text": ""},
    {"spot": ".st-key-to-closeout", "text": "Books are in! Hit Next: Close out to pay people back."},
    {"spot": "[class*='st-key-paid-']", "text": "Paid them back? Hit Mark paid!"},
    {"spot": ".st-key-finish-event", "text": "Last one! Hit Finish event to close it out."},
]
PUSH = {"sheets": "Hit Push to Google Sheets - I'll write every row into your club's sheet.",
        "excel": "Hit Save and get Excel - your whole book in one file!"}


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
    stops = [{**s, "text": push_line()} if s.get("push") else s for s in STOPS]
    cfg = json.dumps({"token": ss.tour, "stops": stops, "img": "app/static/intro/rig/"})
    st.html(f'<script>window.TLY_TOUR={cfg};window.tlyTour&&window.tlyTour.config(window.TLY_TOUR)</script>'
            '<script src="app/static/tour.js"></script>', unsafe_allow_javascript=True)
