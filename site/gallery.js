/* Circular gallery for the features section.

   The supplied CircularGallery, with React removed: the App/Media/Title
   classes are the ones from the source, driven by an init call instead of a
   useEffect. ogl is vendored under vendor/ogl and loaded as plain modules,
   because this site has no bundler and its CSP admits same-origin scripts
   only.

   Three deliberate departures from the original, each noted where it happens:

     - The component is an image carousel and MAICA has no photography, so
       each card is drawn on a canvas from the feature it stands for. The
       explanatory copy stays in the DOM underneath, where a screen reader and
       a crawler can still reach it — a WebGL canvas is opaque to both.

     - Scroll, drag and key listeners bind to the container rather than to
       window. As written they would capture the page's own scrolling, which
       on a long marketing page means the reader cannot get past this section.

     - The font loader is dropped. It fetches a Google Fonts stylesheet, which
       connect-src 'self' blocks, and the page already loads IBM Plex Mono.
*/

import { Camera, Mesh, Plane, Program, Renderer, Texture, Transform } from "./vendor/ogl/index.js";

const FEATURES = [
  { k: "Ingestion", t: "Two evidence types,\none timeline" },
  { k: "Reasoning", t: "Ranked,\nnot listed" },
  { k: "Provenance", t: "Every claim\ncites its row" },
  { k: "Access", t: "Read-only\nby construction" },
];

const LABEL_FONT = 'bold 30px "IBM Plex Mono", ui-monospace, monospace';
const CARD_W = 800;
const CARD_H = 600;

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function debounce(fn, wait) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), wait);
  };
}

/* Each card is drawn rather than photographed: the mono key, a rule, and the
   feature's title, on the panel colour the rest of the site uses. */
function drawCard(feature) {
  const c = document.createElement("canvas");
  c.width = CARD_W;
  c.height = CARD_H;
  const x = c.getContext("2d");

  x.fillStyle = "#12162e";
  x.fillRect(0, 0, CARD_W, CARD_H);

  const glow = x.createRadialGradient(CARD_W * 0.75, CARD_H * 0.2, 0, CARD_W * 0.75, CARD_H * 0.2, CARD_W * 0.8);
  glow.addColorStop(0, "rgba(56, 79, 255, 0.42)");
  glow.addColorStop(1, "rgba(56, 79, 255, 0)");
  x.fillStyle = glow;
  x.fillRect(0, 0, CARD_W, CARD_H);

  x.strokeStyle = "rgba(255, 255, 255, 0.22)";
  x.lineWidth = 2;
  x.strokeRect(1, 1, CARD_W - 2, CARD_H - 2);

  x.fillStyle = "#9db0ff";
  x.font = '500 30px "IBM Plex Mono", ui-monospace, monospace';
  x.textBaseline = "top";
  x.fillText(feature.k.toUpperCase(), 64, 72);

  x.strokeStyle = "rgba(157, 176, 255, 0.35)";
  x.lineWidth = 1;
  x.beginPath();
  x.moveTo(64, 132);
  x.lineTo(CARD_W - 64, 132);
  x.stroke();

  x.fillStyle = "#f5f6f1";
  x.font = '500 62px "IBM Plex Mono", ui-monospace, monospace';
  feature.t.split("\n").forEach((line, i) => {
    x.fillText(line, 64, 208 + i * 82);
  });

  return c;
}

function fontSize(font) {
  const m = font.match(/(\d+)px/);
  return m ? parseInt(m[1], 10) : 30;
}

function textTexture(gl, text, font, color) {
  const c = document.createElement("canvas");
  const x = c.getContext("2d");
  x.font = font;
  const w = Math.ceil(x.measureText(text).width);
  const h = Math.ceil(fontSize(font) * 1.2);
  c.width = w + 20;
  c.height = h + 20;
  x.font = font;
  x.fillStyle = color;
  x.textBaseline = "middle";
  x.textAlign = "center";
  x.clearRect(0, 0, c.width, c.height);
  x.fillText(text, c.width / 2, c.height / 2);
  const texture = new Texture(gl, { generateMipmaps: false });
  texture.image = c;
  return { texture, width: c.width, height: c.height };
}

