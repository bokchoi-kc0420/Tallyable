# Research starter kit

This is the output of the market-fit research thread. It sits separate from the build in `treasurer/` so the two don't collide. All data is fake.

| File | What it is | Status |
| --- | --- | --- |
| `closeout.py` | **Your exercise.** Funder rules (UC Davis CFC, ORG) and a "who's owed" summary, as stubs | Stubs. The 10 tests fail until you write it. |
| `test_closeout.py` | Tests graded against the fake event | Run them from the repo root |
| `claude_extractor_draft.py` | A draft `ClaudeExtractor` for week 2, with a prompt that says to transcribe and never reconcile | Untested: no API key yet |
| `design_prompts.md` | FigJam, review-screen, owed-panel, and funder-report prompts | |
| `treasurer_interview_script.md` | 5 interviews, 20 minutes each, with a decision rule | Do this before week 2 |

```bash
pytest research/starter -q
```

The rules come from UC Davis CSI pages read on 2026-11-04. Re-check them before relying on them:
- CFC: up to $2,500, food $12 per person per day, club pays 10% or more, report due 21 days after the event with receipts, photos, and an impact statement.
- ORG: $250 a year, purchases within the 42 days before applying, no food, decorations, website subscriptions, or one-time marketing. The application window closes Nov 18, 2026.
