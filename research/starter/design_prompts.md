# Design prompts

Paste-ready prompts for FigJam AI, Claude, or any design tool. All of them use fake data only.

## 1. FigJam: event close-out flow

> Draw a left-to-right flow for a student club treasurer closing out one event. Lanes: Payer, Treasurer, Tool (code), Tool (AI), Funder.
> Steps: Payer uploads a receipt photo and tags their name. AI transcribes it (store, date, items, tax, tip, printed total) and never fixes math. Code runs checks: math, missing payer, duplicate, missing photo, unusual tax, returned item, funder rules. Treasurer reviews each receipt card and approves it, or overrides with a written note. Approved receipts post to the tidy tab. The expense report, balance sheet, and ledger render from the tidy tab. The "Who's owed" list goes to the treasurer, who pays people back and marks them reimbursed. The expenditure report goes to the funder, with its due date shown.
> Mark the one rule that matters: nothing reaches the ledger with an open blocking flag.

## 2. Review screen (Streamlit or Figma)

> Design a desktop and phone review screen for one event: "Fall Mentor Mixer (FAKE), Nov 14, 45 attendees".
> Top bar: 3 counts, "12 ready / 3 need you / $571.75 to post", and an "Owed to members" chip.
> Main area: one card per receipt, sorted so blocked cards come first. Each card has the receipt photo on the left (tap to zoom) and the fields on the right (store, date, payer dropdown, line items as an editable table, tax, tip, printed total, computed total).
> Flags appear as a row of badges. Each badge has an icon, a word ("Blocks", "Check", "Info"), and one sentence, e.g. "Items + tax + tip = $110.26, receipt says $115.26 (off by $5.00)". Never use color alone.
> One primary button per card: "Approve receipt". It's disabled while a blocking flag is open. "Override with note" is a secondary link that opens a required text field.
> Keyboard: Tab moves through fields, Enter approves, and focus jumps to the next card that needs attention.
> Accessibility: 16px base text, 4.5:1 contrast, every input labelled, works at 360px wide.

## 3. "Who's owed" panel

> A small panel listing each payer, with amount fronted, amount reimbursed, and amount still owed, biggest first. Receipts with no payer show as "(no payer)" in a warning style with a "Fix" link. A "Mark paid" button records the date and amount. Fake names are Member A to D.

## 4. Funder report export

> A one-page expenditure report for "UC Davis Club Finance Council (CFC)". Header: event, date, attendees, amount requested, the club's share (must be 10% or more), and "Report due Dec 5, 2026". Table: receipt ID, store, date, category, amount, and a receipt-attached check mark. Callouts: food total vs. cap ($12 x 45 = $540), plus sections for event photos and an impact statement, which the treasurer fills in. Export to PDF and to a Sheets tab.

## 5. Claude prompt: write the README pitch (for later)

> Here's my project's README and the results table from running one fake event. Write a 120-word "Why this exists" section for recruiters. Lead with the measured result (time to close, dollars posted vs. truth, flags caught). Explain the "AI reads, code checks, a human signs" design in one sentence, citing that vision models silently repair totals. No hype words.
