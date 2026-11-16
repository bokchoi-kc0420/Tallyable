"""Tally's tour of the demo: the page blurs, one spot stays sharp, and Tally points at it with his own
arm (the intro's Tally). It runs in the browser (static/tour.js) and waits for the user: each stop
shows when its spot is on screen, and goes away on Got it or a click on the spot."""
from __future__ import annotations

import json

import streamlit as st

from ui.common import is_demo, ss

# (spot on the page, what Tally says). Copy is Kevin's call: casual, no filler.
STOPS = [
    (".st-key-event-group", "This ticket is your Boba Social. These 4 steps close it out - follow me!"),
    (".st-key-tag-all", "First up: who paid? Pick a name and hit Apply to all, or tag each photo."),
    (".st-key-read-bar", "Now hit Read and I'll type up every receipt for you!"),
    (".st-key-clean-card", "These look clean. Give the photos a peek, then approve them all at once!"),
    ("[class*='st-key-flag-']", "I flagged this one - check it against the photo before you approve."),
    (".st-key-push-row", "Here's the money picture. Save it to get your Excel - with your real club it goes to your Sheet too."),
    (".st-key-whos-owed", "Who's owed what. Mark each person paid once you pay them back."),
    (".st-key-finish-row", "Last one! Hit Finish event to close it out."),
]


def show() -> None:
    """Every run in the demo: hand the stops to the browser. tour.js keeps its place in localStorage,
    starts over when the demo does (a new token), and hides itself outside the demo."""
    if not is_demo() or not ss.get("tour"):
        return
    cfg = json.dumps({"token": ss.tour, "stops": STOPS, "img": "app/static/intro/rig/"})
    st.html(f'<script>window.TLY_TOUR={cfg};window.tlyTour&&window.tlyTour.config(window.TLY_TOUR)</script>'
            '<script src="app/static/tour.js"></script>', unsafe_allow_javascript=True)