class Title {
  constructor({ gl, plane, text, textColor, font }) {
    const { texture, width, height } = textTexture(gl, text, font, textColor);
    const program = new Program(gl, {
      vertex: `
        attribute vec3 position;
        attribute vec2 uv;
        uniform mat4 modelViewMatrix;
        uniform mat4 projectionMatrix;
        varying vec2 vUv;
        void main() {
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }`,
      fragment: `
        precision highp float;
        uniform sampler2D tMap;
        varying vec2 vUv;
        void main() {
          vec4 color = texture2D(tMap, vUv);
          if (color.a < 0.1) discard;
          gl_FragColor = color;
        }`,
      uniforms: { tMap: { value: texture } },
      transparent: true,
    });
    this.mesh = new Mesh(gl, { geometry: new Plane(gl), program });
    const th = plane.scale.y * 0.15;
    const tw = th * (width / height);
    this.mesh.scale.set(tw, th, 1);
    this.mesh.position.y = -plane.scale.y * 0.5 - th * 0.5 - 0.05;
    this.mesh.setParent(plane);
  }
}

class Media {
  constructor(opts) {
    Object.assign(this, opts);
    this.extra = 0;
    this.createShader();
    this.createMesh();
    this.title = new Title({
      gl: this.gl,
      plane: this.plane,
      text: this.text,
      textColor: this.textColor,
      font: this.font,
    });
    this.onResize();
  }

  createShader() {
    const texture = new Texture(this.gl, { generateMipmaps: true });
    this.program = new Program(this.gl, {
      depthTest: false,
      depthWrite: false,
      vertex: `
        precision highp float;
        attribute vec3 position;
        attribute vec2 uv;
        uniform mat4 modelViewMatrix;
        uniform mat4 projectionMatrix;
        uniform float uTime;
        uniform float uSpeed;
        varying vec2 vUv;
        void main() {
          vUv = uv;
          vec3 p = position;
          p.z = (sin(p.x * 4.0 + uTime) * 1.5 + cos(p.y * 2.0 + uTime) * 1.5) * (0.1 + uSpeed * 0.5);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
        }`,
      fragment: `
        precision highp float;
        uniform vec2 uImageSizes;
        uniform vec2 uPlaneSizes;
        uniform sampler2D tMap;
        uniform float uBorderRadius;
        varying vec2 vUv;

        float roundedBoxSDF(vec2 p, vec2 b, float r) {
          vec2 d = abs(p) - b;
          return length(max(d, vec2(0.0))) + min(max(d.x, d.y), 0.0) - r;
        }

        void main() {
          vec2 ratio = vec2(
            min((uPlaneSizes.x / uPlaneSizes.y) / (uImageSizes.x / uImageSizes.y), 1.0),
            min((uPlaneSizes.y / uPlaneSizes.x) / (uImageSizes.y / uImageSizes.x), 1.0)
          );
          vec2 uv = vec2(
            vUv.x * ratio.x + (1.0 - ratio.x) * 0.5,
            vUv.y * ratio.y + (1.0 - ratio.y) * 0.5
          );
          vec4 color = texture2D(tMap, uv);
          float d = roundedBoxSDF(vUv - 0.5, vec2(0.5 - uBorderRadius), uBorderRadius);
          float edgeSmooth = 0.002;
          float alpha = 1.0 - smoothstep(-edgeSmooth, edgeSmooth, d);
          gl_FragColor = vec4(color.rgb, alpha);
        }`,
      uniforms: {
        tMap: { value: texture },
        uPlaneSizes: { value: [0, 0] },
        uImageSizes: { value: [0, 0] },
        uSpeed: { value: 0 },
        uTime: { value: 100 * Math.random() },
        uBorderRadius: { value: this.borderRadius },
      },
      transparent: true,
    });

    // The card is a canvas we drew, so there is no network fetch and no
    // cross-origin dance — it is ready immediately.
    texture.image = this.canvas;
    this.program.uniforms.uImageSizes.value = [this.canvas.width, this.canvas.height];
  }

