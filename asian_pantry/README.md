# Asian Pantry

A mobile web app for cooking Asian food from an ordinary European supermarket.

Every recipe ingredient is mapped to a product you can actually pick up at Lidl,
Albert Heijn, Jumbo or REWE — with the Dutch or German name printed on the pack,
the package size it is sold in, the aisle it sits in, and a substitute for the
things that are not always on the shelf.

Built for the phone in your hand while you are standing in the world food aisle.

## Try it

```bash
python3 asian_pantry/build.py     # writes pantry.html at the repo root
```

Open `pantry.html` in a browser, or put it on a phone. There is no server, no
build toolchain and no network call at runtime — the whole app, including all
the data, is one 164 KB HTML file. It works offline, which matters in a
supermarket basement.

## What it does

**Pick your store.** Product names, package sizes, aisle names and the walking
order of the shopping list all follow the chain you select. Switching from Lidl
NL to REWE changes `Vitasia Ketjap Manis` to `Kikkoman Sojasauce süß` and
`Wereldkeuken` to `Weltküche`.

**Read a recipe.** Ingredients show the English name, the local product name,
the pack it comes in and the prep. A coloured edge marks pantry staples,
specialty items and things that only appear during a theme week. Servings scale
the quantities.

**Tap any ingredient for its shelf card.** A large, high-contrast card with the
local product name to show a member of staff, the package description, the
aisle, and — the part that actually saves the evening — what to use instead.
No mainstream European store sells Shaoxing wine, doubanjiang or holy basil, so
the app tells you what does the job: dry sherry, sambal plus miso, Italian basil
with an extra chilli.

**Build a shopping list.** "Add missing" adds only what is not already in your
kitchen. The list groups items by aisle in the order you walk them, converts
recipe amounts into whole packs (30 ml of soy sauce is still one 150 ml bottle),
and remembers which recipes drove each item.

**Search backwards.** The Kitchen tab takes what you already have and ranks
every recipe by how little else you need to buy.

## Editing the data

The data files are the point of this project; the app is a viewer for them.

```
asian_pantry/data/stores.json        chains, regions, aisle names, walking order
asian_pantry/data/ingredients.json   ingredients + per-store product mappings
asian_pantry/data/recipes.json       recipes
```

Adding a store is a data change, not a code change: add an entry to
`stores.json` with a `language` that has aisle labels, and every ingredient
immediately resolves through its regional default. Fill in `products.<store_id>`
on individual ingredients where you know the exact own-brand item.

An ingredient looks like this:

```json
{
  "id": "ketjap_manis",
  "en": "Sweet soy sauce",
  "category": "world_food",
  "role": "core",
  "note": "The most useful bottle in a Dutch supermarket.",
  "defaults": {
    "nl": { "name": "Ketjap manis", "package": "fles 500 ml", "size": 500, "unit": "ml" },
    "de": { "name": "Süße Sojasauce", "package": "Flasche 250 ml", "size": 250, "unit": "ml",
            "availability": "varies" }
  },
  "products": {
    "ah_nl": { "name": "Conimex Ketjap Manis", "package": "fles 500 ml", "size": 500, "unit": "ml",
               "shelf": "Wereldkeuken, blauw Conimex-blok, hoge donkere fles" }
  },
  "substitutes": [
    { "text": "3 tbsp light soy + 2 tbsp brown sugar, warmed until dissolved",
      "note": "Makes about 5 tbsp of a very close stand-in. This is the German workaround." }
  ]
}
```

`defaults` is the regional fallback — the typical own-brand item, keyed by
language. `products` overrides it with a store-specific match, and the shelf
card tells the user which of the two they are looking at. `role` separates
pantry staples from specialty items; `availability` (`staple` / `varies` /
`seasonal`) flags things like Lidl's Asia-week-only stock.

After editing, rebuild and run the checks:

```bash
python3 asian_pantry/build.py
python3 -m pytest tests/test_pantry_data.py
```

The tests catch the failure modes that are invisible in the UI: a recipe
pointing at an ingredient that does not exist, a product in an aisle the store
has no shelf position for, a pack size without a unit, or a not-always-stocked
ingredient with no substitute offered.

## How accurate is the product data?

It is a researched starting point, not a live feed. Supermarkets rotate ranges,
rename own-brand lines and change pack sizes constantly, and this data was
written from knowledge of these chains rather than scraped from their systems.

The app is built around that limitation rather than hiding it:

- The shelf card states whether a product is a store-specific match on file or
  the regional default name.
- Items known to be intermittent are flagged in the UI before you go shopping.
- Substitutes are given for everything that is not a permanent fixture, so a
  wrong product name costs you a moment, not the meal.

Treat a product name as a strong lead. The aisle, the local wording and the
substitute are what get you home with dinner.

## Layout

```
asian_pantry/
├── build.py                  inlines everything into one HTML file
├── data/                     the three JSON files above
└── src/
    ├── index.template.html   page shell with {{STYLES}} {{DATA}} {{APP}} slots
    ├── styles.css            design tokens, light and dark
    └── app.js                the whole app, vanilla JS, no framework
```

`build.py --fragment` emits the body content without the document wrapper, for
embedding the app in a host page.
