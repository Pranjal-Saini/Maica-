# Fonts

The wordmark is set in **Garet**. The font file is not in this repository —
Garet is licensed, and which licence applies (personal vs commercial) is a
decision for the product owner, not something to be settled by committing a
file found online.

To use it, drop the web font here:

    maica/web/static/fonts/Garet-Book.woff2
    maica/web/static/fonts/Garet-Heavy.woff2

`@font-face` in `templates/_brand.html` already points at those paths. Until
they exist the wordmark falls back to a geometric sans of similar proportion
(Century Gothic / Questrial / Futura), so nothing looks broken in the meantime.
