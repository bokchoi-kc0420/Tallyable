"""The demo's books step (Kevin's pick C): Push to Google Sheets is there, but the demo has no club sheet, so
it opens a pop-up with the book, tab by tab as the sheet would show it (with its fills, merges and money format),
and the Excel file to take away."""
from __future__ import annotations

import html
import string
from decimal import Decimal

import streamlit as st

from treasurer.views import View
from ui.common import ss

SIDES = ("top", "bottom", "left", "right")


def cell(v, money=None) -> str:
    if v is None:
        return ""
    if not isinstance(v, (Decimal, float, int)) or isinstance(v, bool):
        return html.escape(str(v))
    if not money:
        return f"{v:,}" if isinstance(v, int) else f"{v:,.2f}"
    if money is True and v == 0:
        return "$ -"  # accounting format, as in the sheet
    return f"${v:,.2f}" if v >= 0 else f"-${-v:,.2f}"


def styles(view: View, h: int, w: int) -> tuple[list[list[dict]], dict, set]:
    """Each cell's look, the merged ranges by their top-left cell, and the cells a merge covers."""
    looks = [[{} for _ in range(w)] for _ in range(h)]
    spans, covered = {}, set()
    for lk in view.looks:
        (r0, r1), (c0, c1) = lk["rows"], lk["cols"]
        border = lk.get("border")
        for r in range(r0, min(r1, h)):
            for c in range(c0, min(c1, w)):
                s = looks[r][c]
                s.update({k: v for k, v in lk.items() if k not in ("rows", "cols", "border", "merge")})
                edges = {"top": r == r0, "bottom": r == r1 - 1, "left": c == c0, "right": c == c1 - 1}
                sides = SIDES if border in ("grid", "box") else ("top", "bottom") if border == "topbottom" else ()
                for side in sides:
                    if border == "grid" or edges[side]:
                        s[side] = True
                if lk.get("merge") and (r, c) != (r0, c0):
                    covered.add((r, c))
        if lk.get("merge"):
            spans[(r0, c0)] = (r1 - r0, c1 - c0)
    return looks, spans, covered


def css(s: dict, number: bool) -> str:
    out = [f"background:#{s['fill']}" if s.get("fill") else "", f"color:#{s['color']}" if s.get("color") else "",
           "font-weight:700" if s.get("bold") else "", "font-style:italic" if s.get("italic") else "",
           "text-decoration:line-through" if s.get("strike") else "", f"font-size:{s['size'] * 4 // 3}px" if s.get("size") else "",
           "white-space:normal" if s.get("wrap") else "", f"text-align:{s.get('align') or ('right' if number else 'left')}"]
    out += [f"border-{side}:2px solid var(--tly-ink)" for side in SIDES if s.get(side)]
    return ";".join(x for x in out if x)


def grid(view: View) -> str:
    """A tab drawn like the club's sheet: lettered columns at the sheet's widths, numbered rows, and its look."""
    rows = view.grid
    h, w = len(rows), max((len(r) for r in rows), default=0)
    widths = [round(x * 1.15) for x in (view.widths or [120] * w)[:w]]  # the sheet's px are for its smaller font
    looks, spans, covered = styles(view, h, w)
    head = "".join(f"<th>{string.ascii_uppercase[i % 26]}</th>" for i in range(w))
    body = []
    for r, row in enumerate(rows):
        tds = []
        if len([v for v in row if v not in (None, "")]) == 1 and row[0] not in (None, "") and (r, 0) not in spans:
            spans[(r, 0)] = (1, w)  # a lone line (the note, a title) runs across the empty cells, as in Sheets
            covered |= {(r, c) for c in range(1, w)}
        for c in range(w):
            if (r, c) in covered:
                continue
            v = row[c] if c < len(row) else None
            n, k = spans.get((r, c), (1, 1))
            span = (f' rowspan="{n}"' if n > 1 else "") + (f' colspan="{k}"' if k > 1 else "")
            number = isinstance(v, (Decimal, float, int)) and not isinstance(v, bool)
            tds.append(f'<td{span} style="{css(looks[r][c], number)}">{cell(v, looks[r][c].get("money"))}</td>')
        height = f' style="height:{view.heights[r]}px"' if r in view.heights else ""
        body.append(f"<tr{height}><th>{r + 1}</th>{''.join(tds)}</tr>")
    cols = "".join(f'<col style="width:{x}px">' for x in widths)
    return (f'<div class="tly-sheet"><table style="width:{40 + sum(widths)}px"><col style="width:40px">{cols}'
            f"<tr><th></th>{head}</tr>{''.join(body)}</table></div>")


def show(views: dict, done: bool, waiting: list, download, save) -> None:
    """The green Push to Google Sheets button. It opens the book in a pop-up, with its Download as Excel
    (`download` draws that button, True once clicked) and a Looks good! that books it without the file
    (`save` writes the books)."""
    with st.container(horizontal=True, key="push-row"):
        st.button("Push to Google Sheets", type="secondary" if done else "primary", disabled=bool(waiting) or not views,
                  icon=":material/upload:", key="push-sheets", on_click=peek, args=(True,))
    if ss.event.get("peek") and views:  # kept open across reruns until closed, so its Excel click is seen
        book(views, download, save)


def peek(on: bool) -> None:
    ss.event = {**ss.event, "peek": on}  # per event, so the next one starts closed


@st.dialog("Here's what goes in your sheet", width="large", on_dismiss=lambda: peek(False))
def book(views: dict, download, save) -> None:
    with st.container(key="sheet-peek"):
        st.markdown("This is what would go in your club's sheet. Want a copy? Download the Excel.")
        with st.container(horizontal=True):
            ok = st.button("Looks good!", type="primary", icon=":material/check:", key="peek-ok")
            if download() or ok:
                peek(False)
                save()
        for tab, view in zip(st.tabs(list(views)), views.values(), strict=True):
            tab.html(grid(view))
