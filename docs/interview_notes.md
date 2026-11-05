# Interview notes: talking about Tallyable

Fill in the blanks after your first measured run. Say it in your own words. These are prompts, not a script.

## 30-second version
"I'm the treasurer of a student club. After every event, I had to turn a pile of receipt photos into an expense report, a balance sheet, and a ledger, then work out who was owed money and whether we met the funder's rules. I built Tallyable to do that close-out. AI reads the receipts, plain code checks the math, and I approve every row before anything reaches the books. On a test event with 6 planted errors, it caught all 6. Close-out went from ___ minutes by hand to ___ minutes."

## The story (situation, task, action, result)
- **Situation:** Receipts arrive as group-chat photos. The books live in Google Sheets. Errors are easy to make: totals that don't add up, missing tip lines, duplicates, untagged payers. The funder (UC Davis CFC) caps food at $12 per person and wants a report within 21 days.
- **Task:** Make close-out faster without making the books less trustworthy.
- **Action:**
  - Built a fake event with an answer key before writing any AI code, so every claim is measurable.
  - Kept the AI to one job, reading receipts. Everything else is deterministic code.
  - Required a human approval for every row, with a written note to override a blocking flag.
- **Result:** 99.5% field accuracy on Sonnet 5.5 (one miss, a category call) at about $0.08 per event. Held-out set: ___%. 6 of 6 planted errors caught, 0 false flags. ___ minutes vs ___ by hand.

## Decisions you can defend
| Decision | Why | What you gave up |
| --- | --- | --- |
| AI reads, code checks | Flags must be exact and explainable to a funder | Can't catch "weird but valid" spending |
| Prompt says "transcribe, never reconcile" | Models quietly fix totals to make them add up, which hides real errors | Drafts have more visible mismatches to review |
| Human approves every row | It's money, and people are accountable | Slower than full automation |
| `Decimal`, not float | Floats drift by fractions of a cent | Slightly more verbose code |
| Sheets as the system of record | The club already uses it, so adoption costs nothing | Weaker than a real database |
| Tidy tabs plus rebuilt views | Keeps the familiar layout and keeps data analyzable | Views can't be hand-edited |
| Stub extractor plus answer key | Build and test with no API cost; score any model the same way | Up-front work making fake receipts |
| Mid-tier model by default, $1 budget stop | Cost matters for a club; measure before paying for the top model | Maybe a few points of accuracy |
| Funder rules as data (`RulePack`) | A new funder means new numbers, not new code | Odd rules still need code |

## Questions you'll likely get
- **"Where did the AI get it wrong?"** Only on category, 2 of 32 lines, like "Sauce cups": food or tableware? Category is a judgment, not something printed on the receipt. So I tightened the definition and started scoring the food-vs-other split separately, because that's the part funder rules use. I wrote general definitions instead of naming those two items, which would just teach the model the test. The rerun fixed one; "Sauce cups" still came back as tableware. I stopped tuning there, because the definitions were written after seeing the misses, and more tuning would just teach the model the test. Instead I built a second set of 12 receipts with new stores and borderline items, labeled them before any run, and froze the prompt. On that set it scored ___%.
- **"How do you know the AI is right?"** Every receipt is scored field by field against an answer key. Lines are matched by name, so one invented line doesn't count the whole receipt as wrong. In real use, nothing posts without a person approving it.
- **"What happens when it's wrong?"** The math check catches misread numbers that break the total. A misread name or category is caught in review. Edits are counted, so you can see where the model struggles.
- **"Why not just use OCR?"** Receipts are messy: handwriting, Korean item names, folded paper. A vision model handles those. Structured output keeps the result in a fixed shape.
- **"What would you do next?"** Interview 5 treasurers about what slows them down, then decide between multi-event history and supporting more funders.
- **"What was hard?"** Example: the returned-item rule. A return also removes its share of the tax, and the balance-sheet lines still have to add up exactly.
- **"What did you learn?"** Measure before you optimize. Building the answer key first made every later choice, including which model to use, a data question.

## Numbers to have ready
- Field accuracy: 99.5% on Sonnet 5.5 (every field 100% except category, 96.9%; first run was 99.0%). Held-out set: ___. Haiku 5.5: ___
- Cost per event: $0.079 for 14 receipts, 33 seconds
- Minutes by hand: ___. Minutes in the tool: ___
- Edits per receipt: ___
- Tests: 100, 93% coverage, running on every push in GitHub Actions
