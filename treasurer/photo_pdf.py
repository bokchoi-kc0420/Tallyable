"""Every receipt photo in one PDF, one labeled page each: to attach to a funder request
or flip through while checking prices against the Expense Report.

A photo can't go inside a Google Sheet cell without being uploaded somewhere public, and
the bot account Tallyable uses has no Drive storage of its own, so the photos travel as a
file instead. A receipt typed in by hand, or uploaded as a PDF, gets a page that says so.
"""
from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

from .models import Receipt

PAGE = (1275, 1650)  # US letter at 150 dpi
MARGIN, HEAD = 75, 150


def _label(r: Receipt, paid: str) -> list[str]:
    who = r.payer or "no payer"
    return [f"{r.receipt_id}  ·  {r.place}  ·  {r.date.strftime('%m/%d/%Y')}",
            f"Total ${r.posted_amount:,.2f}  ·  paid by {who}" + (f"  ·  paid back: {paid}" if paid else "")]


def receipts_pdf(receipts: list[Receipt], images: dict[str, tuple[bytes, str]],
                 paid_back: dict[str, str] | None = None) -> bytes:
    """`images` is receipt id -> (bytes, media type), as the app keeps them.
    `paid_back` is receipt id -> "Yes" / "Not yet" / ..., from the Receipts tab."""
    big, small = ImageFont.load_default(size=40), ImageFont.load_default(size=30)
    pages = []
    for r in sorted(receipts, key=lambda r: (r.date, r.receipt_id)):
        page = Image.new("RGB", PAGE, "white")
        draw = ImageDraw.Draw(page)
        first, second = _label(r, (paid_back or {}).get(r.receipt_id, ""))
        draw.text((MARGIN, 45), first, fill="#222A35", font=big)
        draw.text((MARGIN, 98), second, fill="#6B7280", font=small)
        draw.line((MARGIN, HEAD - 10, PAGE[0] - MARGIN, HEAD - 10), fill="#B7B7B7", width=2)
        data, media = images.get(r.receipt_id, (None, ""))
        if data and media.startswith("image/"):
            photo = Image.open(io.BytesIO(data)).convert("RGB")
            box = (PAGE[0] - 2 * MARGIN, PAGE[1] - HEAD - MARGIN)
            scale = min(box[0] / photo.width, box[1] / photo.height)  # small photos grow to fill the page
            photo = photo.resize((int(photo.width * scale), int(photo.height * scale)))
            page.paste(photo, ((PAGE[0] - photo.width) // 2, HEAD + 10))
        else:
            note = "Typed in by hand: no photo." if not data else "Uploaded as a PDF: see the original file."
            draw.text((MARGIN, HEAD + 40), note, fill="#C62828", font=small)
        pages.append(page)
    out = io.BytesIO()
    if pages:
        pages[0].save(out, "PDF", save_all=True, append_images=pages[1:], resolution=150)
    return out.getvalue()
