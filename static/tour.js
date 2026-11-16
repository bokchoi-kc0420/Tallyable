/* Tally's demo tour (ui/tour.py hands over window.TLY_TOUR = {token, stops: [[selector, line], ...], img}).
   Everything blurs except one spot; Tally stands beside it and reaches for it with his stick arm (the intro's
   rig: real body + face images, arms and legs drawn here). A stop shows when its spot is on the page and goes
   away on "Got it" or a click on the spot. Progress lives in localStorage, so reruns and new pages keep it. */
(() => {
  const KEY = "tly-tour", S = 0.7, GAP = 32;
  const load = () => { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch { return {}; } };
  const save = (st) => { try { localStorage.setItem(KEY, JSON.stringify(st)); } catch { /* private window: tour just restarts */ } };

  if (!window.tlyTour) window.tlyTour = (() => {
    let cfg = null, cur = -1, el = null, raf = 0, ui = null;
    const state = () => load();
    const mark = (patch) => { save({ ...state(), ...patch }); check(); };
    const doneOne = (i) => mark({ done: [...new Set([...(state().done || []), i])] });

    function build() {
      const d = document.createElement("div");
      d.id = "tly-tour";
      d.innerHTML = `<div class="veil"></div><div class="ring"></div>
        <div class="tal"><div class="limb leg l"><i></i><b class="foot"></b></div><div class="limb leg r"><i></i><b class="foot"></b></div>
          <div class="limb arm back"><i></i><b></b></div><div class="limb arm reach"><i></i><b></b></div>
          <img class="body" src="${cfg.img}tally-base.png" alt=""><img class="body" src="${cfg.img}tally-face-happy.png" alt=""></div>
        <div class="bub" role="dialog" aria-live="polite"><p></p><div class="row"><span class="cnt"></span>
          <button class="skip" type="button">Skip tour</button><button class="go" type="button">Got it</button></div></div>`;
      d.querySelector(".skip").onclick = () => mark({ off: true });
      d.querySelector(".go").onclick = () => doneOne(cur);
      document.body.appendChild(d);
      // a click on the sharp spot counts as doing the step
      document.addEventListener("click", (e) => { if (el && cur >= 0 && el.contains(e.target)) setTimeout(() => doneOne(cur), 0); }, true);
      return d;
    }

    function pick() {
      const st = state();
      if (!cfg || st.off || !document.querySelector(".tly-demo-pill") || document.querySelector('[role="dialog"]:not(#tly-tour .bub)')) return [-1, null];
      for (let i = 0; i < cfg.stops.length; i++) {
        if ((st.done || []).includes(i)) continue;
        const t = document.querySelector(cfg.stops[i][0]);
        if (t && t.getBoundingClientRect().width > 0) return [i, t];
      }
      return [-1, null];
    }

    function check() {
      const [i, t] = pick();
      if (i < 0) { if (ui) ui.style.display = "none"; cur = -1; el = null; cancelAnimationFrame(raf); return; }
      ui = ui || build();
      if (i !== cur) {
        cur = i; el = t;
        ui.querySelector(".bub p").textContent = cfg.stops[i][1];
        ui.querySelector(".cnt").textContent = `${i + 1} of ${cfg.stops.length}`;
        ui.querySelector(".go").textContent = i === cfg.stops.length - 1 ? "Let's go!" : "Got it";
        ui.style.display = "";
        ui.classList.remove("pop"); void ui.offsetWidth; ui.classList.add("pop");
        t.scrollIntoView({ block: "center", behavior: "smooth" });
      }
      el = t;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(place);
    }

    // Lay out the hole, Tally and his bubble around the spot, every frame while it shows (the page scrolls and reflows).
    function place() {
      if (!el || !el.isConnected) return check();
      const r = el.getBoundingClientRect(), W = innerWidth, H = innerHeight, pad = 8;
      const x0 = Math.max(4, r.left - pad), y0 = Math.max(4, r.top - pad), x1 = Math.min(W - 4, r.right + pad), y1 = Math.min(H - 4, r.bottom + pad);
      const rr = 16, hole = `M${x0 + rr},${y0} H${x1 - rr} Q${x1},${y0} ${x1},${y0 + rr} V${y1 - rr} Q${x1},${y1} ${x1 - rr},${y1} H${x0 + rr} Q${x0},${y1} ${x0},${y1 - rr} V${y0 + rr} Q${x0},${y0} ${x0 + rr},${y0} Z`;
      ui.querySelector(".veil").style.clipPath = `path(evenodd, "M0,0 H${W} V${H} H0 Z ${hole}")`;
      Object.assign(ui.querySelector(".ring").style, { left: x0 + "px", top: y0 + "px", width: x1 - x0 + "px", height: y1 - y0 + "px" });

      // Tally: to the right of the spot if it fits, else to its left, else above it, reaching for its nearest edge
      const bw = 150 * S, tall = 278 * S, room = bw + 2 * GAP;
      let fx, fy, side;
      if (W - x1 > room + 120) { side = "right"; fx = x1 + GAP + bw / 2; }
      else if (y0 > tall + 160) { side = "up"; fx = Math.min(x1 - bw, x0 + 160); }   // wide spots: he stands on top
      else { side = "left"; fx = Math.max(bw / 2 + 16, x0 - GAP - bw / 2); }
      fy = side === "up" ? y0 - 16 : Math.min(H - 16, Math.max(tall + 200, (y0 + y1) / 2 + tall / 2));
      const tal = ui.querySelector(".tal");
      tal.style.transform = `translate(${fx}px,${fy}px)`;
      const sx = side === "left" ? 70 * S : -70 * S, sy = -128 * S;   // shoulder of the reaching arm, from his feet
      const aimX = side === "right" ? x1 + 4 : side === "left" ? x0 - 4 : fx + sx - 48;   // up: down and out, onto the spot's edge
      const aimY = side === "up" ? y0 + 4 : Math.min(y1 - 16, Math.max(y0 + 16, fy + sy - 24));
      const dx = aimX - (fx + sx), dy = aimY - (fy + sy), len = Math.max(28, Math.hypot(dx, dy) - 12 * S);
      const reach = tal.querySelector(".reach"), back = tal.querySelector(".back");
      reach.style.left = sx + "px"; back.style.left = -sx + "px";
      reach.style.transform = `rotate(${Math.atan2(-dx, dy)}rad)`;
      reach.querySelector("i").style.height = len + "px"; reach.querySelector("b").style.top = len - 12 + "px";
      back.style.transform = `rotate(${side === "left" ? -14 : 14}deg)`;

      // his bubble sits over his head with its tail on him, kept on screen and off the spot
      const b = ui.querySelector(".bub"), bwid = b.offsetWidth, bh = b.offsetHeight, head = fy - tall;
      let bx = side === "left" ? fx - bwid + 48 : fx - 48, by = head - 16 - bh;
      bx = Math.min(W - bwid - 16, Math.max(16, bx));
      if (by < 16) by = 16;
      b.style.transform = `translate(${bx}px,${by}px)`;
      b.style.setProperty("--tx", Math.min(bwid - 24, Math.max(24, fx - bx)) + "px");
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
