/* Shared behaviour for every page. Loaded with `defer`, so it never blocks
   rendering and the page is readable before this runs. */
(function () {
  "use strict";

  /* ── where the app lives ────────────────────────────────────
     One place to change. The app root already routes by session —
     /dashboard when there is one, /login when there is not — so a
     single link serves both states and the app decides.

     This page cannot tell the difference itself: the session cookie
     belongs to app.maica.in and is HttpOnly, so script here can
     neither read it nor ask across origins without opening CORS on
     the host that holds client evidence.                          */
  var APP_URL = "https://app.maica.in";

  /* ── analytics ──────────────────────────────────────────────
     Cloudflare Web Analytics: no cookies, no cross-site tracking,
     no personal data. Paste the token from the Cloudflare dashboard
     (Web Analytics → your site → the `token` in the snippet) and it
     starts working. Empty means analytics is simply off, which is
     why the consent notice stays hidden until you fill it in —
     asking permission to collect nothing would be theatre.        */
  var ANALYTICS_TOKEN = "";

  var CONSENT_KEY = "maica.analytics-consent";

  function appTarget() {
    return APP_URL.replace(/\/+$/, "") + "/";
  }

  function wireAppLinks() {
    var target = appTarget();
    var links = document.querySelectorAll("a.js-app");
    for (var i = 0; i < links.length; i++) links[i].href = target;
  }

  /* ── consent ────────────────────────────────────────────────
     The site sets no cookies of its own. This governs whether the
     analytics script loads at all, and the answer is remembered in
     localStorage rather than a cookie — so declining does not
     itself create the thing you declined.                        */
  function readConsent() {
    try { return window.localStorage.getItem(CONSENT_KEY); }
    catch (e) { return null; }  // private mode, or storage blocked
  }

  function writeConsent(value) {
    try { window.localStorage.setItem(CONSENT_KEY, value); } catch (e) {}
  }

  function loadAnalytics() {
    if (!ANALYTICS_TOKEN) return;
    var s = document.createElement("script");
    s.defer = true;
    s.src = "https://static.cloudflareinsights.com/beacon.min.js";
    s.setAttribute("data-cf-beacon", JSON.stringify({ token: ANALYTICS_TOKEN }));
    document.head.appendChild(s);
  }

  function setUpConsent() {
    var box = document.getElementById("consent");
    if (!box) return;

    // Nothing to consent to until a token exists.
    if (!ANALYTICS_TOKEN) { box.remove(); return; }

    var choice = readConsent();
    if (choice === "granted") { loadAnalytics(); box.remove(); return; }
    if (choice === "denied") { box.remove(); return; }

    box.setAttribute("data-open", "true");

    var accept = document.getElementById("consent-accept");
    var decline = document.getElementById("consent-decline");

    if (accept) {
      accept.addEventListener("click", function () {
        writeConsent("granted");
        loadAnalytics();
        box.remove();
      });
    }
    if (decline) {
      decline.addEventListener("click", function () {
        writeConsent("denied");
        box.remove();
      });
    }
  }

  /* ── keyboard shortcuts ─────────────────────────────────────
     The badges on the hero buttons name a key that actually works.
     A badge that decorated nothing would be a lie told in a corner
     of the page nobody would think to check.

     Ignored while typing in a field, and while a modifier is held,
     so browser and assistive-tech shortcuts keep working.        */
  function wireShortcuts() {
    var targets = document.querySelectorAll("[data-key]");
    if (!targets.length) return;

    var byKey = {};
    for (var i = 0; i < targets.length; i++) {
      byKey[targets[i].getAttribute("data-key").toLowerCase()] = targets[i];
    }

    document.addEventListener("keydown", function (e) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      var el = document.activeElement;
      if (el && (el.isContentEditable || /^(input|textarea|select)$/i.test(el.tagName))) return;

      var hit = byKey[(e.key || "").toLowerCase()];
      if (!hit) return;
      e.preventDefault();
      hit.click();
    });
  }


  /* ── the mound ──────────────────────────────────────────────
     A heap of records under the closing call to action. Density
     falls off away from the peak and upward from the base, so the
     shape reads as a pile rather than a rectangle of noise. A few
     squares are brighter: the ones that ranked.

     Seeded, so the heap is the same on every load, and drawn once
     per size rather than animated.                              */
  function drawMound() {
    var canvas = document.getElementById("mound");
    if (!canvas || !canvas.getContext) return;
    var ctx = canvas.getContext("2d");

    function rng(seed) {
      return function () {
        seed = (seed * 1664525 + 1013904223) % 4294967296;
        return seed / 4294967296;
      };
    }

    function draw() {
      var w = canvas.clientWidth, h = canvas.clientHeight;
      if (!w || !h) return;
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      var box = 5, gap = 3, step = box + gap;
      var cols = Math.floor(w / step), rows = Math.floor(h / step);
      var random = rng(20260910);
      var peak = 0.62;   // where the heap is tallest, across the width

      for (var cx = 0; cx < cols; cx++) {
        var fx = cx / (cols - 1);
        // A smooth bump, taller at the peak and tailing off either side.
        var height = Math.exp(-Math.pow((fx - peak) / 0.34, 2));
        for (var cy = 0; cy < rows; cy++) {
          var fromBase = (rows - 1 - cy) / rows;   // 0 at the base, 1 at the top
          if (fromBase > height) continue;
          // Solid near the base, thinning towards the surface.
          var density = 1 - fromBase / Math.max(height, 0.001);
          if (random() > 0.25 + density * 0.75) continue;

          var lit = random() < 0.06;
          ctx.fillStyle = lit
            ? "rgba(140, 162, 255, .95)"
            : "rgba(120, 142, 255, " + (0.16 + density * 0.4).toFixed(2) + ")";
          ctx.fillRect(cx * step, cy * step, box, box);
        }
      }
    }

    draw();
    var pending;
    window.addEventListener("resize", function () {
      clearTimeout(pending);
      pending = setTimeout(draw, 150);
    });
  }

  wireAppLinks();
  setUpConsent();
  drawMound();
  wireShortcuts();
})();
