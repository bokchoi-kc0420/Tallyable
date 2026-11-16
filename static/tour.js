/* Tally's demo tour (ui/tour.py hands over window.TLY_TOUR = {token, stops: [[selector, line], ...], img}).
   Everything blurs except one spot; Tally stands beside it and reaches for it with his stick arm (the intro's
   rig: real body + face images, arms and legs drawn here). A stop shows when its spot is on the page and goes
   away on "Got it" or a click on the spot. Progress lives in localStorage, so reruns and new pages keep it. */
(() => {
  const KEY = "tly-tour", S = 0.7;
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

      // Tally stays close to the spot so his arm never grows past MAX (a long stick arm looks scary)
      const MAX = 48, tall = 278 * S, SH = 90, mid = Math.min(y1 - 16, Math.max(y0 + 16, (y0 + y1) / 2));
      const tal = ui.querySelector(".tal"), reach = tal.querySelector(".reach"), back = tal.querySelector(".back");
      const bodies = tal.querySelectorAll(".body"), legs = tal.querySelectorAll(".leg");
      let fx, fy, side, sx = -40, aimX, aimY, clip = "none", hideLegs = [false, false], hideBack = false;
      const fitsR = x1 + 141 < W - 8, fitsL = x0 - 141 > 8;
      if (y0 > 160) {                          // peeks over the top edge, the spot hides his lower half; hand on the ring
        side = "up"; fx = Math.min(x1 - 80, x0 + 120); fy = y0 + 70;
        aimX = fx + sx - 30; aimY = y0 + 4; clip = `inset(0 0 ${177 - (y0 - fy + 195)}px 0)`; hideLegs = [true, true]; hideBack = true;
      } else {                                 // no room above: stands right beside it, arm out level
        side = fitsR || !fitsL ? "right" : "left"; fx = side === "right" ? x1 + 89 : x0 - 89; sx = side === "right" ? -40 : 40;
        fy = Math.min(H - 8, mid + SH - 12); aimX = side === "right" ? x1 + 4 : x0 - 4; aimY = Math.min(y1 - 8, fy - SH + 20);
      }
      tal.style.transform = `translate(${fx}px,${fy}px)`;
      bodies.forEach((b) => { b.style.clipPath = clip; });
      legs.forEach((l, i) => { l.style.display = hideLegs[i] ? "none" : ""; });
      back.style.display = hideBack ? "none" : "";
      const dx = aimX - (fx + sx), dy = aimY - (fy - SH), len = Math.min(MAX, Math.max(20, Math.hypot(dx, dy) - 8));
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
