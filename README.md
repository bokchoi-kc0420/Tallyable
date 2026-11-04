# Tallyable

A tool that turns club receipt photos into reviewed expense rows, flags errors with plain-code rules, and posts approved totals to Google Sheets. Portfolio project. **All data in this repo is fake.**

## Status
Week 1 of 4 done, plus a working review app. Week 2: the app reads receipts with Claude when an API key is set, and falls back to a stand-in AI when it is not. Push writes to Google Sheets when it is set up ([setup guide](docs/google_sheets_setup.md)), and to a local CSV when it is not.

![Review screen](docs/review_screen.png)

## Run the app
```bash
streamlit run app.py
```
Click "Use the fake event's 14 receipts instead", tag payers, Draft rows, then Review, Summary (push), and Close out (who's owed, funder flags, report download). Each push logs its time to `output/run_log.csv`.

## Use Claude to read receipts
1. Copy `.env.example` to `.env` and paste your key after `ANTHROPIC_API_KEY=`. Git ignores `.env`; never commit it or paste it anywhere.
2. Try one receipt: `python -m treasurer.try_one fake_event/receipts/R01.jpg`
3. Score all 14 photos against the answer key: `python -m treasurer.score_all` (add `--model claude-haiku-5-5` to compare a cheaper model). Results are saved in `output/`. It prints a cost estimate first and stops at `--budget` (default $1).

The default model is Claude Sonnet 5.5. Change it with `TALLYABLE_MODEL` in `.env`. A full run of 14 receipts is estimated at most about $0.01 on Haiku 5.5, $0.28 on Sonnet 5.5, and $0.56 on Opus 5.5.

Uploads can be JPG, PNG, WEBP, PDF or HEIC. HEIC needs `python -m pip install pillow-heif`. Rotated photos are turned upright, blurry ones get a warning, and any file that can't be read can be typed in by hand with the photo still attached.

Without a key, the app and tests use the stub. Tests never call the API.

## Put it online
See [docs/deploy_streamlit_cloud.md](docs/deploy_streamlit_cloud.md). Set `APP_PASSWORD` first; the app is gated when it is set.

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
| `treasurer/claude_extract.py` | `ClaudeExtractor`: one vision call per receipt, prompt says transcribe and never reconcile |
| `treasurer/reader.py` | Picks Claude if `ANTHROPIC_API_KEY` is in `.env`, else the stub |
| `treasurer/try_one.py`, `score_all.py` | Read one receipt; score all of them against the answer key |
| `treasurer/score.py` | Field-level accuracy of drafts against the answer key |
| `treasurer/post.py` | Long-format transaction rows, event totals, idempotent local CSV sink |
| `treasurer/closeout.py` | Funder rules (UC Davis CFC, ORG), who's owed, funder report CSV |
| `treasurer/runlog.py` | One row per push in `output/run_log.csv`: receipts, edits, overrides, minutes |
| `treasurer/sheets.py` | Google Sheets sink: tidy Transactions and Events tabs, rebuilt Balance Sheet and Ledger views |
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
