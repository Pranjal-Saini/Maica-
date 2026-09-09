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

  wireAppLinks();
  setUpConsent();
})();
