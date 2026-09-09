# Marketing site

Static HTML, no build step. Open `index.html` in a browser and it is exactly
what ships.

| File | |
|---|---|
| `index.html` | the landing page |
| `privacy.html`, `terms.html` | legal pages |
| `404.html` | Netlify serves this for unknown paths automatically |
| `style.css`, `app.js` | shared by every page, so the browser fetches each once |
| `robots.txt`, `sitemap.xml` | crawler directions |
| `_headers` | security headers and cache policy, applied by Netlify |
| `maica-logo.png` | the mark |
| `favicon.png` | 512px tab icon |
| `social-card.png` | 1200x630 link preview, drawn from the same traces as the hero |

## Why it is separate from the app

`maica.in` serves this from Netlify; `app.maica.in` serves the FastAPI app on
Render. Render spins a free service down after 15 minutes idle and takes about
a minute to wake — a visitor arriving at the domain must never see that. The
wake still happens, but only after someone has clicked through, by which point
they are committed.

It also means the app needs no marketing code: `/` on `app.maica.in` still goes
straight to `/login`, and this page links to it.

## Where the buttons point

One constant at the top of `app.js`:

```js
var APP_URL = "https://app.maica.in";
```

Every call to action is built from it, and it points at the app **root**, not
`/login` — the app already routes by session, so a signed-in visitor lands on
their dashboard instead of being asked to sign in again.

This page cannot tell whether you are signed in. The session cookie belongs to
`app.maica.in` and is `HttpOnly`, so script here can neither read it nor ask
across origins without opening CORS on the host that holds client evidence.
Letting the app decide costs nothing and adds no attack surface.

## Analytics

Off until you paste a token. In `app.js`:

```js
var ANALYTICS_TOKEN = "";
```

Fill it from Cloudflare Web Analytics (Web Analytics → your site → the `token`
in the snippet). It is cookieless and does not track across sites.

The consent notice stays hidden while the token is empty — asking permission to
collect nothing would be theatre. Once set, nothing loads until the visitor
chooses, and the choice is kept in `localStorage` rather than a cookie, so
declining does not itself create the thing that was declined.

## Deploying

Netlify, from GitHub, publish directory `site` (declared in `netlify.toml` at
the repo root). No build command.

**Not Vercel** — its Hobby plan bars "advertising the sale of a product or
service", which is what this page is. Cloudflare Pages and GitHub Pages have no
such restriction.

## Checking it

```
uv run python site/audit.py
```

Checks every internal link and in-page anchor, alt attributes, width/height on
images, and the length of each title and description. Exits non-zero on a
finding, so it can be wired into CI. There are no forms on this site, so there
is nothing to test there.

## What this page deliberately does not have

No customer logo strip and no testimonials. There are no customers yet, and
invented social proof is not worth having.
