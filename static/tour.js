/* Tally's demo tour (ui/tour.py hands over window.TLY_TOUR = {token, stops: [{spot, hand, explain, hint, info,
   stay, until}], img}). Tally and his words sit in a card docked in a corner (a pose of his own per stop), so he
   never covers what he points at. Explain phase: everything blurs except the spot, and "Got it" hands the page back.
   Nudge phase: no blur, a green ring pulses round the button that does the step, and the stop ends once that button
   is clicked (or its `until` shows up). Scrolled away from it, the card offers "Show me". Progress lives in
   localStorage, so reruns, refreshes and new pages keep it. */
(() => {
  const KEY = "tly-tour", GAP = 24;  // card distance from the window edge
  const load = () => { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch { return {}; } };
  const save = (st) => { try { localStorage.setItem(KEY, JSON.stringify(st)); } catch { /* private window: tour just restarts */ } };

  if (!window.tlyTour) window.tlyTour = (() => {
    let cfg = null, cur = -1, el = null, hand = null, raf = 0, ui = null;
    const state = () => load();
    const mark = (patch) => { save({ ...state(), ...patch }); check(); };
    const add = (k, i) => mark({ [k]: [...new Set([...(state()[k] || []), i])] });
    const doneOne = (i) => add("done", i);
    let phase = "";

    function build() {
      const d = document.createElement("div");
      d.id = "tly-tour";
      d.innerHTML = `<div class="veil"></div><div class="ring"></div>
        <div class="bub" role="dialog" aria-live="polite"><img class="pose" alt=""><h4 class="ttl"></h4><p></p><div class="row"><span class="cnt"></span>
          <button class="skip" type="button">Skip tour</button><button class="show" type="button">Show me</button><button class="go" type="button">Got it</button></div></div>`;
      // The last stop asks what's next: their own club (a fresh page load in real mode) or another demo event.
      d.querySelector(".skip").onclick = () => {
        if (!cfg.stops[cur].end) return mark({ off: true });
        doneOne(cur); document.querySelector(cfg.stops[cur].spot + " button")?.click();
      };
      d.querySelector(".go").onclick = () => {
        if (cfg.stops[cur].end) return location.assign("?demo=off");
        cfg.stops[cur].info ? doneOne(cur) : add("seen", cur);  // page is theirs now
      };
      d.querySelector(".show").onclick = () => hand && hand.scrollIntoView({ block: "center", behavior: "smooth" });
      document.body.appendChild(d);
      // the blur sits over the page, so a wheel on it scrolls the page underneath (to see the rest of the spot)
      d.querySelector(".veil").addEventListener("wheel", (e) => {
        let n = el && el.parentElement;
        while (n && !(n.scrollHeight > n.clientHeight && /auto|scroll/.test(getComputedStyle(n).overflowY))) n = n.parentElement;
        (n || document.scrollingElement).scrollBy(0, e.deltaY);
      }, { passive: true });
      // only a click on the green button counts as doing the step (picking a name in the spot doesn't)
      document.addEventListener("click", (e) => {
        const s = cur >= 0 && cfg.stops[cur], h = s && !s.info && !s.stay && document.querySelector(s.hand || s.spot);
        if (h && h.contains(e.target)) setTimeout(() => doneOne(cur), 0);
      }, true);
      return d;
    }

    function pick() {
      const st = state();
      if (!cfg || st.off || !document.querySelector(".tly-demo-pill") || document.querySelector('[role="dialog"]:not(#tly-tour .bub)')) return [-1, null];
      for (let i = 0; i < cfg.stops.length; i++) {
        const s = cfg.stops[i];
        if ((st.done || []).includes(i)) continue;
        if (s.until && document.querySelector(s.until)) { doneOne(i); return [-1, null]; }  // done another way
        let p = s.explain && !(st.seen || []).includes(i) ? "explain" : "nudge";
        if (p === "explain" && s.typed && typed(s)) { add("seen", i); return [-1, null, ""]; }  // they put it in: on to the button
        const t = document.querySelector(p === "explain" ? s.spot : s.hand || s.spot);
        if (t && t.getBoundingClientRect().width > 0) return [i, t, p];
      }
      return [-1, null, ""];
    }

    const typed = (s) => (document.querySelector(s.spot)?.textContent || "").includes(s.typed);  // e.g. the total shows it

    function check() {
      const [i, t, p] = pick();
      if (i < 0) { if (ui) ui.style.display = "none"; cur = -1; el = null; cancelAnimationFrame(raf); return; }
      ui = ui || build();
      if (i !== cur || p !== phase) {
        cur = i; el = t; phase = p;
        const s = cfg.stops[i];
        ui.querySelector(".bub p").textContent = p === "explain" ? s.explain : s.hint || "";
        ui.querySelector(".cnt").textContent = `Step ${i + 1} of ${cfg.stops.length}`;
        ui.dataset.stop = i; ui.dataset.phase = p;
        const img = ui.querySelector(".pose"), src = `${cfg.img}tally-${s.pose}.png`;
        if (!img.src.endsWith(src)) img.src = src;
        ui.classList.toggle("end", !!s.end);
        ui.querySelector(".ttl").textContent = s.title || "";
        ui.querySelector(".go").textContent = s.end ? "Set up my club" : "Got it";
        ui.querySelector(".skip").textContent = s.end ? "Try another demo event" : "Skip tour";
        ui.querySelector(".go").style.display = p === "explain" ? "" : "none";  // a nudge ends on its own button
        ui.classList.toggle("nudge", p === "nudge");
        ui.style.display = "";
        ui.classList.remove("pop"); void ui.offsetWidth; ui.classList.add("pop");
        if (p === "explain" && !s.end) t.scrollIntoView({ block: "center", behavior: "smooth" });  // a nudge leaves the scroll alone
      }
      el = t;
      const inner = p === "explain" && cfg.stops[i].hand && document.querySelector(cfg.stops[i].hand);
      hand = inner && t.contains(inner) ? inner : t;  // explaining: his hand on the button only if it's in the spot
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(place);
    }

    // Lay out the hole and the ring round the spot, and dock the card in the first corner that keeps clear of it,
    // every frame while it shows (the page scrolls and reflows).
    function place() {
      if (!el || !el.isConnected) return check();
      if (cfg.stops[cur].end) return middle();
      const r = el.getBoundingClientRect(), W = innerWidth, H = innerHeight, pad = 8;
      const t = phase === "nudge" && hand && hand.isConnected ? hand.getBoundingClientRect() : r;
      ui.classList.toggle("away", phase === "nudge" && (t.bottom < 0 || t.top > H));
      const x0 = Math.max(4, r.left - pad), y0 = Math.max(4, r.top - pad), x1 = Math.min(W - 4, r.right + pad), y1 = Math.min(H - 4, r.bottom + pad);
      const rr = 16, hole = `M${x0 + rr},${y0} H${x1 - rr} Q${x1},${y0} ${x1},${y0 + rr} V${y1 - rr} Q${x1},${y1} ${x1 - rr},${y1} H${x0 + rr} Q${x0},${y1} ${x0},${y1 - rr} V${y0 + rr} Q${x0},${y0} ${x0 + rr},${y0} Z`;
      ui.querySelector(".veil").style.clipPath = `path(evenodd, "M0,0 H${W} V${H} H0 Z ${hole}")`;
      Object.assign(ui.querySelector(".ring").style, { left: t.left - pad + "px", top: t.top - pad + "px", width: t.width + 2 * pad + "px", height: t.height + 2 * pad + "px" });

      const b = ui.querySelector(".bub"), bw = b.offsetWidth, bh = b.offsetHeight;
      const clear = ([x, y]) => x > t.right + pad + 16 || x + bw < t.left - pad - 16 || y > t.bottom + pad + 16 || y + bh < t.top - pad - 16;
      const bar = document.querySelector(".st-key-upload-next, .st-key-finish-next")?.getBoundingClientRect();  // pinned to the bottom
      const low = bar && bar.height && bar.bottom >= H - 16 ? H - bar.top + 16 : GAP;  // sit above that bar, not on it
      const corners = [[W - bw - GAP, H - bh - low], [W - bw - GAP, GAP + 48], [Math.max(GAP, W / 2 - bw), H - bh - low]];
      if (cfg.stops[cur].dock === "top") corners.unshift(corners[1]);  // the boxes to fix sit at the bottom right
      const [bx, by] = corners.find(clear) || corners[0];  // bottom right, then top right, then bottom middle
      b.style.transform = `translate(${bx}px,${by}px)`;
      raf = requestAnimationFrame(place);
    }

    // The last stop: the whole page blurs, and Tally peeks over a card in the middle (his feet behind it).
    function middle() {
      const W = innerWidth, H = innerHeight, b = ui.querySelector(".bub");
      ui.querySelector(".veil").style.clipPath = "none";
      b.style.transform = `translate(${(W - b.offsetWidth) / 2}px,${(H - b.offsetHeight) / 2 + 48}px)`;
      raf = requestAnimationFrame(place);
    }

    new MutationObserver(() => { cancelAnimationFrame(raf); raf = requestAnimationFrame(check); })
      .observe(document.body, { childList: true, subtree: true });
    return {
      config(c) {
        cfg = c;
        if (state().token !== c.token) save({ token: c.token, done: [], off: false });  // a fresh demo: tour from the top
        check();
      },
    };
  })();
  window.tlyTour.config(window.TLY_TOUR);
})();
