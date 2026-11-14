"""Events drawn as tickets. Each event gets a color, picked automatically so two events in a
row never match (changeable in Edit event). An event still open is a whole ticket; a finished
one is its torn-off stub: date plus a short name, all the same size, so finished events read
like a ticket collection."""
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
    """A finished event as its torn-off stub. Hover shows the full name."""
    return (f'<div class="tly-stub" style="{_vars(color)}" title="{html.escape(name)} · {d:%b %d, %Y}">'
            f'<span>{d.strftime("%b").upper()}</span><b>{d.day:02d}</b><i>{html.escape(short_name(name))}</i></div>')


RIP_START, RIP_LEN = 380, 450  # ms: when the tear starts, and how long it takes to run down the perforation
# Puts the ticket (264 x 76, so its middle is 132, 38) on the Past events row it is torn into, centers it (--cx, --cy),
# and aims the stub's flight at that row's icon (--fx, --fy, in the centered ticket's own pixels: it is drawn at
# twice its size there). Reduced motion: no rip at all.
RIP_JS = """(() => {
  const src = document.querySelector('.tly-rip:not(.go)');
  const row = document.querySelector('[data-testid="stSidebar"] [data-testid="stExpander"] summary');  // its header, open or not
  if (!src || !row || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const r = row.getBoundingClientRect(), x = r.left + 16, y = r.top + r.height / 2 - 38, rip = src.cloneNode(true);
  const fx = (r.left + 24 - innerWidth / 2) / 2 + 70, fy = (r.top + r.height / 2 - innerHeight / 2) / 2 - 33;
  const cx = innerWidth / 2 - x - 132, cy = innerHeight / 2 - y - 38;
  rip.style.cssText += `--x:${x}px;--y:${y}px;--cx:${cx}px;--cy:${cy}px;--fx:${fx}px;--fy:${fy}px`;
  rip.classList.add('go'); document.body.append(rip); setTimeout(() => rip.remove(), 2400);
})()"""


def rip(d: date, name: str, receipts: int, color: str | None = None) -> str:
    """The Finish event moment (finish.css): the ticket comes to the middle of a blurred page, its stub is torn
    off from the top down and flies into Past events, and the rest drops away. The stub is cut into 19 thin
    bands; each one swings away only once the tear has passed it, so the part not torn yet stays on the ticket."""
    face = f'<div class="stub"><span>{d.strftime("%b").upper()}</span><b>{d.day}</b><span>{d.year}</span></div>'
    passed = [RIP_START + RIP_LEN * (y / 76) ** (2 / 3) for y in range(0, 76, 4)]  # slow at first, then it zips
    end = RIP_START + RIP_LEN
    bands = "".join(f'<div class="band" style="--i:{i};--s:{74 - i * 4};--d:{t:.0f}ms;--t:{end - t:.0f}ms">{face}</div>'
                    for i, t in enumerate(passed))
    bits = "".join(f'<i style="--y:{y}px;--bx:{x}px;--by:{f}px;--d:{passed[y // 4]:.0f}ms"></i>'
                   for y, x, f in [(8, 9, -14), (28, -7, 16), (44, 11, 12), (60, -6, 18)])  # paper bits off the tear
    return (f'<div class="tly-rip" aria-hidden="true" style="{_vars(color)}"><div class="blur"></div><div class="tk">'
            f'<div class="shade"><div class="body"><b>{html.escape(name)}</b>'
            f'<small>{receipts} receipt{"s" if receipts != 1 else ""}</small></div></div>'
            f'<div class="shade"><div class="stubw">{bands}</div></div>{bits}</div></div><script>{RIP_JS}</script>')
