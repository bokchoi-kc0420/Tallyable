"use client";
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";

const QA = [
  {
    q: "Does the AI change my books?",
    a: "No. It only reads receipts and drafts rows. You approve every row before anything reaches your sheet, and plain code (not AI) checks the math, missing payers, duplicates and missing receipts.",
  },
  {
    q: "My school isn't UC Davis. Does it still work?",
    a: "Yes. Funder rules are optional, so pick No funder and you still get who's owed, the ledger and the balance sheet. You can name your own income sources too, like dues, ticket sales or a sponsor.",
  },
  {
    q: "Where does my data live?",
    a: "In your own Google Sheet, which stays the record. No Sheet? Download the whole book as one Excel file instead.",
  },
  {
    q: "What happens when I hand off to the next treasurer?",
    a: "Every event is kept and can be reopened. Give them the Sheet or the Excel book and they see every receipt, payback and report from your term.",
  },
  {
    q: "What does it cost?",
    a: "The app is free and open source. Reading receipts with AI runs on your own API key, at under a cent per receipt in our tests. There's also a free mode where you type rows in yourself.",
  },
];

export function Faq() {
  const [open, setOpen] = useState<number | null>(0);
  return (
    <div className="divide-y-2 divide-line rounded-3xl border-2 border-forest bg-paper">
      {QA.map((item, i) => {
        const isOpen = open === i;
        return (
          <div key={item.q}>
            <button
              type="button"
              aria-expanded={isOpen}
              onClick={() => setOpen(isOpen ? null : i)}
              className="group flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition-colors hover:bg-sun-soft/60 sm:px-6"
            >
              <span className="font-round text-lg font-semibold">{item.q}</span>
              <motion.span
                animate={{ rotate: isOpen ? 45 : 0 }}
                className="grid size-8 shrink-0 place-items-center rounded-full border-2 border-forest text-xl leading-none text-forest transition group-hover:bg-forest group-hover:text-white"
                aria-hidden
              >
                +
              </motion.span>
            </button>
            <AnimatePresence initial={false}>
              {isOpen && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden"
                >
                  <p className="px-5 pb-5 leading-relaxed text-ink-soft sm:px-6">{item.a}</p>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}
