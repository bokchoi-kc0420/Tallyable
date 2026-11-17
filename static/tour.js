/* Tally's demo tour (ui/tour.py hands over window.TLY_TOUR = {token, stops: [{spot, hand, explain, hint, info,
   quiet, until}], img}). Explain phase: everything blurs except the spot, Tally (a pose of
   his own per stop) stands by it and "Got it" hands the page back. Nudge phase: no blur, the green button pulses
   with Tally beside it and a one-line hint, and the stop ends once that button is clicked (or its
   `until` shows up). Progress lives in localStorage, so reruns and new pages keep it. */
(() => {
  const KEY = "tly-tour", K = 0.3;  // pose size: the art is drawn at about 3.3x
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
        <img class="pose" alt="">
        <div class="bub" role="dialog" aria-live="polite"><h4 class="ttl"></h4><p></p><div class="row"><span class="cnt"></span>
          <button class="skip" type="button">Skip tour</button><button class="go" type="button">Got it</button></div></div>`;
      // The last stop asks what's next: their own club (a fresh page load in real mode) or another demo event.
      d.querySelector(".skip").onclick = () => {
        if (!cfg.stops[cur].end) return mark({ off: true });
        doneOne(cur); document.querySelector(cfg.stops[cur].spot + " button")?.click();
      };
      d.querySelector(".go").onclick = () => {
        if (cfg.stops[cur].end) return location.assign("?demo=off");
        cfg.stops[cur].info ? doneOne(cur) : add("seen", cur);  // page is theirs now
      };
      document.body.appendChild(d);
      // the blur sits over the page, so a wheel on it scrolls the page underneath (to see the rest of the spot)
      d.querySelector(".veil").addEventListener("wheel", (e) => {
        let n = el && el.parentElement;
        while (n && !(n.scrollHeight > n.clientHeight && /auto|scroll/.test(getComputedStyle(n).overflowY))) n = n.parentElement;
        (n || document.scrollingElement).scrollBy(0, e.deltaY);
      }, { passive: true });
      // only a click on the green button counts as doing the step (picking a name in the spot doesn't)
      document.addEventListener("click", (e) => {
        const s = cur >= 0 && cfg.stops[cur], h = s && !s.info && document.querySelector(s.hand || s.spot);
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
        ui.querySelector(".cnt").textContent = `${i + 1} of ${cfg.stops.length}`;
        ui.dataset.stop = i; ui.dataset.phase = p;
        const img = ui.querySelector(".pose"), src = `${cfg.img}tally-${s.pose}.png`;
        if (!img.src.endsWith(src)) img.src = src;
        ui.classList.toggle("end", !!s.end);
        ui.querySelector(".ttl").textContent = s.title || "";
        ui.querySelector(".go").textContent = s.end ? "Set up my club" : "Got it";
        ui.querySelector(".skip").textContent = s.end ? "Try another demo event" : "Skip tour";
        ui.querySelector(".go").style.display = p === "explain" ? "" : "none";  // a nudge ends on its own button
        ui.classList.toggle("nudge", p === "nudge");
        ui.classList.toggle("quiet", p === "nudge" && !!s.quiet);
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

    // Lay out the hole, Tally and his bubble around the spot, every frame while it shows (the page scrolls and reflows).
    function place() {
      if (!el || !el.isConnected) return check();
      if (cfg.stops[cur].end) return middle();
      const r = el.getBoundingClientRect(), W = innerWidth, H = innerHeight, pad = 8;
      ui.classList.toggle("away", phase === "nudge" && (r.bottom < 0 || r.top > H));  // scrolled off: Tally waits there
      const x0 = Math.max(4, r.left - pad), y0 = Math.max(4, r.top - pad), x1 = Math.min(W - 4, r.right + pad), y1 = Math.min(H - 4, r.bottom + pad);
      const rr = 16, hole = `M${x0 + rr},${y0} H${x1 - rr} Q${x1},${y0} ${x1},${y0 + rr} V${y1 - rr} Q${x1},${y1} ${x1 - rr},${y1} H${x0 + rr} Q${x0},${y1} ${x0},${y1 - rr} V${y0 + rr} Q${x0},${y0} ${x0 + rr},${y0} Z`;
      ui.querySelector(".veil").style.clipPath = `path(evenodd, "M0,0 H${W} V${H} H0 Z ${hole}")`;
      Object.assign(ui.querySelector(".ring").style, { left: x0 + "px", top: y0 + "px", width: x1 - x0 + "px", height: y1 - y0 + "px" });

      // Tally (this stop's own pose, never cut off) perches on top of the button's right end, so he doesn't cover
      // what sits beside it; with no room above he stands beside it. Explaining, he perches on the spot instead.
      const h = phase === "nudge" && hand && hand.isConnected ? hand.getBoundingClientRect() : r;
      const img = ui.querySelector(".pose"), pw = img.naturalWidth * K, ph = img.naturalHeight * K;
      let px, py;
      if (h.top - ph > 72) { px = Math.min(W - pw - 8, h.right - pw * 0.8); py = h.top - ph + 6; }
      else if (W - h.right > pw + 24) { px = h.right + 12; py = h.bottom - ph; }
      else { px = Math.max(8, h.left - 12 - pw); py = h.bottom - ph; }
      Object.assign(img.style, { width: pw + "px", height: ph + "px", transform: `translate(${px}px,${Math.max(8, py)}px)` });

      const b = ui.querySelector(".bub"), bwid = b.offsetWidth, bh = b.offsetHeight, mid = px + pw / 2;
      let bx = mid - 48, by = Math.max(8, py) - 12 - bh;
      const beside = by < 16;
      if (beside) { by = Math.max(16, py + 16); bx = px + pw + 12 + bwid < W - 16 ? px + pw + 12 : px - 12 - bwid; }
      b.classList.toggle("side", beside); b.classList.toggle("flip", beside && bx < px);
      bx = Math.min(W - bwid - 16, Math.max(16, bx)); by = Math.min(H - bh - 16, by);
      b.style.transform = `translate(${bx}px,${by}px)`;
      b.style.setProperty("--tx", Math.min(bwid - 24, Math.max(24, mid - bx)) + "px");
      raf = requestAnimationFrame(place);
    }

    // The last stop: the whole page blurs, and Tally peeks over a card in the middle (his feet behind it).
    function middle() {
      const W = innerWidth, H = innerHeight, b = ui.querySelector(".bub"), img = ui.querySelector(".pose");
      const pw = img.naturalWidth * K, ph = img.naturalHeight * K, bx = (W - b.offsetWidth) / 2, by = (H - b.offsetHeight) / 2 + ph / 3;
      ui.querySelector(".veil").style.clipPath = "none";
      Object.assign(img.style, { width: pw + "px", height: ph + "px", transform: `translate(${(W - pw) / 2}px,${by - ph + 24}px)` });
      b.classList.remove("side", "flip");
      b.style.transform = `translate(${bx}px,${by}px)`;
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
