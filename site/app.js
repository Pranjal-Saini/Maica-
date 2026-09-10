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
     The supplied GradientWaves shader, running on plain WebGL 2. ogl's
     Renderer/Program/Mesh/Triangle are replaced by direct GL calls and the
     React effects by this function; the GLSL itself is unchanged.

     Config is the supplied one: speed .4, amplitude 2.5, waveScale .6,
     waveRatio .9, swell 35, turbulence 20, tilt 1.11, zoom 1, height 5.5,
     fogDepth 15, detail medium (70 steps), brightness 1, opacity 1, grain on
     at .05, mouse on with parallax .5.                                     */
  function drawWaves() {
    var canvas = document.getElementById("waves");
    if (!canvas) return;

    var gl = canvas.getContext("webgl2", {
      alpha: true,
      premultipliedAlpha: true,
      antialias: false
    });
    if (!gl) return;   // No WebGL 2: the panel keeps its own background.

    var VERT = `#version 300 es
in vec2 position;
void main() {
  gl_Position = vec4(position, 0.0, 1.0);
}
`;

    var FRAG = `#version 300 es
precision highp float;
uniform vec2 iResolution;
uniform float iTime;
uniform float uSpeed;
uniform float uAmplitude;
uniform float uWaveScale;
uniform float uWaveRatio;
uniform float uSwell;
uniform float uTurbulence;
uniform float uTilt;
uniform float uZoom;
uniform float uHeight;
uniform float uFogDepth;
uniform float uSteps;
uniform float uBrightness;
uniform float uOpacity;
uniform float uGrain;
uniform float uGrainIntensity;
uniform vec2 uMouse;
uniform float uParallax;
uniform bool uEnableMouse;
uniform vec3 uHorizonColor;
uniform vec3 uWaveColor;
uniform vec3 uCrestColor;
out vec4 fragColor;

const float MAX_DIST = 20000.0;

float hash21(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}

float plasma(vec3 r, vec2 freq, vec4 tc) {
  float mx = r.x + tc.x;
  mx += uSwell * sin((r.y + mx) / 20.0 + tc.y);
  float my = r.y - tc.z;
  my += uTurbulence * cos(r.x / 23.0 + tc.w);
  return r.z - (sin(mx * freq.x) * uAmplitude + sin(my * freq.y) * uAmplitude + uHeight);
}

float raymarch(vec3 pos, vec3 dir, vec2 freq, vec4 tc) {
  float dist = 0.0;
  for (int i = 0; i < 128; i++) {
    if (float(i) >= uSteps) break;
    float dscene = plasma(pos + dist * dir, freq, tc);
    if (abs(dscene) < 0.1) break;
    dist += 0.9 * dscene;
    if (!(abs(dist) < MAX_DIST)) return MAX_DIST;
  }
  return dist;
}

void main() {
  float T = iTime * uSpeed;
  vec2 freq = vec2(uWaveScale / 7.0, (uWaveScale * uWaveRatio) / 3.0);
  vec4 tc = vec4(T / 0.130, T / 0.810, T / 0.200, T / 0.710);
  float c, s;
  float vfov = (3.14159 / 2.3) / max(uZoom, 0.05);
  vec3 cam = vec3(0.0, 0.0, 30.0);
  vec2 uv = (gl_FragCoord.xy / iResolution.xy) - 0.5;
  uv.x *= iResolution.x / iResolution.y;
  uv.y *= -1.0;

  vec3 dir = vec3(0.0, 0.0, -1.0);
  float ulen = length(uv);
  float xrot = vfov * ulen;
  c = cos(xrot); s = sin(xrot);
  dir = mat3(1.0, 0.0, 0.0, 0.0, c, -s, 0.0, s, c) * dir;
  vec2 nuv = ulen > 1e-5 ? uv / ulen : vec2(1.0, 0.0);
  c = nuv.x; s = nuv.y;
  dir = mat3(c, -s, 0.0, s, c, 0.0, 0.0, 0.0, 1.0) * dir;
  c = cos(uTilt); s = sin(uTilt);
  dir = mat3(c, 0.0, s, 0.0, 1.0, 0.0, -s, 0.0, c) * dir;

  if (uEnableMouse) {
    float yaw = (uMouse.x - 0.5) * uParallax * 0.4;
    float pitch = (uMouse.y - 0.5) * uParallax * 0.4;
    c = cos(yaw); s = sin(yaw);
    dir = mat3(c, 0.0, s, 0.0, 1.0, 0.0, -s, 0.0, c) * dir;
    c = cos(pitch); s = sin(pitch);
    dir = mat3(1.0, 0.0, 0.0, 0.0, c, -s, 0.0, s, c) * dir;
  }

  float dist = raymarch(cam, dir, freq, tc);
  vec3 pos = cam + dist * dir;

  float t = clamp(uFogDepth / max(dist, 0.001), 0.0, 1.0);
  vec3 body = mix(uWaveColor, uCrestColor, clamp(pos.z * 0.08 + 0.5, 0.0, 1.0));
  vec3 col = mix(uHorizonColor, body, t);
  col *= uBrightness;
  col = clamp(col, 0.0, 1.0);

  float alpha = clamp(t, 0.0, 1.0) * uOpacity;
  if (uGrain > 0.5) {
    float g = hash21(gl_FragCoord.xy + mod(iTime, 64.0) * 11.0);
    alpha += (g - 0.5) * uGrainIntensity;
  }
  alpha = clamp(alpha, 0.0, 1.0);
  fragColor = vec4(col * alpha, alpha);
}
`;

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

    // ogl's Triangle: one oversized triangle covering the viewport.
    var buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    var aPos = gl.getAttribLocation(prog, "position");
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    function u(name) { return gl.getUniformLocation(prog, name); }

    function hexToRgb(hex) {
      var m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
      if (!m) return [1, 1, 1];
      return [parseInt(m[1], 16) / 255, parseInt(m[2], 16) / 255, parseInt(m[3], 16) / 255];
    }

    // The supplied configuration.
    gl.uniform1f(u("uSpeed"), 0.4);
    gl.uniform1f(u("uAmplitude"), 2.5);
    gl.uniform1f(u("uWaveScale"), 0.6);
    gl.uniform1f(u("uWaveRatio"), 0.9);
    gl.uniform1f(u("uSwell"), 35.0);
    gl.uniform1f(u("uTurbulence"), 20.0);
    gl.uniform1f(u("uTilt"), 1.11);
    gl.uniform1f(u("uZoom"), 1.0);
    gl.uniform1f(u("uHeight"), 5.5);
    gl.uniform1f(u("uFogDepth"), 15.0);
    gl.uniform1f(u("uSteps"), 70.0);          // detail: medium
    gl.uniform1f(u("uBrightness"), 1.0);
    gl.uniform1f(u("uOpacity"), 1.0);
    gl.uniform1f(u("uGrain"), 1.0);
    gl.uniform1f(u("uGrainIntensity"), 0.05);
    gl.uniform1f(u("uParallax"), 0.5);
    gl.uniform1i(u("uEnableMouse"), 1);
    gl.uniform3fv(u("uHorizonColor"), hexToRgb("#5227FF"));
    gl.uniform3fv(u("uWaveColor"), hexToRgb("#FF9FFC"));
    gl.uniform3fv(u("uCrestColor"), hexToRgb("#FFFFFF"));

    var uRes = u("iResolution"), uTime = u("iTime"), uMouse = u("uMouse");

    // premultipliedAlpha: the shader already multiplies colour by alpha.
    gl.clearColor(0, 0, 0, 0);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);

    function setSize() {
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      var w = Math.max(1, Math.floor(canvas.clientWidth * dpr));
      var h = Math.max(1, Math.floor(canvas.clientHeight * dpr));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w; canvas.height = h;
        gl.viewport(0, 0, w, h);
      }
      gl.uniform2f(uRes, gl.drawingBufferWidth, gl.drawingBufferHeight);
    }

    if (window.ResizeObserver) new ResizeObserver(setSize).observe(canvas);
    else window.addEventListener("resize", setSize);
    setSize();

    var cur = [0.5, 0.5], tgt = [0.5, 0.5];
    canvas.parentNode.addEventListener("pointermove", function (e) {
      var r = canvas.getBoundingClientRect();
      tgt[0] = (e.clientX - r.left) / r.width;
      tgt[1] = 1.0 - (e.clientY - r.top) / r.height;
    }, { passive: true });
    canvas.parentNode.addEventListener("pointerleave", function () {
      tgt[0] = 0.5; tgt[1] = 0.5;
    }, { passive: true });

    var t0 = performance.now();
    function frame(now) {
      setSize();
      cur[0] += 0.05 * (tgt[0] - cur[0]);
      cur[1] += 0.05 * (tgt[1] - cur[1]);
      gl.uniform2f(uMouse, cur[0], cur[1]);
      gl.uniform1f(uTime, (now - t0) * 0.001);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      canvas.setAttribute("data-ready", "true");
    }

    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      frame(t0 + 3000);   // One frame, held.
      return;
    }

    var raf = 0, onScreen = true, pageOn = !document.hidden;
    function loop(now) { frame(now); raf = requestAnimationFrame(loop); }
    function start() { if (onScreen && pageOn && !raf) raf = requestAnimationFrame(loop); }
    function stop() { if (raf) { cancelAnimationFrame(raf); raf = 0; } }

    if (window.IntersectionObserver) {
      new IntersectionObserver(function (e) {
        onScreen = e[0].isIntersecting;
        onScreen ? start() : stop();
      }, { threshold: 0 }).observe(canvas);
    }
    document.addEventListener("visibilitychange", function () {
      pageOn = !document.hidden;
      pageOn ? start() : stop();
    });
    start();
  }

  /* ── border glow ────────────────────────────────────────────
     All React did for this component was set two custom properties from a
     pointermove: how close the cursor is to an edge, and its angle from the
     centre. The stylesheet does everything else.

     Edge proximity is the component's own measure — the ratio of the cursor's
     offset to the half-extent it would need to reach the boundary along
     whichever axis it reaches first — so it hits 100 exactly at the border
     and falls to 0 dead centre.                                            */
  function wireBorderGlow() {
    var cards = document.querySelectorAll(".border-glow-card");
    if (!cards.length) return;

    function onMove(card, e) {
      var rect = card.getBoundingClientRect();
      var cx = rect.width / 2, cy = rect.height / 2;
      var dx = (e.clientX - rect.left) - cx;
      var dy = (e.clientY - rect.top) - cy;

      var kx = dx !== 0 ? cx / Math.abs(dx) : Infinity;
      var ky = dy !== 0 ? cy / Math.abs(dy) : Infinity;
      var edge = Math.min(Math.max(1 / Math.min(kx, ky), 0), 1);

      var angle = 0;
      if (dx !== 0 || dy !== 0) {
        angle = Math.atan2(dy, dx) * (180 / Math.PI) + 90;
        if (angle < 0) angle += 360;
      }

      card.style.setProperty("--edge-proximity", (edge * 100).toFixed(3));
      card.style.setProperty("--cursor-angle", angle.toFixed(3) + "deg");
    }

    for (var i = 0; i < cards.length; i++) {
      (function (card) {
        card.addEventListener("pointermove", function (e) { onMove(card, e); }, { passive: true });
      })(cards[i]);
    }
  }

  wireAppLinks();
  wireBorderGlow();
  setUpConsent();
  drawWaves();
  wireShortcuts();
})();
