"""Events drawn as tickets. Each event gets a color, picked automatically so two events in a
row never match (changeable in Edit event). Past events show as torn-off stubs: date plus a
short name, all the same size, so the row reads like a ticket collection."""
from __future__ import annotations

import html
import re
from datetime import date

# name -> (color, text color). Light colors get dark text so they stay readable.
PALETTE = {"Forest": ("#1C5C36", "#FFFFFF"), "Teal": ("#1F7A73", "#FFFFFF"), "Navy": ("#2F4B7C", "#FFFFFF"),
           "Plum": ("#6B4E8A", "#FFFFFF"), "Berry": ("#B0413E", "#FFFFFF"), "Terracotta": ("#C8673C", "#FFFFFF"),
           "Sunflower": ("#F2B632", "#1F2A22"), "Sage": ("#8FB38A", "#1F2A22")}
NAMES = list(PALETTE)


def next_color(last: str | None) -> str:
    """The color after the last event's, so neighbors never match."""
    return NAMES[(NAMES.index(last) + 1) % len(NAMES)] if last in PALETTE else NAMES[0]


def short_name(name: str) -> str:
    """What fits on a stub: no "(FAKE)"-style notes, no leading season, whole words up to 16 letters."""
    words = re.sub(r"\(.*?\)", "", name).split()
    if len(words) > 2 and words[0].lower() in ("fall", "winter", "spring", "summer"):
        words = words[1:]
    out = words[:1]
    for w in words[1:]:
        if len(" ".join([*out, w])) > 16:
            break
        out.append(w)
    return " ".join(out) or name


def _vars(color: str | None) -> str:
    bg, fg = PALETTE.get(color or "", PALETTE["Forest"])
    return f"--tly-c: {bg}; --tly-ct: {fg};"


def ticket(d: date, name: str, receipts: int, color: str | None = None) -> str:
    """An event as a ticket: a date stub in the event's color, then the name and receipt count."""
    return (f'<div class="tly-event" style="{_vars(color)}"><div class="stub"><span>{d.strftime("%b").upper()}</span>'
            f'<b>{d.day}</b><span>{d.year}</span></div><div class="info"><b>{html.escape(name)}</b>'
            f'<small>{receipts} receipt{"s" if receipts != 1 else ""}</small></div></div>')


def stub(d: date, name: str, color: str | None = None) -> str:
    """A past event as its torn-off stub. Hover shows the full name."""
    return (f'<div class="tly-stub" style="{_vars(color)}" title="{html.escape(name)} · {d:%b %d, %Y}">'
            f'<span>{d.strftime("%b").upper()}</span><b>{d.day:02d}</b><i>{html.escape(short_name(name))}</i></div>')
