# Vendored third-party assets

## `tailwind-play.js`

The Tailwind Play CDN build, taken from `https://cdn.tailwindcss.com`. MIT
licensed.

It is served from here rather than the CDN so that no page rendering a client's
ledger evidence executes a script fetched from a third party at load time, and
so `Content-Security-Policy` can be `script-src 'self'` instead of naming an
external host. A CDN compromise would otherwise have been arbitrary JavaScript
on every authenticated page.

**This is the Play build**: it compiles classes in the browser at runtime.
Tailwind's own guidance is that it is not intended for production — it is large
and it does work on every page load that a build step would do once. Replacing
it with a real Tailwind build (a compiled stylesheet, no runtime JS) is the
proper fix and needs a Node step in the Dockerfile. Vendoring is the security
half of that, done now; the performance half is still outstanding.

To refresh: `curl -L -o maica/web/static/vendor/tailwind-play.js https://cdn.tailwindcss.com`
