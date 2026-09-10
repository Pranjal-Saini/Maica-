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

  /* ── keyboard shortcut ──────────────────────────────────────
     One binding: M opens the app, matching the badge on the nav's
     Get started. Kept generic over [data-key] so the binding lives
     next to the button it belongs to rather than in a list here.

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


  /* ── the wave field ─────────────────────────────────────────
     A ray is marched against a height field of summed sines and fogged
     toward a horizon — the construction the registry component uses, written
     against WebGL 2 directly so the page needs no React, no ogl and no
     bundler, and stays inside a CSP that admits same-origin scripts only.

     Three things keep it from being a battery drain in the corner of a
     landing page: it renders only while it is on screen, it caps device
     pixel ratio at 1.5 because a soft gradient does not need retina density,
     and under prefers-reduced-motion it draws a single frame and stops. */
  function drawWaves() {
    var canvas = document.getElementById("waves");
    if (!canvas) return;

    var gl = canvas.getContext("webgl2", { antialias: false, alpha: true });
    if (!gl) return;   // No WebGL 2: the panel keeps its own background.

    var VERT =
      "#version 300 es\n" +
      "in vec2 p; void main(){ gl_Position = vec4(p, 0.0, 1.0); }";

    var FRAG =
      "#version 300 es\n" +
      "precision highp float;\n" +
      "uniform vec2 res; uniform float t; uniform vec2 mouse;\n" +
      "uniform vec3 cHorizon, cWave, cCrest;\n" +
      "out vec4 frag;\n" +
      // Height field: a few sines at different scales and angles. The lowest
      // frequency is the swell; the rest is chop riding on it.
      "float wave(vec2 q){\n" +
      "  float h = sin(q.x * 0.42 + t * 0.55) * 1.00;\n" +
      "  h += sin(q.y * 0.31 - t * 0.41) * 0.85;\n" +
      "  h += sin((q.x + q.y) * 0.67 + t * 0.83) * 0.42;\n" +
      "  h += sin((q.x - q.y * 1.7) * 1.13 - t * 1.21) * 0.18;\n" +
      "  return h * 0.55;\n" +
      "}\n" +
      "void main(){\n" +
      "  vec2 uv = (gl_FragCoord.xy * 2.0 - res) / res.y;\n" +
      "  uv.x += mouse.x * 0.12; uv.y += mouse.y * 0.05;\n" +
      // Camera sits above the field, tilted down toward the horizon.
      "  vec3 ro = vec3(0.0, 2.6, -t * 1.3);\n" +
      "  vec3 rd = normalize(vec3(uv.x, uv.y * 0.62 - 0.30, 1.0));\n" +
      "  float d = 0.0; float hit = 0.0; vec3 pos = ro;\n" +
      "  for (int i = 0; i < 56; i++) {\n" +
      "    pos = ro + rd * d;\n" +
      "    float diff = pos.y - wave(pos.xz);\n" +
      "    if (diff < 0.035) { hit = 1.0; break; }\n" +
      "    d += max(diff * 0.42, 0.06);\n" +
      "    if (d > 44.0) break;\n" +
      "  }\n" +
      "  vec3 col = cHorizon;\n" +
      "  if (hit > 0.5) {\n" +
      // Crest weight from the local slope: steep water catches the light.
      "    float e = 0.12;\n" +
      "    float hx = wave(pos.xz + vec2(e, 0.0)) - wave(pos.xz - vec2(e, 0.0));\n" +
      "    float hz = wave(pos.xz + vec2(0.0, e)) - wave(pos.xz - vec2(0.0, e));\n" +
      "    float slope = clamp(length(vec2(hx, hz)) * 2.6, 0.0, 1.0);\n" +
      "    float crest = smoothstep(0.30, 0.95, slope);\n" +
      "    col = mix(cWave, cCrest, crest * 0.85);\n" +
      "    col = mix(col, cHorizon, smoothstep(4.0, 30.0, d));\n" +   // fog
      "  }\n" +
      // A little grain, so the gradient does not band on wide flat areas.
      "  float g = fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453);\n" +
      "  col += (g - 0.5) * 0.045;\n" +
      "  float edge = smoothstep(0.0, 0.45, uv.y + 0.75);\n" +
      "  frag = vec4(col, edge);\n" +
      "}";

    function compile(type, src) {
      var sh = gl.createShader(type);
      gl.shaderSource(sh, src);
      gl.compileShader(sh);
      return gl.getShaderParameter(sh, gl.COMPILE_STATUS) ? sh : null;
    }

    var vs = compile(gl.VERTEX_SHADER, VERT);
    var fs = compile(gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) return;

    var prog = gl.createProgram();
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return;
    gl.useProgram(prog);

    // One triangle covering the viewport — cheaper than two, and no seam.
    var buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    var loc = gl.getAttribLocation(prog, "p");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

    var uRes = gl.getUniformLocation(prog, "res");
    var uT = gl.getUniformLocation(prog, "t");
    var uMouse = gl.getUniformLocation(prog, "mouse");
    gl.uniform3f(gl.getUniformLocation(prog, "cHorizon"), 0.039, 0.063, 0.188);
    gl.uniform3f(gl.getUniformLocation(prog, "cWave"), 0.220, 0.310, 1.000);
    gl.uniform3f(gl.getUniformLocation(prog, "cCrest"), 0.855, 0.890, 1.000);

    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    var mx = 0, my = 0, tx = 0, ty = 0;
    var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function size() {
      var dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      var w = Math.max(1, Math.round(canvas.clientWidth * dpr));
      var hh = Math.max(1, Math.round(canvas.clientHeight * dpr));
      if (canvas.width !== w || canvas.height !== hh) {
        canvas.width = w; canvas.height = hh;
        gl.viewport(0, 0, w, hh);
      }
      gl.uniform2f(uRes, canvas.width, canvas.height);
    }

    function render(time) {
      size();
      tx += (mx - tx) * 0.06;
      ty += (my - ty) * 0.06;
      gl.uniform2f(uMouse, tx, ty);
      gl.uniform1f(uT, (time || 0) * 0.0004);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      canvas.setAttribute("data-ready", "true");
    }

    if (reduced) { render(3000); return; }   // One frame, then stop.

    var running = false, raf = 0;
    function loop(time) { render(time); raf = requestAnimationFrame(loop); }

    // Only while it is on screen. A shader running behind a scrolled-past
    // section is pure battery.
    if (window.IntersectionObserver) {
      new IntersectionObserver(function (entries) {
        var visible = entries[0].isIntersecting;
        if (visible && !running) { running = true; raf = requestAnimationFrame(loop); }
        else if (!visible && running) { running = false; cancelAnimationFrame(raf); }
      }, { threshold: 0.01 }).observe(canvas);
    } else {
      running = true; raf = requestAnimationFrame(loop);
    }

    document.addEventListener("mousemove", function (e) {
      mx = (e.clientX / window.innerWidth) * 2 - 1;
      my = (e.clientY / window.innerHeight) * 2 - 1;
    }, { passive: true });
  }

  wireAppLinks();
  setUpConsent();
  drawWaves();
  wireShortcuts();
})();
