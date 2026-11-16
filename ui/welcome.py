"""The first screen of a new install: a close-out receipt prints out with the two ways in, setting
up your club or watching the demo. The demo plays the intro animation first (full only the first
time), and the intro's last frame hands off into the sample event, where Tally gives the tour."""
from __future__ import annotations

import streamlit as st

from ui.common import BASE, mascot_uri, ss

INTRO_SEEN = BASE / "intro_seen"  # the intro auto-plays in full once; after that the demo opens right away
LINES = [("Receipts in", "done"), ("Read by Tally", "done"), ("Math checked", "done"), ("Who's owed", "done"),
         ("Pushed to your Sheet", "done")]


def watch_demo() -> None:
    """Watch the demo callback: the intro the first time, straight into the demo after that."""
    if INTRO_SEEN.exists():
        from ui.home import switch_mode
        switch_mode(True)
        return
    ss.view = "intro"


def start_demo_from_link() -> bool:
    """The intro's Skip and "Try it with these receipts" links come back as ?demo=go (a new page load)."""
    if st.query_params.get("demo") != "go":
        return False
    st.query_params.clear()
    BASE.mkdir(parents=True, exist_ok=True)
    INTRO_SEEN.touch()
    from ui.home import switch_mode
    switch_mode(True)
    return True


def intro() -> None:
    """The intro animation over the whole window, with a way past it."""
    # Made by a script, not st.html markup: Streamlit strips iframes from markup and sandboxes its own, and the
    # intro's last button has to reload this page (?demo=go). No tags in the script text: Streamlit drops those scripts.
    st.html("""<script>if (!document.getElementById("tly-intro")) {
      const d = document.createElement("div"), f = document.createElement("iframe"), a = document.createElement("a");
      d.id = "tly-intro"; f.src = "app/static/intro/index.html"; f.title = "Tallyable intro";
      a.className = "tly-intro-skip"; a.href = "?demo=go"; a.textContent = "Skip intro";
      d.append(f, a); document.body.append(d); }</script>""", unsafe_allow_javascript=True)


def receipt() -> None:
    lines = "".join(f'<div class="ln"><span>{k}</span><i></i><span{" class=ok" if v == "done" else ""}>{v}</span></div>'
                    for k, v in LINES)
    with st.container(key="welcome"):
        st.html(f'<div class="tly-printer"><span>TALLYABLE</span><i></i></div>'
                f'<img class="tly-welcome-tally" src="{mascot_uri("tally-magnify.png")}" alt="">'
                '<p class="tly-welcome-bub">Every receipt, read and checked - you just approve!</p>')
        with st.container(key="welcome-rc"):
            st.html(f'<img class="logo" src="{mascot_uri("logo.png")}" alt="Tallyable">'
                    '<p class="ce">CLOSE-OUT RECEIPT · BOBA SOCIAL</p>'
                    '<p class="big">Close out events without the receipt pile.</p>'
                    f'<div class="hr"></div>{lines}<div class="hr"></div>'
                    '<div class="tot"><span>Your time</span><span>~3 min</span></div><div class="hr"></div>')
            st.button("Set up my club", icon=":material/arrow_forward:", icon_position="right", type="primary",
                      key="welcome-setup", width="stretch", on_click=lambda: ss.update(club_form=True))
            st.button("Just looking? Watch the demo", icon=":material/play_circle:", key="welcome-demo",
                      width="stretch", on_click=watch_demo)
            st.html('<div class="bc"></div>')