  createMesh() {
    this.plane = new Mesh(this.gl, { geometry: this.geometry, program: this.program });
    this.plane.setParent(this.scene);
  }

  update(scroll, direction) {
    this.plane.position.x = this.x - scroll.current - this.extra;

    const x = this.plane.position.x;
    const H = this.viewport.width / 2;

    if (this.bend === 0) {
      this.plane.position.y = 0;
      this.plane.rotation.z = 0;
    } else {
      const B = Math.abs(this.bend);
      const R = (H * H + B * B) / (2 * B);
      const ex = Math.min(Math.abs(x), H);
      const arc = R - Math.sqrt(R * R - ex * ex);
      if (this.bend > 0) {
        this.plane.position.y = -arc;
        this.plane.rotation.z = -Math.sign(x) * Math.asin(ex / R);
      } else {
        this.plane.position.y = arc;
        this.plane.rotation.z = Math.sign(x) * Math.asin(ex / R);
      }
    }

    this.speed = scroll.current - scroll.last;
    this.program.uniforms.uTime.value += 0.04;
    this.program.uniforms.uSpeed.value = this.speed;

    const half = this.plane.scale.x / 2;
    const edge = this.viewport.width / 2;
    this.isBefore = this.plane.position.x + half < -edge;
    this.isAfter = this.plane.position.x - half > edge;
    if (direction === "right" && this.isBefore) {
      this.extra -= this.widthTotal;
      this.isBefore = this.isAfter = false;
    }
    if (direction === "left" && this.isAfter) {
      this.extra += this.widthTotal;
      this.isBefore = this.isAfter = false;
    }
  }

  onResize({ screen, viewport } = {}) {
    if (screen) this.screen = screen;
    if (viewport) this.viewport = viewport;
    this.scale = this.screen.height / 1500;
    this.plane.scale.y = (this.viewport.height * (900 * this.scale)) / this.screen.height;
    this.plane.scale.x = (this.viewport.width * (700 * this.scale)) / this.screen.width;
    this.plane.program.uniforms.uPlaneSizes.value = [this.plane.scale.x, this.plane.scale.y];
    this.padding = 2;
    this.width = this.plane.scale.x + this.padding;
    this.widthTotal = this.width * this.length;
    this.x = this.width * this.index;
  }
}

class Gallery {
  constructor(container, opts = {}) {
    this.container = container;
    this.bend = opts.bend ?? 1;
    this.textColor = opts.textColor ?? "#ffffff";
    this.borderRadius = opts.borderRadius ?? 0.05;
    this.scrollSpeed = opts.scrollSpeed ?? 2;
    this.scroll = { ease: opts.scrollEase ?? 0.05, current: 0, target: 0, last: 0, position: 0 };
    this.onCheckDebounce = debounce(() => this.onCheck(), 200);

    this.renderer = new Renderer({ alpha: true, antialias: true, dpr: Math.min(window.devicePixelRatio || 1, 2) });
    this.gl = this.renderer.gl;
    this.gl.clearColor(0, 0, 0, 0);
    container.appendChild(this.gl.canvas);

    this.camera = new Camera(this.gl);
    this.camera.fov = 45;
    this.camera.position.z = 20;
    this.scene = new Transform();

    this.onResize();
    this.geometry = new Plane(this.gl, { heightSegments: 50, widthSegments: 100 });
    this.createMedias();
    this.addListeners();
    this.running = false;
  }

