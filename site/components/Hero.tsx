"use client";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { CloseoutPreview } from "./CloseoutPreview";
import { Sparkle } from "./Sparkle";
import { APP_URL } from "./links";

type StickerProps = {
  src: string;
  alt: string;
  className: string;
  float?: number;
  delay?: number;
  tilt?: number;
};

// Each sticker bobs gently and pops on hover, like it's being peeled off the page.
function Sticker({ src, alt, className, float = 8, delay = 0, tilt = 6 }: StickerProps) {
  return (
    <motion.img
      src={src}
      alt={alt}
      draggable={false}
      className={`absolute select-none ${className}`}
      animate={{ y: [0, -float, 0] }}
      transition={{ duration: 4 + delay, repeat: Infinity, ease: "easeInOut", delay }}
      whileHover={{ scale: 1.12, rotate: tilt, transition: { type: "spring", stiffness: 300, damping: 12 } }}
    />
  );
}

export function Hero() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <section className="relative mx-auto grid max-w-6xl items-center gap-6 px-4 pb-16 pt-6 sm:px-6 md:grid-cols-[1.05fr_1fr] md:pt-12">
      <div className="relative z-10">
        <p className="font-round text-sm font-semibold uppercase tracking-[0.18em] text-forest">
          For club treasurers
        </p>
        <h1 className="mt-3 font-display text-5xl font-black leading-[1.05] text-ink sm:text-6xl lg:text-7xl">
          Every receipt,
          <br />
          accounted for.
        </h1>
        <p className="mt-5 max-w-md text-lg leading-relaxed text-ink-soft">
          Snap your event&apos;s receipts. Tallyable checks the math, shows who&apos;s owed, and builds the funder
          report. You approve every row.
        </p>
        <div className="mt-7 flex flex-wrap gap-3">
          <a href={APP_URL} className="btn btn-primary">
            Get Started <span className="arrow" aria-hidden>→</span>
          </a>
          <a href="#payoff" className="btn btn-ghost">See what you get</a>
        </div>
        <p className="mt-5 text-sm text-ink-soft">Works for any club · Your Google Sheet stays the record</p>
      </div>

      <div className="relative mx-auto aspect-[1/1] w-full max-w-[520px]">
        <Sparkle className="left-[8%] top-[14%]" delay={0} />
        <Sparkle className="right-[10%] top-[4%]" delay={0.8} size={18} />
        <Sparkle className="bottom-[16%] right-[4%]" delay={1.4} size={26} />
        <Sparkle className="bottom-[6%] left-[30%]" delay={0.4} size={16} />
        <Sticker src="/art/boba.png" alt="Boba sticker" className="left-[6%] top-[2%] w-[22%]" delay={0.3} tilt={-8} />
        <Sticker src="/art/pizza.png" alt="Pizza sticker" className="right-[6%] top-[0%] w-[28%]" delay={0.9} />
        <Sticker src="/art/mascot.png" alt="Tallyable's receipt mascot giving a thumbs up" className="left-[12%] top-[14%] w-[68%]" float={10} delay={0} tilt={-4} />
        <Sticker src="/art/coins-a.png" alt="" className="bottom-[2%] left-[2%] w-[20%]" delay={1.2} />
        <Sticker src="/art/coins-b.png" alt="" className="bottom-[6%] right-[22%] w-[15%]" delay={0.6} tilt={-10} />
        <motion.button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Tap the phone to peek inside the app"
          className="group absolute bottom-[14%] right-[0%] w-[30%] cursor-zoom-in"
          animate={{ y: [0, -7, 0] }}
          transition={{ duration: 4.6, repeat: Infinity, ease: "easeInOut" }}
          whileHover={{ scale: 1.12, rotate: 8 }}
        >
          <img src="/art/phone.png" alt="" draggable={false} className="w-full select-none" />
          <span className="absolute -left-6 -top-3 rotate-[-8deg] rounded-full bg-sun px-2.5 py-1 font-round text-xs font-semibold text-ink shadow transition group-hover:scale-110">
            Tap me!
          </span>
        </motion.button>
      </div>

      <AnimatePresence>
        {open && (
          <motion.div
            className="fixed inset-0 z-50 grid place-items-center bg-ink/50 p-4 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, transition: { duration: 0.22 } }}
            onClick={() => setOpen(false)}
            role="dialog"
            aria-modal="true"
            aria-label="Inside the app: the close out screen"
          >
            <motion.div
              initial={{ scale: 0.3, x: 200, y: 120, rotate: 10, opacity: 0 }}
              animate={{ scale: 1, x: 0, y: 0, rotate: 0, opacity: 1 }}
              exit={{ scale: 0.3, x: 200, y: 120, rotate: 10, opacity: 0, transition: { duration: 0.22 } }}
              transition={{ type: "spring", stiffness: 260, damping: 24 }}
              onClick={(e) => e.stopPropagation()}
              className="relative max-h-[90vh] w-full max-w-[400px] overflow-y-auto rounded-[2.5rem] border-[10px] border-forest bg-cream p-3 shadow-2xl"
            >
              <div className="mx-auto mb-3 h-1.5 w-20 rounded-full bg-forest/30" />
              <CloseoutPreview compact />
              <div className="mt-3 flex flex-col gap-2">
                <a href={APP_URL} className="btn btn-primary justify-center">
                  Try it on your event <span className="arrow" aria-hidden>→</span>
                </a>
                <button type="button" onClick={() => setOpen(false)} className="btn btn-ghost justify-center">
                  Close
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
