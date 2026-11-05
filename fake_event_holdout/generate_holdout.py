"""Generate the held-out receipts: a second fake set the prompt was never tuned on.

The prompt's category definitions were written after seeing misses on fake_event/.
Scoring on that same set again would flatter it. These receipts use new stores and
new items, many of them deliberately borderline on category, so the score here is
the honest one. Do not edit the prompt to fix misses on this set: if you do, it
stops being held out, and you need a third set.

Labels follow how a treasurer would book the item for a funder's food rule, decided
before any model run (written 2026-11-05):
  Food = eaten, Drink = drunk (including ice for drinks), Other = not consumed.

Reuses the drawing code from fake_event/generate_fake_event.py.
Run:  python fake_event_holdout/generate_holdout.py
"""
from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

OUT = Path(__file__).parent
_spec = importlib.util.spec_from_file_location("gen", OUT.parent / "fake_event" / "generate_fake_event.py")
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)

# Each item: (category, item, unit, price, taxable, returned)
RECEIPTS = [
    dict(id="H01", place="Corner Grocer", date="2026-12-02", payer="Member A", tip="0", items=[
        ("Food", "Ice cream cups (24)", 1, "11.99", False, False),
        ("Other", "Paper bowls (40)", 1, "5.49", True, False),
        ("Food", "Ketchup packets (100)", 1, "3.99", False, False)]),
    dict(id="H02", place="Bean Street Cafe", date="2026-12-03", payer="Member B", tip="6.00", items=[
        ("Drink", "Coffee carafe", 2, "18.50", True, False),
        ("Food", "Muffin box (12)", 1, "21.00", True, False),
        ("Other", "Cup sleeves", 1, "2.00", True, False)]),
    dict(id="H03", place="Value Depot", date="2026-12-01", payer="Member C", tip="0", items=[
        ("Drink", "Tea bags (100)", 1, "6.79", False, False),
        ("Other", "Coffee filters", 1, "3.29", True, False),
        ("Other", "Water jug, empty 5gal", 1, "9.99", True, False),
        ("Food", "Sugar packets (200)", 1, "4.59", False, False)]),
    dict(id="H04", place="Noodle House", date="2026-12-04", payer="Member D", tip="9.50", items=[
        ("Food", "Japchae tray", 1, "45.00", True, False),
        ("Food", "Dumpling platter", 2, "26.00", True, False),
        ("Drink", "Barley tea pitcher", 2, "4.50", True, False)]),
    dict(id="H05", place="Party Planet", date="2026-11-30", payer="Member A", tip="0", items=[
        ("Other", "Birthday candles", 2, "2.49", True, False),
        ("Other", "Cake knife", 1, "4.99", True, False),
        ("Other", "Streamers", 3, "1.99", True, False)]),
    dict(id="H06", place="Sweet Oven Bakery", date="2026-12-04", payer="Member B", tip="0", items=[
        ("Food", "Sheet cake", 1, "38.00", False, False),
        ("Food", "Edible glitter", 1, "6.50", False, False)]),
    dict(id="H07", place="Value Depot", date="2026-12-03", payer="Member C", tip="0", items=[
        ("Drink", "Drink mix powder", 2, "4.99", False, False),
        ("Other", "Reusable bottles (6)", 1, "14.99", True, False),
        ("Drink", "Bagged ice 10lb", 2, "3.79", False, False)]),
    dict(id="H08", place="Campus Market", date="2026-12-04", payer="Member D", tip="0", items=[
        ("Food", "Cup noodles (12)", 1, "9.48", False, False),
        ("Food", "Popcorn kernels", 1, "4.29", False, False),
        ("Other", "Chopsticks (50)", 1, "3.99", True, False),
        ("Drink", "Oat milk", 2, "4.49", False, False)]),
    # Handwritten tip and total, like a sit-down restaurant slip
    dict(id="H09", place="Grill & Bowl", date="2026-12-04", payer="Member A", tip="14.00", handwritten=True, items=[
        ("Food", "Rice bowl", 6, "11.50", True, False),
        ("Drink", "Fountain drink", 6, "2.75", True, False)]),
    dict(id="H10", place="Home Goods Plus", date="2026-12-02", payer="Member B", tip="0", items=[
        ("Other", "Serving tongs", 2, "3.99", True, False),
        ("Other", "Aluminum trays (10)", 1, "8.99", True, False),
        ("Other", "Hand sanitizer", 1, "4.49", True, False)]),
    dict(id="H11", place="Corner Grocer", date="2026-12-04", payer="Member C", tip="0", items=[
        ("Food", "Hummus tub", 2, "4.99", False, False),
        ("Food", "Pita chips", 2, "3.79", False, False),
        ("Food", "Gummy candy bag", 1, "5.99", True, False),
        ("Drink", "Coconut water", 4, "2.29", False, False)]),
    dict(id="H12", place="Copy Hut", date="2026-11-28", payer="Member D", tip="0", items=[
        ("Other", "Poster print 24x36", 1, "22.00", True, False),
        ("Other", "Raffle tickets", 1, "7.50", True, False)]),
]


def main() -> None:
    (OUT / "receipts").mkdir(exist_ok=True)
    rows = []
    for n, r in enumerate(RECEIPTS):
        c = gen.compute(r)
        image = f"receipts/{r['id']}.jpg"
        gen.draw_receipt(r, c, seed=1000 + n * 11).save(OUT / image, quality=88)
        for cat, item, unit, price, _taxable, returned in r["items"]:
            rows.append(dict(
                receipt_id=r["id"], image_file=image, place=r["place"], date=r["date"], payer=r["payer"],
                category=cat, item=item, unit=unit, price=price,
                tax=c["tax"], tip=c["tip"], total=c["printed_total"],
                returned="TRUE" if returned else "FALSE", planted_error="", duplicate_of=""))
    with open(OUT / "answer_key.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(RECEIPTS)} receipts, {len(rows)} lines")


if __name__ == "__main__":
    main()
