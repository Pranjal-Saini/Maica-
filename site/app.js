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

  /* ── hero graphic ───────────────────────────────────────────
     Many faint paths resolving on one point: contributing factors
     converging on one transaction. The same drawing as the app's
     sign-in panel, so the site and the product read as one thing.

     Seeded, so the composition is fixed rather than different on
     every load, and drawn once per size rather than animated —
     nothing to pause for reduced motion, nothing draining a
     battery. Decorative, so the canvas is aria-hidden.           */
  function drawTraces() {
    var canvas = document.getElementById("traces");
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

      var fx = w * 0.82, fy = h * 0.2;

      var glow = ctx.createRadialGradient(fx, fy, 0, fx, fy, h * 0.9);
      glow.addColorStop(0, "rgba(56, 79, 255, 0.22)");
      glow.addColorStop(1, "rgba(56, 79, 255, 0)");
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, w, h);

      var random = rng(20260907);
      var count = w < 700 ? 24 : 42;

      for (var i = 0; i < count; i++) {
        var t = i / (count - 1);
        var sy = h * (-0.2 + 1.35 * t) + (random() - 0.5) * h * 0.05;
        var cx = w * (0.3 + random() * 0.45);
        var cy = sy + (fy - sy) * (0.08 + random() * 0.28);

        ctx.beginPath();
        ctx.moveTo(-w * 0.05, sy);
        ctx.quadraticCurveTo(cx, cy, fx, fy);
        var strength = 0.04 + 0.14 * (1 - Math.abs(t - 0.45) * 1.9);
        ctx.strokeStyle = "rgba(157, 176, 255, " + Math.max(strength, 0.02).toFixed(3) + ")";
        ctx.lineWidth = 0.6 + random() * 0.7;
        ctx.stroke();
      }

      var marks = rng(775);
      for (var j = 0; j < 7; j++) {
        var d = 0.18 + marks() * 0.6;
        var x = fx - (fx + w * 0.05) * d;
        var y = fy + (marks() - 0.5) * h * 0.55 * d;
        ctx.beginPath();
        ctx.arc(x, y, 1.5 + marks() * 1.3, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(157, 176, 255, " + (0.45 - d * 0.35).toFixed(3) + ")";
        ctx.fill();
      }

      ctx.beginPath();
      ctx.arc(fx, fy, 3.2, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(230, 233, 255, 0.9)";
      ctx.fill();
    }

    draw();
    var pending;
    window.addEventListener("resize", function () {
      clearTimeout(pending);
      pending = setTimeout(draw, 120);
    });
  }

  wireAppLinks();
  setUpConsent();
  drawTraces();
})();
