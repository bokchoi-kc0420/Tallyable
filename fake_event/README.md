# Fake event: Fall Mentor Mixer (FAKE)

All data here is made up: the stores, the "Member A to D" payers, and every amount. Regenerate everything with `python generate_fake_event.py` (needs Pillow).

## Files
- `answer_key.csv`: one row per visible line item. `tax`, `tip`, `total` are receipt-level and repeat on each line of a receipt. `total` is what the receipt **prints**.
- `receipts/R01.jpg` to `R15.jpg`: 14 images. R14 has no image on purpose.
- `expected_summary.json`: what a correct review should post per receipt, plus event totals (expenses $571.75, income $740.00, margin 22.74%).

## Planted errors (6)
| Receipt | Error | What the tool should do |
| --- | --- | --- |
| R06 | Handwritten total is $115.26, but items + tax + tip = $110.26 | Math flag, off by $5.00 |
| R12 | A fold hides one line; visible items + tax do not reach the printed $22.43 | Math flag |
| R07 | No payer | Missing payer flag |
| R11 | Same receipt as R03, re-photographed, different payer | Duplicate flag (same place, date, total) |
| R14 | Cash purchase with no photo | Missing receipt note |
| R09 | Bluetooth speaker returned | List it, exclude $39.99 + $3.30 tax from totals |

Assumed tax rate for the fake data: 8.25% on taxable items.
