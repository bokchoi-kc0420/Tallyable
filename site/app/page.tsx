import { CloseoutPreview } from "@/components/CloseoutPreview";
import { Faq } from "@/components/Faq";
import { Hero } from "@/components/Hero";
import { APP_URL, REPO_URL } from "@/components/links";
import { Reveal } from "@/components/Reveal";
import { Sparkle } from "@/components/Sparkle";

const STEPS = [
  { img: "/art/snap.png", title: "Snap it", body: "Drop in receipt photos, order screenshots or PDFs. Tag who paid." },
  { img: "/art/check.png", title: "We check it", body: "AI drafts each line. Code checks the math and flags anything off. You approve." },
  { img: "/art/settle.png", title: "Settle up", body: "See who's owed, mark paybacks, and download the funder report." },
];

const FEATURES = [
  { img: "/art/owed.png", title: "Who's owed", body: "Everyone who fronted money, what they're owed, and a Mark paid button." },
  { img: "/art/report.png", title: "Funder report", body: "Checks your funder's rules, the most you can request, and when it's due." },
  { img: "/art/events.png", title: "Every event kept", body: "Past events stay saved. Reopen one anytime from the sidebar." },
  { img: "/art/proof.png", title: "Any proof works", body: "Paper receipts, food-court tickets, delivery screenshots, PDF invoices." },
  { img: "/art/rules.png", title: "Your club's rules", body: "Funder rules are optional. Name your own income sources." },
  { img: "/art/moneyin.png", title: "Money in too", body: "Log Venmo, Zelle, cash and grants so the balance sheet adds up." },
];

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="relative mx-auto w-fit px-8 text-center font-round text-4xl font-bold text-forest sm:text-5xl">
      <Sparkle className="-left-1 top-0" size={20} />
      {children}
      <Sparkle className="-right-1 bottom-0" size={20} delay={1} />
    </h2>
  );
}

export default function Home() {
  return (
    <main className="overflow-x-clip">
      <header className="sticky top-0 z-40 border-b border-line/70 bg-cream/85 backdrop-blur">
        <nav className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <a href="#top" className="shrink-0 transition hover:-rotate-2 hover:scale-105" aria-label="Tallyable home">
            <img src="/art/logo.png" alt="Tallyable" className="h-12 w-auto sm:h-16" />
          </a>
          <div className="hidden items-center gap-6 font-medium md:flex">
            {[["#how", "How it works"], ["#features", "Features"], ["#faq", "FAQ"]].map(([href, label]) => (
              <a key={href} href={href} className="relative after:absolute after:-bottom-1 after:left-0 after:h-0.5 after:w-0 after:bg-sun after:transition-all hover:text-forest hover:after:w-full">
                {label}
              </a>
            ))}
          </div>
          <a href={APP_URL} className="btn btn-primary !px-4 !py-2 text-sm">Open the app</a>
        </nav>
      </header>

      <div id="top" />
      <Hero />

      <section id="payoff" className="scroll-mt-20 bg-paper/70 py-16 sm:py-20">
        <div className="mx-auto max-w-5xl px-4 sm:px-6">
          <Reveal>
            <SectionTitle>What you walk away with</SectionTitle>
            <p className="mx-auto mt-4 max-w-xl text-center text-lg text-ink-soft">
              The end of the event, not the middle of it. This is the last screen.
            </p>
          </Reveal>
          <Reveal delay={0.1} className="mt-10">
            <CloseoutPreview />
          </Reveal>
          <Reveal delay={0.15}>
            <dl className="mt-8 grid gap-4 text-center sm:grid-cols-3">
              {[
                ["6 of 6", "planted mistakes caught on a test event: bad math, a duplicate, a missing payer, and more"],
                ["99.5%", "of line items read right on 14 test receipts, and 100% on 12 it had never seen"],
                ["0 rows", "reach your sheet before you approve them"],
              ].map(([big, small]) => (
                <div key={big} className="lift rounded-2xl border-2 border-forest bg-white p-5">
                  <dt className="font-display text-3xl font-black text-forest">{big}</dt>
                  <dd className="mt-1 text-sm text-ink-soft">{small}</dd>
                </div>
              ))}
            </dl>
          </Reveal>
        </div>
      </section>

      <section id="how" className="scroll-mt-20 py-16 sm:py-20">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <Reveal><SectionTitle>How it works</SectionTitle></Reveal>
          <ol className="mt-10 grid gap-5 md:grid-cols-3">
            {STEPS.map((s, i) => (
              <Reveal key={s.title} delay={i * 0.08}>
                <li className="lift group relative h-full rounded-3xl border-2 border-sun bg-how p-5 text-center">
                  <span className="absolute -top-4 left-1/2 grid size-9 -translate-x-1/2 place-items-center rounded-full bg-forest font-round font-bold text-white">
                    {i + 1}
                  </span>
                  <img src={s.img} alt="" className="mx-auto h-44 w-auto transition duration-300 group-hover:scale-105" />
                  <h3 className="mt-2 font-round text-2xl font-bold text-forest">{s.title}</h3>
                  <p className="mt-2 text-ink-soft">{s.body}</p>
                </li>
              </Reveal>
            ))}
          </ol>
        </div>
      </section>

      <section id="features" className="scroll-mt-20 bg-paper/70 py-16 sm:py-20">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <Reveal><SectionTitle>Everything a treasurer needs</SectionTitle></Reveal>
          <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f, i) => (
              <Reveal key={f.title} delay={(i % 3) * 0.08}>
                <article className="lift group h-full rounded-3xl border-2 border-forest bg-cream-2 p-5 text-center">
                  <img src={f.img} alt="" className="mx-auto h-32 w-auto transition duration-300 group-hover:-rotate-3 group-hover:scale-110" />
                  <h3 className="mt-3 font-round text-2xl font-bold text-forest">{f.title}</h3>
                  <p className="mt-1 text-ink-soft">{f.body}</p>
                </article>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section id="faq" className="scroll-mt-20 py-16 sm:py-20">
        <div className="mx-auto max-w-3xl px-4 sm:px-6">
          <Reveal><SectionTitle>Straight answers</SectionTitle></Reveal>
          <Reveal delay={0.1} className="mt-10"><Faq /></Reveal>
        </div>
      </section>

      <section className="px-4 pb-16 sm:px-6">
        <Reveal>
          <div className="relative mx-auto flex max-w-5xl flex-col items-center gap-5 overflow-hidden rounded-[2rem] bg-forest px-6 py-12 text-center text-white sm:flex-row sm:text-left">
            <img src="/art/mascot-empty.png" alt="" className="w-52 shrink-0 transition hover:rotate-6 hover:scale-110" />
            <div className="flex-1">
              <h2 className="font-display text-3xl font-black sm:text-4xl">Close out your next event tonight.</h2>
              <p className="mt-2 text-white/80">Bring the receipts. Tallyable does the adding up.</p>
            </div>
            <a href={APP_URL} className="btn bg-sun text-ink shadow-[0_4px_0_#B88A1F] hover:-translate-y-0.5 hover:bg-[#FFCB52]">
              Get Started <span className="arrow" aria-hidden>→</span>
            </a>
          </div>
        </Reveal>
      </section>

      <footer className="border-t border-line py-8">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-4 text-sm text-ink-soft sm:flex-row sm:px-6">
          <img src="/art/logo.png" alt="Tallyable" className="h-10 w-auto" />
          <p>Built by a college club treasurer. Demo data is fake.</p>
          <a href={REPO_URL} className="font-medium text-forest underline-offset-4 hover:underline">Source on GitHub</a>
        </div>
      </footer>
    </main>
  );
}
