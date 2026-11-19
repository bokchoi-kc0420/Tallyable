"""The demo's books step (Kevin's pick C): Push to Google Sheets is there, but the demo has no club sheet, so
it opens a peek at the book instead, tab by tab as the sheet would show it, with the Excel file to take away."""
from __future__ import annotations

import html
import string
from decimal import Decimal

import streamlit as st

from ui.common import ss


def cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (Decimal, float)) and not isinstance(v, bool):
        return f"${v:,.2f}" if v >= 0 else f"-${-v:,.2f}"
    return html.escape(str(v))


def grid(rows: list[list], widths: list[int]) -> str:
    """A tab drawn like a spreadsheet: lettered columns at the sheet's own widths, numbered rows, light grid lines."""
    width = max((len(r) for r in rows), default=0)
    cols = "".join(f'<col style="width:{w}px">' for w in (widths or [120] * width)[:width])
    head = "".join(f"<th>{string.ascii_uppercase[i % 26]}</th>" for i in range(width))
    body = "".join(f"<tr><th>{n}</th>" + "".join(f"<td>{cell(v)}</td>" for v in r) + "<td></td>" * (width - len(r)) + "</tr>"
                   for n, r in enumerate(rows, 1))
    return f'<div class="tly-sheet"><table><col style="width:40px">{cols}<tr><th></th>{head}</tr>{body}</table></div>'


def peek() -> None:
    ss.event = {**ss.event, "peek": True}  # per event, so the next one starts closed


def show(views: dict, done: bool, waiting: list, download) -> None:
    """The green Push to Google Sheets button, and once clicked the peek with its Download as Excel (`download`
    draws that button and saves the books when it's clicked)."""
    with st.container(horizontal=True, key="push-row"):
        st.button("Push to Google Sheets", type="secondary" if done or ss.event.get("peek") else "primary",
                  disabled=bool(waiting), icon=":material/upload:", key="push-sheets", on_click=peek)
    if not ss.event.get("peek") or not views:
        return
    with st.container(border=True, key="sheet-peek"):
        st.markdown("**Sheets is for real clubs** - here's what would go in yours:")
        for tab, view in zip(st.tabs(list(views)), views.values(), strict=True):
            tab.html(grid(view.grid, view.widths))
        download()
