# Marketing site

One static file. No build step, no dependencies, nothing to compile — open
`index.html` in a browser and it is exactly what ships.

It is deliberately separate from the app:

- `maica.in` / `www.maica.in` serve this page from a static host
- `app.maica.in` serves the FastAPI app on Render

That split means the landing page never waits on a cold start. Render spins a
free service down after 15 minutes idle and takes about a minute to wake; a
visitor arriving at `maica.in` must never see that. The wake still happens, but
only after someone has clicked **Get started** and is already committed.

It also means the app needs no marketing code: `/` on `app.maica.in` keeps
going straight to `/login`, and this page just links to it.

## Where the buttons point

One constant, near the bottom of `index.html`:

```js
var APP_URL = "https://app.maica.in";
```

Every **Get started** and **Sign in** link is built from it at load. Until
`app.maica.in` is pointed at Render, set this to the `onrender.com` host so the
buttons still work.

## Deploying

Any static host. **Not Vercel** — its Hobby plan bars "advertising the sale of
a product or service", which is what this page is; legitimate use there means
Pro. Cloudflare Pages, Netlify and GitHub Pages have no such restriction.

Point the host at this `site/` directory as the publish root. There is no build
command.

## Brand

Colours and the wordmark match the app's tokens (`--brand: #384fff`,
`--ink: #111310`, `--canvas: #e8eae2`), and the hero draws the same converging
traces as the sign-in panel, so the two read as one product.

`maica-logo.png` is a copy of the app's. The mark is white on an *opaque* black
square with no alpha channel, so `mix-blend-mode: screen` composites it onto a
dark surface — every place it appears on this page is dark. On a light surface
it would show its tile.

Garet is licensed and not committed, so the wordmark falls back to Questrial,
which has similar proportions. Drop the Garet files in and it picks them up.

## What this page deliberately does not have

No customer logo strip and no testimonials. There are no customers yet, and
invented social proof is the one pattern from the reference design worth
leaving behind.
