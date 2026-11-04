# Tallyable

A tool that turns club receipt photos into reviewed expense rows, flags errors with plain-code rules, and posts approved totals to Google Sheets. Portfolio project. **All data in this repo is fake.**

## Status
Week 1 of 4 done, plus a working review app on a stand-in AI. The Claude API call (week 2) and the Google Sheets push (week 4) are the two pieces left to swap in.

![Review screen](docs/review_screen.png)

## Run the app
```bash
streamlit run app.py
```
Click "Use the fake event's 14 receipts instead", tag payers, Draft rows, then Review.

## Run the tests
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest
```

## Layout
| Path | What |
| --- | --- |
| `treasurer/models.py` | `Receipt` with many `LineItem`s. Money is `Decimal`. |
| `treasurer/checks.py` | Six rule checks: math, missing payer, duplicate, missing receipt, unusual tax, returned item |
| `treasurer/loader.py` | Loads the fake answer key into models |
| `treasurer/extract.py` | `Extractor` interface; `StubExtractor` replays the key with 4 realistic misreads |
| `treasurer/score.py` | Field-level accuracy of drafts against the answer key |
| `treasurer/post.py` | Long-format transaction rows, event totals, idempotent local CSV sink |
| `app.py` | Streamlit: Upload, Review, Summary |
| `fake_event/` | 15 fake receipts, answer key, 6 planted errors (see its README) |
| `tests/` | pytest suite graded against the answer key |

## Rules
| Flag | Rule | Blocks approval |
| --- | --- | --- |
| `math_error` | items + tax + tip differs from the printed total by more than $0.01 | Yes |
| `missing_payer` | no payer | Yes |
| `possible_duplicate` | same image bytes, or same place, date and total in one event | Yes |
| `missing_receipt` | no photo | No |
| `unusual_tax` | tax over 12% of subtotal | No |
| `returned_item` | listed, cost and its tax share excluded from totals | No |

A blocking flag can be overridden only with a written note.

## Week 1 results
- All 6 planted errors caught, 0 false flags on the 9 clean receipts.
- A simulated correct review posts $571.75, matching the expected total.
