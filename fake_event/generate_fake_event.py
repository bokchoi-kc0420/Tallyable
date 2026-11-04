"""Generate the fake test event: answer key CSV, receipt images, expected summary.

One data structure (RECEIPTS) drives every output, so the CSV and the images
can never disagree. All names, stores, and amounts are made up.

Run:  python generate_fake_event.py
Needs: Pillow
"""
from __future__ import annotations

import csv
import json
import random
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).parent
IMG_DIR = OUT / "receipts"
TAX_RATE = Decimal("0.0825")  # assumed local sales tax for fake data
CENT = Decimal("0.01")

EVENT = {
    "event_id": "EVT-FAKE-01",
    "name": "Fall Mentor Mixer (FAKE)",
    "date": "2026-11-14",
    "quarter": "Fall 2026",
    "attendees": 45,
    "income": {"Zelle": "264.00", "Venmo": "180.00", "Cash": "96.00", "National KSEA funding": "200.00"},
}

PAYERS = ["Member A", "Member B", "Member C", "Member D"]


def D(x: str) -> Decimal:
    return Decimal(x)


def money(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


# Each item: (category, item, unit, price, taxable, returned)
# Receipt fields: printed_total overrides the computed total when a planted error needs it.
RECEIPTS = [
    dict(id="R01", place="Bulk Warehouse", date="2026-11-12", payer="Member A", tip="0", items=[
        ("Drink", "Water 24pk", 2, "4.99", False, False),
        ("Other", "Paper plates", 1, "12.99", True, False),
        ("Other", "Napkins", 1, "6.49", True, False)]),
    dict(id="R02", place="Chicken Shack", date="2026-11-13", payer="Member B", tip="0", items=[
        ("Food", "Tenders tray (40)", 1, "74.50", True, False),
        ("Drink", "Lemonade gallon", 2, "6.25", True, False)]),
    dict(id="R03", place="Pizza Corner", date="2026-11-14", payer="Member C", tip="12.00", items=[
        ("Food", "Large cheese pizza", 3, "15.99", True, False),
        ("Food", "Large pepperoni pizza", 2, "17.49", True, False)]),
    dict(id="R04", place="Dollar Spot", date="2026-11-12", payer="Member A", tip="0", items=[
        ("Other", "Plastic cups (50)", 2, "1.25", True, False),
        ("Other", "Plastic forks", 1, "1.25", True, False),
        ("Other", "Table cover", 2, "1.25", True, False)]),
    dict(id="R05", place="Davis Mart", date="2026-11-13", payer="Member D", tip="0", items=[
        ("Food", "Chips variety pack", 2, "8.99", False, False),
        ("Drink", "Soda 12pk", 3, "6.99", True, False),
        ("Food", "Cookies", 1, "4.49", False, False)]),
    # PLANTED: handwritten total is $5.00 too high (true total 110.26)
    dict(id="R06", place="Seoul Kitchen", date="2026-11-14", payer="Member B", tip="15.00",
         printed_total="115.26", handwritten=True, planted="math_total_mismatch", items=[
        ("Food", "Kimbap platter", 2, "28.00", True, False),
        ("Food", "Tteokbokki tray", 1, "32.00", True, False)]),
    # PLANTED: no payer tagged
    dict(id="R07", place="Bulk Warehouse", date="2026-11-13", payer="", tip="0", planted="missing_payer", items=[
        ("Food", "Fruit tray", 1, "24.99", False, False),
        ("Drink", "Juice boxes (40)", 1, "13.99", False, False)]),
    dict(id="R08", place="Party Supply Co", date="2026-11-11", payer="Member C", tip="0", items=[
        ("Other", "Balloons", 2, "5.99", True, False),
        ("Other", "Name tags", 1, "4.50", True, False),
        ("Other", "Tape", 1, "3.29", True, False)]),
    # PLANTED: speaker was returned; list it, exclude its cost (and its tax)
    dict(id="R09", place="Home Goods Plus", date="2026-11-11", payer="Member D", tip="0", planted="returned_item", items=[
        ("Other", "Extension cord", 1, "14.99", True, False),
        ("Other", "Bluetooth speaker", 1, "39.99", True, True),
        ("Other", "Trash bags", 1, "9.49", True, False)]),
    dict(id="R10", place="Chicken Shack", date="2026-11-14", payer="Member A", tip="0", items=[
        ("Food", "Sauce cups (20)", 1, "8.00", True, False),
        ("Drink", "Sweet tea gallon", 1, "6.25", True, False)]),
    # PLANTED: same receipt as R03, re-photographed and submitted by another member
    dict(id="R11", duplicate_of="R03", payer="Member D", planted="duplicate"),
    # PLANTED: one line hidden by a fold; visible items do not add up to the printed total
    dict(id="R12", place="Davis Mart", date="2026-11-14", payer="Member B", tip="0", planted="math_hidden_item",
         hidden=[("Drink", "Sparkling water", 1, "5.99", True, False)], items=[
        ("Drink", "Ice bag", 3, "2.99", False, False),
        ("Food", "Rice cakes", 2, "3.49", False, False)]),
    dict(id="R13", place="Pizza Corner", date="2026-11-14", payer="Member C", tip="4.00", items=[
        ("Food", "Garlic knots", 2, "6.99", True, False),
        ("Drink", "2L soda", 3, "3.49", True, False)]),
    # PLANTED: cash purchase typed in by hand, no photo
    dict(id="R14", place="Gas & Go", date="2026-11-14", payer="Member A", tip="0", no_image=True,
         planted="missing_receipt", items=[
        ("Drink", "Ice bags", 2, "3.50", False, False)]),
    dict(id="R15", place="Print Shop", date="2026-11-10", payer="Member D", tip="0", items=[
        ("Other", "Flyers (50)", 1, "18.75", True, False)]),
]


def compute(r: dict) -> dict:
    """Subtotal, tax, true total over ALL lines (including hidden ones)."""
    lines = r["items"] + r.get("hidden", [])
    subtotal = sum(D(p) * u for _, _, u, p, _, _ in lines)
    taxable = sum(D(p) * u for _, _, u, p, t, _ in lines if t)
    tax = money(taxable * TAX_RATE)
    tip = D(r["tip"])
    true_total = money(subtotal + tax + tip)
    printed_total = D(r["printed_total"]) if "printed_total" in r else true_total
    return dict(subtotal=money(subtotal), tax=tax, tip=tip, true_total=true_total, printed_total=printed_total)


def resolve(r: dict) -> dict:
    if "duplicate_of" in r:
        src = next(x for x in RECEIPTS if x["id"] == r["duplicate_of"])
        merged = {**src, **{k: v for k, v in r.items() if k != "duplicate_of"}}
        merged["duplicate_of"] = r["duplicate_of"]
        merged.pop("planted", None)
        merged["planted"] = r["planted"]
        return merged
    return r


# ---------- images ----------
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
HAND = "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf"


def draw_receipt(r: dict, c: dict, seed: int) -> Image.Image:
    rng = random.Random(seed)
    f = ImageFont.truetype(MONO, 22)
    fb = ImageFont.truetype(MONO_B, 28)
    fh = ImageFont.truetype(HAND, 34)
    W, lh = 560, 32
    lines: list[tuple[str, str]] = []  # (kind, text)
    lines += [("title", r["place"].upper()), ("c", "123 Fake St, Davis CA"), ("c", f"Date: {r['date']}"), ("rule", "")]
    for cat, item, unit, price, taxable, returned in r["items"]:
        amt = money(D(price) * unit)
        left = f"{unit} x {item}"[:26]
        lines.append(("row", f"{left:<27}{amt:>9}"))
        if unit > 1:
            lines.append(("sub", f"   @ {price} ea"))
    for h in r.get("hidden", []):
        lines.append(("hidden", f"{h[2]} x {h[1]:<23}{money(D(h[3]) * h[2]):>9}"))
    lines += [("rule", ""), ("row", f"{'SUBTOTAL':<27}{c['subtotal']:>9}"), ("row", f"{'TAX':<27}{c['tax']:>9}")]
    if r.get("handwritten"):
        lines += [("row", f"{'TIP':<27}{'______':>9}"), ("row", f"{'TOTAL':<27}{'______':>9}")]
    else:
        if c["tip"] > 0:
            lines.append(("row", f"{'TIP':<27}{c['tip']:>9}"))
        lines.append(("total", f"{'TOTAL':<22}{c['printed_total']:>9}"))
    lines += [("rule", ""), ("c", "THANK YOU"), ("c", "SAMPLE RECEIPT - TEST DATA")]

    H = 60 + lh * len(lines) + 40
    img = Image.new("RGB", (W, H), (250, 248, 240))
    d = ImageDraw.Draw(img)
    y = 40
    hidden_box = None
    for kind, text in lines:
        if kind == "title":
            d.text((W // 2, y), text, font=fb, fill=(20, 20, 20), anchor="mt")
        elif kind == "c":
            d.text((W // 2, y), text, font=f, fill=(40, 40, 40), anchor="mt")
        elif kind == "rule":
            d.text((24, y), "-" * 38, font=f, fill=(60, 60, 60))
        elif kind == "total":
            d.text((24, y), text, font=fb, fill=(10, 10, 10))
        elif kind == "hidden":
            d.text((24, y), text, font=f, fill=(30, 30, 30))
            hidden_box = (0, y - 6, W, y + lh - 2)
        else:
            d.text((24, y), text, font=f, fill=(30, 30, 30))
        if r.get("handwritten") and text.startswith("TIP"):
            d.text((W - 150, y - 8), f"{c['tip']}", font=fh, fill=(20, 40, 140))
        if r.get("handwritten") and text.startswith("TOTAL"):
            d.text((W - 150, y - 8), f"{c['printed_total']}", font=fh, fill=(20, 40, 140))
        y += lh
    if hidden_box:  # a fold: dark crease that blocks the line
        d.rectangle(hidden_box, fill=(120, 118, 110))
    # light noise so it looks less like a screenshot
    px = img.load()
    for _ in range(W * H // 40):
        x, yy = rng.randrange(W), rng.randrange(H)
        v = rng.randint(200, 245)
        px[x, yy] = (v, v, v - 8)
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    angle = rng.uniform(-2.5, 2.5)
    bg = Image.new("RGB", (W + 160, H + 160), (90, 85, 80))  # "table" behind the paper
    bg.paste(img, (80, 80))
    return bg.rotate(angle, expand=False, fillcolor=(90, 85, 80))


def main() -> None:
    IMG_DIR.mkdir(exist_ok=True)
    rows, summary_receipts = [], []
    for n, raw in enumerate(RECEIPTS):
        r = resolve(raw)
        c = compute(r)
        image = "" if r.get("no_image") else f"receipts/{r['id']}.jpg"
        if image:
            seed = n * 7 + (3 if r.get("duplicate_of") else 0)
            im = draw_receipt(r, c, seed)
            if r.get("duplicate_of"):  # re-photographed: different angle and lighting
                im = im.rotate(4, fillcolor=(90, 85, 80)).point(lambda v: min(255, int(v * 0.93)))
            im.save(OUT / image, quality=88)
        for cat, item, unit, price, taxable, returned in r["items"]:
            rows.append(dict(
                receipt_id=r["id"], image_file=image, place=r["place"], date=r["date"], payer=r["payer"],
                category=cat, item=item, unit=unit, price=price,
                tax=c["tax"], tip=c["tip"], total=c["printed_total"],
                returned="TRUE" if returned else "FALSE",
                planted_error=r.get("planted", ""),
                duplicate_of=r.get("duplicate_of", ""),
            ))
        # what a correct review should post for this receipt
        if r.get("duplicate_of"):
            posted = Decimal("0")
        else:
            posted = c["true_total"]
            for _, _, unit, price, taxable, returned in r["items"]:
                if returned:
                    amt = D(price) * unit
                    posted -= money(amt + (amt * TAX_RATE if taxable else 0))
        summary_receipts.append(dict(receipt_id=r["id"], printed_total=str(c["printed_total"]),
                                     true_total=str(c["true_total"]), expected_posted=str(money(posted)),
                                     planted_error=r.get("planted", "")))

    with open(OUT / "answer_key.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    total_exp = sum(D(x["expected_posted"]) for x in summary_receipts)
    total_inc = sum(D(v) for v in EVENT["income"].values())
    summary = dict(event=EVENT, receipts=summary_receipts,
                   expected_total_expenses=str(money(total_exp)),
                   expected_total_income=str(money(total_inc)),
                   expected_net=str(money(total_inc - total_exp)),
                   expected_margin_pct=str(money((total_inc - total_exp) / total_inc * 100)))
    (OUT / "expected_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"{len(rows)} line items, {len(RECEIPTS)} receipts, expenses {summary['expected_total_expenses']}, "
          f"income {summary['expected_total_income']}, margin {summary['expected_margin_pct']}%")


if __name__ == "__main__":
    main()
