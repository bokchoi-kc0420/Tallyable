# Held-out receipts (FAKE)

12 receipts the extraction prompt has never been tuned on. All stores, payers and amounts are made up.

**Why it exists:** the prompt's category definitions were written after seeing misses on `fake_event/`, so that set now flatters the model. This one gives the honest accuracy number.

**Rule:** don't change the prompt because of a miss here. If you do, this set stops being held out and you need a third one.

- Score it: `python -m treasurer.score_all --set holdout` (prints an upper-bound estimate of $0.24 on Sonnet 5.5; the main set's 14 receipts actually cost $0.08). Results go to `output/score_<model>_holdout.json`.
- Regenerate: `python fake_event_holdout/generate_holdout.py`
- No planted errors: every receipt adds up, so any miss is the model's. One receipt (H09) has a handwritten tip and total.
- Labels were set on 2026-11-05 before any model run: Food = eaten, Drink = drunk (including ice for drinks), Other = not consumed. Borderline on purpose: ice cream cups, an empty water jug, coffee filters vs tea bags, edible glitter, reusable bottles, drink mix powder.
