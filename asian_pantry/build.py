#!/usr/bin/env python3
"""Build the Asian Pantry app into a single self-contained HTML file.

The app has no dependencies and no toolchain: this script inlines the CSS, the
JavaScript and the three JSON data files into one page that runs from a phone's
browser with no server and no network.

    python3 asian_pantry/build.py                 # -> pantry.html (standalone page)
    python3 asian_pantry/build.py --fragment -o x.html   # body-only, for embedding

The data files are the interesting part to edit; see asian_pantry/README.md.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
DATA = ROOT / "data"
SRC = ROOT / "src"

# Everything before this marker in the template is document head, the rest is body.
SPLIT = "<!-- head above / body below -->"

DOCUMENT = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="Cook Asian food from a European supermarket: every recipe ingredient mapped to a real product at Lidl, Albert Heijn, Jumbo or REWE.">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#e7eae1">
{head}
</head>
<body>
{body}
</body>
</html>
"""


def load_data() -> dict:
    """Read the three data files and check they refer to each other correctly."""
    stores = json.loads((DATA / "stores.json").read_text(encoding="utf-8"))
    ingredients = json.loads((DATA / "ingredients.json").read_text(encoding="utf-8"))
    recipes = json.loads((DATA / "recipes.json").read_text(encoding="utf-8"))

    known = {i["id"] for i in ingredients}
    for recipe in recipes:
        for item in recipe["ingredients"]:
            if item["id"] not in known:
                raise SystemExit(
                    f"{recipe['id']}: unknown ingredient '{item['id']}' — "
                    f"add it to data/ingredients.json"
                )

    return {"stores": stores, "ingredients": ingredients, "recipes": recipes}


def render(fragment: bool = False) -> str:
    data = load_data()
    template = (SRC / "index.template.html").read_text(encoding="utf-8")

    page = (
        template
        .replace("{{STYLES}}", (SRC / "styles.css").read_text(encoding="utf-8").strip())
        # </script> inside a JSON string would end the tag early; \\u003c keeps it inert.
        .replace("{{DATA}}", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c"))
        .replace("{{APP}}", (SRC / "app.js").read_text(encoding="utf-8").strip())
    )

    if fragment:
        return page

    if SPLIT not in page:
        raise SystemExit(f"src/index.template.html is missing the {SPLIT!r} marker")
    head, body = page.split(SPLIT, 1)
    return DOCUMENT.format(head=head.strip(), body=body.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-o", "--out", type=Path, default=REPO / "pantry.html", help="output file")
    parser.add_argument("--fragment", action="store_true", help="emit body content only, without the document wrapper")
    args = parser.parse_args()

    html = render(fragment=args.fragment)
    args.out.write_text(html, encoding="utf-8")
    print(f"wrote {args.out} ({len(html) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
