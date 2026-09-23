# Garet

The site's typeface. Two files belong here:

- `Garet-Book.woff2`  (weight 300, serves every weight up to 599)
- `Garet-Heavy.woff2` (serves 600 and above)

These are the two weights Type Forward gives away free, for personal and
commercial use, with credit to Type Forward in project documentation (given in
`site/README.md`). Get them from https://garet.typeforward.com/ — the download
is sent by email. Use only that source; mirror sites repackage fonts without
the licence.

Until both files are here the site falls back to Schibsted Grotesk and nothing
breaks. If the download contains only `.otf`/`.ttf`, convert with
`uv run --with fonttools --with brotli pyftsubset <file> --flavor=woff2 --output-file=<name>.woff2 --unicodes="*"`.
