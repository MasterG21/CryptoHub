"""Integrity checks for the Asian Pantry recipe and supermarket data.

The app is entirely data-driven: a broken reference between recipes.json,
ingredients.json and stores.json shows up as a blank ingredient row or a
missing shopping-list entry rather than an exception, so these tests exist to
catch it at the point the data changes.
"""
import json
import sys
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "asian_pantry" / "data"
sys.path.insert(0, str(DATA.parent))

import build  # noqa: E402  (imported after the path is set up)

KNOWN_UNITS = {"g", "ml", "tbsp", "tsp", "piece", "clove", "cube", "handful"}
PACK_UNITS = {"g", "ml", "piece"}
ROLES = {"core", "specialty"}
AVAILABILITY = {"staple", "seasonal", "varies"}


@pytest.fixture(scope="module")
def stores():
    return json.loads((DATA / "stores.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ingredients():
    return json.loads((DATA / "ingredients.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def recipes():
    return json.loads((DATA / "recipes.json").read_text(encoding="utf-8"))


def products(ingredient):
    """Every product entry on an ingredient, store-specific and regional alike."""
    return list(ingredient.get("products", {}).values()) + list(ingredient.get("defaults", {}).values())


def test_ids_are_unique(ingredients, recipes):
    ing_ids = [i["id"] for i in ingredients]
    rec_ids = [r["id"] for r in recipes]
    assert len(ing_ids) == len(set(ing_ids))
    assert len(rec_ids) == len(set(rec_ids))


def test_every_recipe_ingredient_exists(ingredients, recipes):
    known = {i["id"] for i in ingredients}
    missing = {
        (r["id"], item["id"])
        for r in recipes
        for item in r["ingredients"]
        if item["id"] not in known
    }
    assert not missing


def test_substitutes_point_at_real_ingredients(ingredients):
    known = {i["id"] for i in ingredients}
    dangling = [
        (i["id"], sub["id"])
        for i in ingredients
        for sub in i.get("substitutes", [])
        if "id" in sub and sub["id"] not in known
    ]
    assert not dangling


def test_substitutes_say_something_useful(ingredients):
    """A substitute without a name or a note is a dead end in the shelf card."""
    for i in ingredients:
        for sub in i.get("substitutes", []):
            assert sub.get("id") or sub.get("text"), i["id"]
            assert sub.get("note"), f"{i['id']}: substitute needs a note explaining the swap"


def test_products_reference_real_stores(ingredients, stores):
    known = {s["id"] for s in stores["stores"]}
    unknown = {
        store_id
        for i in ingredients
        for store_id in i.get("products", {})
        if store_id not in known
    }
    assert not unknown


def test_every_ingredient_resolves_at_every_store(ingredients, stores):
    """The app falls back to a regional default, so no store may come up empty."""
    for ingredient in ingredients:
        for store in stores["stores"]:
            product = ingredient.get("products", {}).get(store["id"]) or ingredient.get("defaults", {}).get(
                store["language"]
            )
            assert product, f"{ingredient['id']} has no product at {store['id']}"
            assert product.get("name"), f"{ingredient['id']} at {store['id']} has no product name"
            assert product.get("package"), f"{ingredient['id']} at {store['id']} has no package description"


def test_aisles_are_known_and_walkable(ingredients, stores):
    """Every aisle an item can land in must exist in each store's walking order."""
    labels = stores["aisle_labels"]
    used = {i["category"] for i in ingredients}
    used |= {p["aisle"] for i in ingredients for p in products(i) if p.get("aisle")}

    assert used <= set(stores["default_aisle_order"])
    for store in stores["stores"]:
        order = set(store.get("aisle_order") or stores["default_aisle_order"])
        assert used <= order, f"{store['id']} has no shelf position for {used - order}"
        assert used <= set(labels[store["language"]]), f"missing {store['language']} aisle names"
    assert used <= set(labels["en"])


def test_pack_sizes_are_usable(ingredients):
    """Pack maths needs a size and a unit together, or neither."""
    for i in ingredients:
        for p in products(i):
            if p.get("size") is not None:
                assert p.get("unit") in PACK_UNITS, f"{i['id']}: bad pack unit {p.get('unit')!r}"
                assert p["size"] > 0, i["id"]
            else:
                assert "unit" not in p, f"{i['id']}: unit without a size"
            assert p.get("availability", "staple") in AVAILABILITY, i["id"]


def test_ingredient_shape(ingredients):
    for i in ingredients:
        assert i.get("en"), i["id"]
        assert i.get("role") in ROLES, i["id"]
        assert i.get("defaults"), f"{i['id']} needs a regional default for the fallback"


def test_recipe_shape(recipes):
    for r in recipes:
        assert r.get("title") and r.get("blurb") and r.get("cuisine")
        assert r["serves"] >= 1
        assert r["prep_min"] >= 0 and r["cook_min"] > 0
        assert 0 <= r.get("heat", 0) <= 3
        assert r["ingredients"], r["id"]
        assert len(r["steps"]) >= 3, f"{r['id']} needs real instructions"
        for item in r["ingredients"]:
            assert item["unit"] in KNOWN_UNITS, f"{r['id']}: unknown unit {item['unit']!r}"
            assert item["qty"] > 0, f"{r['id']}: {item['id']} has no quantity"


def test_recipes_are_cookable_from_the_selected_store(recipes, ingredients, stores):
    """A recipe whose ingredients cannot all be bought needs a stated substitute."""
    by_id = {i["id"]: i for i in ingredients}
    for r in recipes:
        for item in r["ingredients"]:
            ingredient = by_id[item["id"]]
            for store in stores["stores"]:
                product = ingredient.get("products", {}).get(store["id"]) or ingredient["defaults"].get(
                    store["language"]
                )
                if product.get("availability", "staple") == "staple":
                    continue
                assert ingredient.get("substitutes") or item.get("optional"), (
                    f"{r['id']} needs {ingredient['id']}, which is not always stocked at "
                    f"{store['id']} and has no substitute or optional flag"
                )


def test_build_produces_a_self_contained_page():
    html = build.render()
    assert html.startswith("<!doctype html>")
    assert "window.__DATA__" in html
    assert "</script>" not in html.split("window.__DATA__ = ", 1)[1].split(";</script>", 1)[0]
    # both themes must be defined, or the page renders one theme's text on the other's ground
    assert "prefers-color-scheme: dark" in html and '[data-theme="dark"]' in html
    # no external assets beyond the font stylesheet
    assert html.count("<script src=") == 0
    assert html.count("<link rel=\"stylesheet\"") == 1


def test_build_rejects_a_dangling_ingredient(tmp_path, monkeypatch):
    recipes = json.loads((DATA / "recipes.json").read_text(encoding="utf-8"))
    recipes[0]["ingredients"][0]["id"] = "unobtanium"
    broken = tmp_path / "data"
    broken.mkdir()
    for name in ("stores.json", "ingredients.json"):
        (broken / name).write_text((DATA / name).read_text(encoding="utf-8"), encoding="utf-8")
    (broken / "recipes.json").write_text(json.dumps(recipes), encoding="utf-8")

    monkeypatch.setattr(build, "DATA", broken)
    with pytest.raises(SystemExit, match="unobtanium"):
        build.load_data()
