// A static, fake-data copy of the app's Close out screen. Used on the landing page and inside the phone zoom.
const OWED = [
  { name: "Emma", n: 4, amt: "$41.20", paid: true, hue: "#F6C9B5" },
  { name: "Liam", n: 6, amt: "$18.75", paid: false, hue: "#BFE0C6" },
  { name: "Sophia", n: 4, amt: "$9.60", paid: false, hue: "#F7D88A" },
];

export function CloseoutPreview({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`rounded-3xl border-2 border-forest bg-paper ${compact ? "p-4" : "p-5 sm:p-7"} text-left`}>
      <div className="flex items-center gap-3">
        <img src="/art/mascot-cheer.png" alt="" className={`${compact ? "w-16" : "w-20 sm:w-24"} rounded-2xl bg-cheer`} />
        <div>
          <p className="font-round text-lg font-semibold text-forest sm:text-xl">All 14 receipts approved!</p>
          <p className="text-sm text-ink-soft">Fall Mixer · 14 receipts · 0 flags left</p>
        </div>
      </div>

      <div className={`mt-5 grid gap-4 ${compact ? "" : "md:grid-cols-2"}`}>
        <div className="rounded-2xl border border-line bg-white p-4">
          <p className="font-round font-semibold">Who&apos;s owed</p>
          <ul className="mt-3 space-y-3">
            {OWED.map((p) => (
              <li key={p.name} className="flex items-center gap-3">
                <span className="grid size-9 place-items-center rounded-full font-round font-semibold" style={{ background: p.hue }}>
                  {p.name[0]}
                </span>
                <span className="flex-1">
                  <span className="block font-medium leading-tight">{p.name}</span>
                  <span className="text-xs text-ink-soft">{p.n} receipts</span>
                </span>
                <span className={`font-semibold tabular-nums ${p.paid ? "text-ink-soft line-through" : ""}`}>{p.amt}</span>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-semibold ${p.paid ? "bg-forest text-white" : "bg-sun-soft text-ink"}`}
                >
                  {p.paid ? "Paid" : "Owed"}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-2xl border border-line bg-white p-4">
          <p className="font-round font-semibold">Funder report</p>
          <p className="mt-1 text-sm text-ink-soft">Every receipt, who paid, and the rule checks, ready to attach.</p>
          <p className="mt-3 inline-block rounded-full bg-sun-soft px-3 py-1 text-xs font-semibold">Due in 21 days</p>
          <p className="mt-4 font-round font-semibold">Money in vs out</p>
          <div className="mt-2 flex justify-between text-sm">
            <span>In <b className="tabular-nums">$180.00</b></span>
            <span>Out <b className="tabular-nums">$128.75</b></span>
          </div>
          <div className="mt-2 h-3 overflow-hidden rounded-full bg-line" role="img" aria-label="Money out is 72% of money in">
            <div className="h-full w-[72%] rounded-full bg-forest" />
          </div>
        </div>
      </div>
    </div>
  );
}
