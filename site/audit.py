"""Static audit of the marketing site.

Checks every internal link and in-page anchor resolves, that images carry alt
text and explicit dimensions, and that each page's title and description are
present and a sensible length.

Run from the repo root:  uv run python site/audit.py
Exits non-zero when it finds something, so CI can call it.
"""

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

SITE = Path(__file__).parent
pages = sorted(SITE.glob("*.html"))
problems = []


class Scan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.imgs, self.ids, self.metas, self.title = [], [], set(), {}, None
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag == "img":
            self.imgs.append(a)
        if tag == "title":
            self._in_title = True
        if tag == "link" and a.get("rel") == "canonical":
            self.metas["canonical"] = a.get("href")
        if tag == "meta":
            if a.get("name") == "description":
                self.metas["description"] = a.get("content")
            if a.get("property"):
                self.metas[a["property"]] = a.get("content")
            if a.get("name", "").startswith("twitter:"):
                self.metas[a["name"]] = a.get("content")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and data.strip():
            self.title = data.strip()


scans = {}
for p in pages:
    s = Scan()
    s.feed(p.read_text(encoding="utf-8"))
    scans[p.name] = s

print("=== pages ===")
for name, s in scans.items():
    print(f"  {name}")
    for key, label in [
        ("title", "<title>"),
        ("description", "description"),
        ("canonical", "canonical"),
        ("og:title", "og:title"),
        ("og:image", "og:image"),
        ("twitter:card", "twitter:card"),
    ]:
        v = s.title if key == "title" else s.metas.get(key)
        if name == "404.html" and key in ("canonical", "og:title", "og:image", "twitter:card"):
            continue
        if not v:
            problems.append(f"{name}: missing {label}")
        elif key == "title" and len(v) > 65:
            problems.append(f"{name}: <title> is {len(v)} chars (aim <= 60)")
        elif key == "description" and not (110 <= len(v) <= 165):
            problems.append(f"{name}: description is {len(v)} chars (aim 120-160)")

print("\n=== images ===")
for name, s in scans.items():
    for img in s.imgs:
        src = img.get("src", "?")
        if "alt" not in img:
            problems.append(f"{name}: <img src={src}> has no alt attribute")
        elif img["alt"] == "" and img.get("aria-hidden") != "true":
            problems.append(f"{name}: decorative <img src={src}> lacks aria-hidden")
        if not (img.get("width") and img.get("height")):
            problems.append(f"{name}: <img src={src}> has no width/height (causes layout shift)")
    print(f"  {name}: {len(s.imgs)} images checked")

print("\n=== links ===")
external = set()
for name, s in scans.items():
    for href in s.links:
        if href.startswith(("http://", "https://")):
            external.add(href)
            continue
        if href.startswith("mailto:") or href == "#":
            continue
        if href.startswith("#"):
            if href[1:] not in s.ids:
                problems.append(f"{name}: anchor {href} has no matching id on the page")
            continue
        path, _, frag = href.partition("#")
        # '/' and '/dir/' both mean that directory's index.html
        if path in ("", "/") or path.endswith("/"):
            path = path + "index.html"
        target = SITE / path.lstrip("/")
        if not target.exists():
            problems.append(f"{name}: link {href} -> {target} does not exist")
        elif frag and target.suffix == ".html":
            if frag not in scans.get(target.name, Scan()).ids:
                problems.append(f"{name}: link {href} points at a missing id")
print(f"  internal links resolved; {len(external)} external targets:")
for e in sorted(external):
    print("   ", e)

# referenced assets that are not links
print("\n=== referenced assets ===")
for p in pages:
    for m in re.findall(r'(?:src|href)="(/[^"]+)"', p.read_text(encoding="utf-8")):
        if m.endswith((".css", ".js", ".png", ".xml", ".txt")):
            if not (SITE / m.lstrip("/")).exists():
                problems.append(f"{p.name}: asset {m} missing from site/")
print("  checked")

print("\n=== result ===")
if problems:
    for pr in problems:
        print("  PROBLEM:", pr)
    sys.exit(1)
print("  no problems found")