  createMedias() {
    // Doubled, as the original does, so the loop has something to wrap onto.
    const items = FEATURES.concat(FEATURES);
    this.medias = items.map((f, index) => new Media({
      geometry: this.geometry,
      gl: this.gl,
      canvas: drawCard(f),
      index,
      length: items.length,
      scene: this.scene,
      screen: this.screen,
      text: f.k,
      viewport: this.viewport,
      bend: this.bend,
      textColor: this.textColor,
      borderRadius: this.borderRadius,
      font: LABEL_FONT,
    }));
  }

  onResize() {
    this.screen = { width: this.container.clientWidth, height: this.container.clientHeight };
    this.renderer.setSize(this.screen.width, this.screen.height);
    this.camera.perspective({ aspect: this.screen.width / this.screen.height });
    const fov = (this.camera.fov * Math.PI) / 180;
    const height = 2 * Math.tan(fov / 2) * this.camera.position.z;
    this.viewport = { width: height * this.camera.aspect, height };
    if (this.medias) this.medias.forEach(m => m.onResize({ screen: this.screen, viewport: this.viewport }));
  }

  onCheck() {
    if (!this.medias || !this.medias[0]) return;
    const w = this.medias[0].width;
    const i = Math.round(Math.abs(this.scroll.target) / w);
    this.scroll.target = this.scroll.target < 0 ? -(w * i) : w * i;
  }

  /* Bound to the container, not to window. The original listens globally,
     which on a page like this one swallows the reader's own scrolling. */
  addListeners() {
    const el = this.container;
    const down = e => {
      this.isDown = true;
      this.scroll.position = this.scroll.current;
      this.start = e.touches ? e.touches[0].clientX : e.clientX;
    };
    const move = e => {
      if (!this.isDown) return;
      const x = e.touches ? e.touches[0].clientX : e.clientX;
      this.scroll.target = this.scroll.position + (this.start - x) * (this.scrollSpeed * 0.025);
    };
    const up = () => { this.isDown = false; this.onCheck(); };

    el.addEventListener("mousedown", down);
    el.addEventListener("mousemove", move);
    el.addEventListener("mouseup", up);
    el.addEventListener("mouseleave", up);
    el.addEventListener("touchstart", down, { passive: true });
    el.addEventListener("touchmove", move, { passive: true });
    el.addEventListener("touchend", up);

    el.addEventListener("keydown", e => {
      if (e.key === "ArrowRight") { e.preventDefault(); this.scroll.target += this.scrollSpeed * 5; this.onCheckDebounce(); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); this.scroll.target -= this.scrollSpeed * 5; this.onCheckDebounce(); }
      else if (e.key === "Home") { e.preventDefault(); this.scroll.target = 0; this.onCheckDebounce(); }
    });

    window.addEventListener("resize", debounce(() => this.onResize(), 150));
  }

  frame() {
    this.scroll.current = lerp(this.scroll.current, this.scroll.target, this.scroll.ease);
    const direction = this.scroll.current > this.scroll.last ? "right" : "left";
    this.medias.forEach(m => m.update(this.scroll, direction));
    this.renderer.render({ scene: this.scene, camera: this.camera });
    this.scroll.last = this.scroll.current;
  }

  start() {
    if (this.running) return;
    this.running = true;
    const tick = () => {
      if (!this.running) return;
      this.frame();
      this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  }

  stop() {
    this.running = false;
    if (this.raf) cancelAnimationFrame(this.raf);
  }
}

const host = document.getElementById("feature-gallery");
if (host) {
  const gallery = new Gallery(host, {
    bend: 1,
    textColor: "#ffffff",
    borderRadius: 0.05,
    scrollEase: 0.05,
    scrollSpeed: 2,
  });

  const reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduced) {
    gallery.frame();          // One frame, held; still draggable.
  } else if (window.IntersectionObserver) {
    new IntersectionObserver(e => (e[0].isIntersecting ? gallery.start() : gallery.stop()), { threshold: 0 })
      .observe(host);
  } else {
    gallery.start();
  }
  host.setAttribute("data-ready", "true");
}
