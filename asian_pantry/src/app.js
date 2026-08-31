/* Asian Pantry — mobile web app for cooking Asian food from European supermarkets.
   No build step, no framework: the data is inlined as window.__DATA__ by build.py. */
(function () {
  "use strict";

  var DB = window.__DATA__;
  var ING = {};
  DB.ingredients.forEach(function (i) { ING[i.id] = i; });
  var REC = {};
  DB.recipes.forEach(function (r) { REC[r.id] = r; });
  var STORES = {};
  DB.stores.stores.forEach(function (s) { STORES[s.id] = s; });

  /* ---------- state ---------- */

  var KEY = "asianpantry.v1";
  var S = defaults();

  function defaults() {
    return {
      store: "lidl_nl",
      pantry: DB.ingredients.filter(function (i) { return i.pantry_default; }).map(function (i) { return i.id; }),
      list: {},
      servings: {},
      localFirst: false
    };
  }

  function load() {
    try {
      var raw = localStorage.getItem(KEY);
      if (!raw) return;
      var saved = JSON.parse(raw);
      Object.keys(S).forEach(function (k) {
        if (saved[k] !== undefined && saved[k] !== null) S[k] = saved[k];
      });
      if (!STORES[S.store]) S.store = "lidl_nl";
      S.pantry = S.pantry.filter(function (id) { return ING[id]; });
    } catch (e) { /* private mode, blocked storage: run with defaults */ }
  }

  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) { /* not fatal */ }
  }

  /* ---------- helpers ---------- */

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function store() { return STORES[S.store]; }

  function aisleName(aisle, lang) {
    var set = DB.stores.aisle_labels[lang] || DB.stores.aisle_labels.en;
    return set[aisle] || aisle;
  }

  /* Resolve an ingredient to a product at the selected store.
     A store-specific entry is an exact match; otherwise fall back to the
     regional default, which is a typical own-brand item rather than a promise. */
  function productFor(ing, st) {
    st = st || store();
    var p = (ing.products || {})[st.id];
    var exact = !!p;
    if (!p) p = (ing.defaults || {})[st.language];
    if (!p) return null;
    return {
      name: p.name,
      pack: p.package || "",
      size: p.size || null,
      unit: p.unit || null,
      aisle: p.aisle || ing.category,
      availability: p.availability || "staple",
      shelf: p.shelf || null,
      exact: exact
    };
  }

  var UNIT_ML = { tbsp: 15, tsp: 5, ml: 1 };
  var UNIT_LABEL = { g: "g", ml: "ml", tbsp: "tbsp", tsp: "tsp", clove: "cloves", cube: "cubes", handful: "handful", piece: "" };

  function baseOf(qty, unit) {
    if (unit === "g") return { kind: "g", amount: qty };
    if (UNIT_ML[unit]) return { kind: "ml", amount: qty * UNIT_ML[unit] };
    return { kind: "count", amount: qty };
  }

  function fmtNum(n) {
    var r = Math.round(n * 100) / 100;
    if (Math.abs(r - Math.round(r)) < 0.005) return String(Math.round(r));
    if (Math.abs(r * 2 - Math.round(r * 2)) < 0.005) return String(Math.round(r * 2) / 2);
    return r.toFixed(1);
  }

  function fmtQty(qty, unit) {
    var label = UNIT_LABEL[unit] === undefined ? unit : UNIT_LABEL[unit];
    var n = fmtNum(qty);
    if (unit === "piece") return n + "×";
    if (unit === "clove" && qty === 1) label = "clove";
    if (unit === "cube" && qty === 1) label = "cube";
    return label ? n + " " + label : n;
  }

  function mult(recipe) {
    var want = S.servings[recipe.id] || recipe.serves;
    return want / recipe.serves;
  }

  function totalTime(r) { return (r.prep_min || 0) + (r.cook_min || 0); }

  function have(id) { return S.pantry.indexOf(id) !== -1; }

  function missingFor(recipe) {
    return recipe.ingredients.filter(function (it) {
      return !it.optional && !have(it.id);
    });
  }

  function required(recipe) {
    return recipe.ingredients.filter(function (it) { return !it.optional; });
  }

  /* ---------- shopping list ---------- */

  function listCount() {
    return Object.keys(S.list).filter(function (id) { return !S.list[id].done; }).length;
  }

  function addToList(id, need) {
    var e = S.list[id];
    if (!e) e = S.list[id] = { needs: [], done: false };
    if (need) {
      var dup = e.needs.some(function (n) {
        return n.r === need.r && n.qty === need.qty && n.unit === need.unit;
      });
      if (!dup) e.needs.push(need);
    }
    e.done = false;
  }

  function addRecipe(recipe, onlyMissing) {
    var m = mult(recipe);
    var added = 0;
    recipe.ingredients.forEach(function (it) {
      // "Add missing" mirrors missingFor(): what you must buy, optional extras excluded.
      if (onlyMissing && (have(it.id) || it.optional)) return;
      addToList(it.id, { r: recipe.id, qty: it.qty * m, unit: it.unit });
      added++;
    });
    save();
    return added;
  }

  function totalsFor(entry) {
    var t = { g: 0, ml: 0, count: 0 };
    entry.needs.forEach(function (n) {
      var b = baseOf(n.qty, n.unit);
      t[b.kind] += b.amount;
    });
    return t;
  }

  function totalsLabel(t) {
    var parts = [];
    if (t.g) parts.push(fmtNum(t.g) + " g");
    if (t.ml) parts.push(fmtNum(t.ml) + " ml");
    if (t.count) parts.push(fmtNum(t.count) + "×");
    return parts.join(" + ");
  }

  function packsFor(product, t) {
    if (!product || !product.size || !product.unit) return null;
    var need = (product.unit === "piece") ? t.count : (t.g + t.ml);
    if (!need) return null;
    return Math.max(1, Math.ceil(need / product.size));
  }

  /* ---------- package glyph ----------
     Shape is read out of the package description itself, so the drawing never
     claims more than the data says. It is a shelf cue, not a product photo. */

  function packShape(product) {
    var p = ((product && product.pack) || "").toLowerCase();
    if (/fles|flasche|bottle|spender|quetsch|knijp/.test(p)) return "bottle";
    if (/blik|dose|tin\b|can\b/.test(p)) return "can";
    if (/pot\b|potje|glas|jar|kuip|becher|streuer|m[uü]hle/.test(p)) return "jar";
    if (/schaal|schale|tray|bakje|punnet/.test(p)) return "tray";
    if (/bos|bund|netje|netz|net\b/.test(p)) return "bunch";
    if (/blok|block|st[uü]ck 250|doos|packung|pack\b|karton/.test(p)) return "box";
    if (/zak|beutel|bag/.test(p)) return "bag";
    return "box";
  }

  var SHAPES = {
    bottle: '<path d="M10 3h4v3.2l2.4 3.1V21H7.6V9.3L10 6.2V3z"/><path d="M7.6 12h8.8"/>',
    can: '<rect x="6" y="5" width="12" height="15" rx="1.4"/><path d="M6 8.4h12M6 16.6h12"/>',
    jar: '<path d="M8 3.6h8v2.2H8z"/><path d="M6.6 8.2c0-1.3 1-2.4 2.3-2.4h6.2c1.3 0 2.3 1.1 2.3 2.4V19a1.6 1.6 0 0 1-1.6 1.6H8.2A1.6 1.6 0 0 1 6.6 19V8.2z"/>',
    tray: '<path d="M4.4 8.6h15.2l-1.5 10.2a1.4 1.4 0 0 1-1.4 1.2H7.3a1.4 1.4 0 0 1-1.4-1.2L4.4 8.6z"/><path d="M3.4 8.6h17.2"/>',
    bunch: '<path d="M12 20.4V9"/><path d="M12 9c-3.6 0-5.6-2.2-5.6-5.4 3.4 0 5.6 2 5.6 5.4z"/><path d="M12 9c3.6 0 5.6-2.2 5.6-5.4-3.4 0-5.6 2-5.6 5.4z"/>',
    box: '<rect x="5" y="4" width="14" height="16.4" rx="1.2"/><path d="M5 9.2h14"/>',
    bag: '<path d="M6.4 7.6h11.2l1.2 12.2a.9.9 0 0 1-.9 1H6.1a.9.9 0 0 1-.9-1L6.4 7.6z"/><path d="M9.2 7.6V5.4c0-.9.7-1.6 1.6-1.6h2.4c.9 0 1.6.7 1.6 1.6v2.2"/>'
  };

  function glyph(product, cls) {
    var s = SHAPES[packShape(product)] || SHAPES.box;
    return '<svg class="' + (cls || "swatch") + '" viewBox="0 0 24 24" aria-hidden="true" ' +
      'style="fill:none;stroke:var(--ink-faint);stroke-width:1.3;stroke-linejoin:round">' + s + "</svg>";
  }

  /* ---------- shared fragments ---------- */

  var STYLE_LABEL = {
    stir_fry: "Stir-fry", curry: "Curry", noodles: "Noodles", rice: "Rice",
    soup: "Soup", oven: "Oven", fried: "Fried", grill: "Grill", sandwich: "Sandwich"
  };
  var PROTEIN_LABEL = {
    chicken: "Chicken", beef: "Beef", pork: "Pork", fish: "Fish",
    seafood: "Seafood", veg: "Vegetables", egg: "Egg"
  };
  var DIET_LABEL = {
    vegetarian: "Vegetarian", vegan: "Vegan", dairy_free: "Dairy-free",
    nut_free: "Nut-free", gluten_free_option: "GF option"
  };

  function heatDots(n) {
    var out = "";
    for (var i = 0; i < 3; i++) out += i < n ? "◆" : '<span>◆</span>';
    return '<span class="heat" title="Heat level ' + n + ' of 3">' + out + "</span>";
  }

  function availTag(product) {
    if (!product) return "";
    if (product.availability === "seasonal") return '<span class="tag tag--warn">Theme week only</span>';
    if (product.availability === "varies") return '<span class="tag tag--warn">Not always stocked</span>';
    return "";
  }

  function recipeCard(r) {
    var miss = missingFor(r).length;
    var pill = miss === 0
      ? '<span class="tag tag--have">Everything in stock</span>'
      : '<span class="tag tag--need">' + miss + " to buy</span>";
    return '<button class="rcard" data-go="#/r/' + r.id + '">' +
      '<span class="rcard__mark"><span class="rcard__time">' + totalTime(r) + '</span>' +
      '<span class="rcard__unit">min</span></span>' +
      '<span class="rcard__body">' +
      '<span class="rcard__title">' + esc(r.title) + "</span>" +
      '<span class="rcard__cuisine">' + esc(r.cuisine) + " · serves " + r.serves + "</span>" +
      '<span class="rcard__blurb">' + esc(r.blurb) + "</span>" +
      '<span class="rcard__foot">' + pill +
      '<span class="tag">' + esc(STYLE_LABEL[r.style] || r.style) + "</span>" +
      (r.heat ? heatDots(r.heat) : "") +
      "</span></span></button>";
  }

  /* ---------- view: recipes ---------- */

  var F = { q: "", time: 0, style: "", protein: "", diet: "" };

  function matches(r) {
    if (F.time && totalTime(r) > F.time) return false;
    if (F.style && r.style !== F.style) return false;
    if (F.protein && r.protein !== F.protein) return false;
    if (F.diet && (r.diet || []).indexOf(F.diet) === -1) return false;
    if (F.q) {
      var q = F.q.toLowerCase();
      var hay = [r.title, r.cuisine, r.blurb].join(" ").toLowerCase();
      var inIng = r.ingredients.some(function (it) {
        var i = ING[it.id];
        if (!i) return false;
        var p = productFor(i);
        return (i.en + " " + (i.aka || []).join(" ") + " " + (p ? p.name : "")).toLowerCase().indexOf(q) !== -1;
      });
      if (hay.indexOf(q) === -1 && !inIng) return false;
    }
    return true;
  }

  function chip(group, value, label) {
    var on = F[group] === value;
    return '<button class="chip" role="button" aria-pressed="' + on + '" data-filter="' + group +
      '" data-value="' + esc(String(value)) + '">' + esc(label) + "</button>";
  }

  function viewRecipes() {
    var list = DB.recipes.filter(matches);
    var active = F.q || F.time || F.style || F.protein || F.diet;

    var filters = [
      chip("time", 20, "≤ 20 min"),
      chip("time", 30, "≤ 30 min"),
      chip("style", "stir_fry", "Stir-fry"),
      chip("style", "curry", "Curry"),
      chip("style", "noodles", "Noodles"),
      chip("style", "rice", "Rice"),
      chip("style", "soup", "Soup"),
      chip("style", "oven", "Oven"),
      chip("protein", "chicken", "Chicken"),
      chip("protein", "pork", "Pork"),
      chip("protein", "beef", "Beef"),
      chip("protein", "fish", "Fish"),
      chip("protein", "veg", "Veg"),
      chip("diet", "vegetarian", "Vegetarian"),
      chip("diet", "vegan", "Vegan")
    ].join("");

    return '<section class="view">' +
      '<div class="search"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.4"/><path d="m16 16 4.5 4.5"/></svg>' +
      '<input type="search" id="q" placeholder="Search recipes or an ingredient" value="' + esc(F.q) + '" autocomplete="off"></div>' +
      '<div class="chips">' + filters +
      (active ? '<button class="chip chip--clear" data-action="clear-filters">Clear</button>' : "") +
      "</div>" +
      '<div class="section-head"><h2>' + list.length + " recipe" + (list.length === 1 ? "" : "s") + "</h2>" +
      '<span class="eyebrow">' + esc(store().name) + "</span></div>" +
      (list.length
        ? '<div class="recipes">' + list.map(recipeCard).join("") + "</div>"
        : '<div class="empty"><strong>Nothing matches</strong>' +
          "<span>Try clearing a filter, or search for an ingredient you already have.</span></div>") +
      "</section>";
  }

  /* ---------- view: recipe detail ---------- */

  function ingredientRow(it, m) {
    var ing = ING[it.id];
    var p = productFor(ing);
    var owned = have(it.id);
    var cls = "irow";
    if (owned) cls += " irow--have";
    else if (p && p.availability === "seasonal") cls += " irow--seasonal";
    else if (ing.role === "specialty") cls += " irow--specialty";

    var local = p ? p.name : null;
    var primary = S.localFirst && local ? local : ing.en;
    var secondary = S.localFirst && local ? ing.en : local;

    return '<button class="' + cls + '" data-shelf="' + it.id + '">' +
      '<span class="irow__main">' +
      '<span class="irow__en">' + esc(primary) + (it.optional ? ' <span class="tag">optional</span>' : "") + "</span>" +
      (secondary ? '<span class="irow__local">' + esc(secondary) + "</span>" : "") +
      (p && p.pack ? '<span class="irow__pack mono">' + esc(p.pack) + "</span>" : "") +
      (it.prep ? '<span class="irow__prep">' + esc(it.prep) + "</span>" : "") +
      "</span>" +
      '<span class="irow__qty">' + esc(fmtQty(it.qty * m, it.unit)) + "</span>" +
      "</button>";
  }

  function viewRecipe(id) {
    var r = REC[id];
    if (!r) return '<section class="view"><div class="empty"><strong>Recipe not found</strong></div></section>';
    var m = mult(r);
    var servings = S.servings[r.id] || r.serves;
    var miss = missingFor(r);
    var specials = r.ingredients.filter(function (it) {
      var p = productFor(ING[it.id]);
      return ING[it.id].role === "specialty" || (p && p.availability !== "staple");
    });

    var diet = (r.diet || []).map(function (d) {
      return '<span class="tag">' + esc(DIET_LABEL[d] || d) + "</span>";
    }).join("");

    return '<section class="view">' +
      '<button class="back" data-go="#/recipes">← All recipes</button>' +
      '<div class="detail__head">' +
      '<span class="eyebrow">' + esc(r.cuisine) + "</span>" +
      '<h1 class="detail__title">' + esc(r.title) + "</h1>" +
      '<p class="detail__blurb">' + esc(r.blurb) + "</p>" +
      '<div class="detail__meta">' +
      '<span class="tag">' + r.prep_min + " min prep</span>" +
      '<span class="tag">' + r.cook_min + " min cook</span>" +
      '<span class="tag">' + esc(STYLE_LABEL[r.style] || r.style) + "</span>" +
      '<span class="tag">' + esc(PROTEIN_LABEL[r.protein] || r.protein) + "</span>" +
      diet + (r.heat ? heatDots(r.heat) : "") +
      "</div></div>" +

      '<div class="card servings">' +
      '<span class="servings__label">Servings</span>' +
      '<span class="stepper">' +
      '<button data-serv="-1" aria-label="Fewer servings"' + (servings <= 1 ? " disabled" : "") + ">−</button>" +
      "<output>" + servings + "</output>" +
      '<button data-serv="1" aria-label="More servings"' + (servings >= 12 ? " disabled" : "") + ">+</button>" +
      "</span></div>" +

      '<div class="section-head"><h2>Ingredients</h2>' +
      '<span class="eyebrow">at ' + esc(store().name) + "</span></div>" +
      '<div class="card ilist">' + r.ingredients.map(function (it) { return ingredientRow(it, m); }).join("") + "</div>" +

      (specials.length
        ? '<div class="notice"><svg viewBox="0 0 24 24"><path d="M12 8.4v4.8M12 16.6h.01"/>' +
          '<path d="M10.3 4.2 2.6 18a1.9 1.9 0 0 0 1.7 2.9h15.4a1.9 1.9 0 0 0 1.7-2.9L13.7 4.2a1.9 1.9 0 0 0-3.4 0z"/></svg>' +
          "<span><b>" + specials.length + (specials.length === 1 ? " item is" : " items are") +
          " not a permanent fixture</b> at " + esc(store().name) +
          ". Tap any ingredient for the substitute that works with what is always on the shelf.</span></div>"
        : "") +

      '<div class="btnrow">' +
      '<button class="btn btn--accent" data-add="' + r.id + '" data-missing="1"' + (miss.length ? "" : " disabled") + ">" +
      (miss.length ? "Add " + miss.length + " missing" : "Nothing to buy") + "</button>" +
      '<button class="btn btn--ghost" data-add="' + r.id + '">Add all</button>' +
      "</div>" +

      '<div class="section-head"><h2>Method</h2></div>' +
      (servings !== r.serves
        ? '<div class="notice"><svg viewBox="0 0 24 24"><path d="M12 8.4v4.8M12 16.6h.01"/>' +
          '<path d="M10.3 4.2 2.6 18a1.9 1.9 0 0 0 1.7 2.9h15.4a1.9 1.9 0 0 0 1.7-2.9L13.7 4.2a1.9 1.9 0 0 0-3.4 0z"/></svg>' +
          "<span>The ingredient list above is scaled to " + servings + ". Amounts written into the steps below " +
          "still read for " + r.serves + " — scale them by " + fmtNum(m) + "× as you go.</span></div>"
        : "") +
      '<ol class="steps">' + r.steps.map(function (s) {
        return '<li class="step"><span class="step__n"></span><p>' + esc(s) + "</p></li>";
      }).join("") + "</ol>" +

      (r.tips && r.tips.length
        ? '<div class="section-head"><h2>Worth knowing</h2></div><ul class="card tips">' +
          r.tips.map(function (t) { return "<li>" + esc(t) + "</li>"; }).join("") + "</ul>"
        : "") +
      "</section>";
  }

  /* ---------- view: kitchen (reverse search) ---------- */

  var kq = "";

  function viewKitchen() {
    var picked = S.pantry.map(function (id) { return ING[id]; }).filter(Boolean);
    var q = kq.toLowerCase();
    var pool = DB.ingredients.filter(function (i) {
      if (have(i.id)) return false;
      if (!q) return false;
      return (i.en + " " + (i.aka || []).join(" ") + " " +
        Object.keys(i.defaults || {}).map(function (k) { return i.defaults[k].name; }).join(" ")
      ).toLowerCase().indexOf(q) !== -1;
    }).slice(0, 20);

    var ranked = DB.recipes.map(function (r) {
      var req = required(r);
      var miss = missingFor(r);
      return { r: r, miss: miss.length, req: req.length, pct: Math.round(((req.length - miss.length) / req.length) * 100) };
    }).sort(function (a, b) {
      return a.miss - b.miss || b.pct - a.pct || totalTime(a.r) - totalTime(b.r);
    }).slice(0, 12);

    return '<section class="view">' +
      '<div class="section-head"><h2>What’s in my kitchen</h2></div>' +
      '<p class="detail__blurb">Tick what you already have. Recipes reorder by how little else you need to buy.</p>' +

      '<div class="search"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.4"/><path d="m16 16 4.5 4.5"/></svg>' +
      '<input type="search" id="kq" placeholder="Add an ingredient you have" value="' + esc(kq) + '" autocomplete="off"></div>' +

      (pool.length
        ? '<div class="pgrid">' + pool.map(function (i) {
            return '<button class="pchip" aria-pressed="false" data-pantry="' + i.id + '">+ ' + esc(i.en) + "</button>";
          }).join("") + "</div>"
        : (kq ? '<p class="detail__blurb">Nothing matching “' + esc(kq) + "” — it may already be ticked below.</p>" : "")) +

      '<div class="section-head"><h2>In your kitchen</h2>' +
      '<button class="back" data-action="reset-pantry">Reset</button></div>' +
      (picked.length
        ? '<div class="pgrid">' + picked.map(function (i) {
            return '<button class="pchip" aria-pressed="true" data-pantry="' + i.id + '">' + esc(i.en) + " ×</button>";
          }).join("") + "</div>"
        : '<div class="empty"><strong>Nothing ticked</strong><span>Search above to add what you have.</span></div>') +

      '<div class="section-head"><h2>Cook this</h2><span class="eyebrow">fewest extras first</span></div>' +
      '<div class="recipes">' + ranked.map(function (x) {
        return '<button class="rcard" data-go="#/r/' + x.r.id + '">' +
          '<span class="rcard__mark"><span class="rcard__time">' + x.miss + '</span>' +
          '<span class="rcard__unit">to buy</span></span>' +
          '<span class="rcard__body">' +
          '<span class="rcard__title">' + esc(x.r.title) + "</span>" +
          '<span class="rcard__cuisine">' + esc(x.r.cuisine) + " · " + totalTime(x.r) + " min</span>" +
          '<span class="match"><span class="match__bar"><span class="match__fill" style="width:' + x.pct + '%"></span></span>' +
          '<span class="rcard__cuisine">' + (x.req - x.miss) + "/" + x.req + "</span></span>" +
          "</span></button>";
      }).join("") + "</div></section>";
  }

  /* ---------- view: shopping list ---------- */

  function viewList() {
    var ids = Object.keys(S.list);
    if (!ids.length) {
      return '<section class="view"><div class="section-head"><h2>Shopping list</h2></div>' +
        '<div class="empty"><strong>Your list is empty</strong>' +
        "<span>Open a recipe and add what you are missing. Items land here sorted by the aisle you walk past first.</span>" +
        '<button class="btn btn--ghost btn--sm" data-go="#/recipes" style="margin:8px auto 0">Browse recipes</button></div></section>';
    }

    var st = store();
    var order = st.aisle_order || DB.stores.default_aisle_order;
    var groups = {};
    ids.forEach(function (id) {
      var ing = ING[id];
      if (!ing) return;
      var p = productFor(ing);
      var a = p ? p.aisle : ing.category;
      (groups[a] = groups[a] || []).push({ id: id, ing: ing, p: p, e: S.list[id] });
    });

    var done = ids.filter(function (id) { return S.list[id].done; }).length;
    var pos = 0;

    var body = order.filter(function (a) { return groups[a]; }).map(function (a) {
      pos++;
      var items = groups[a].sort(function (x, y) { return x.ing.en.localeCompare(y.ing.en); });
      return '<div class="card aisle">' +
        '<div class="aisle__rail"><span class="aisle__n">' + pos + "</span></div>" +
        '<div class="aisle__body">' +
        '<div class="aisle__name">' + esc(aisleName(a, st.language)) +
        "<em>" + esc(aisleName(a, "en")) + "</em></div>" +
        items.map(function (x) {
          var t = totalsFor(x.e);
          var packs = packsFor(x.p, t);
          var why = x.e.needs.map(function (n) { return REC[n.r] ? REC[n.r].title : null; })
            .filter(function (v, i, arr) { return v && arr.indexOf(v) === i; });
          var buy = packs
            ? packs + " × " + esc(x.p.pack)
            : (x.p && x.p.pack ? esc(x.p.pack) : "1 pack");
          return '<div class="litem' + (x.e.done ? " litem--done" : "") + '">' +
            '<button class="litem__box" data-check="' + x.id + '" aria-label="Mark ' + esc(x.ing.en) + ' as picked up">' +
            '<svg viewBox="0 0 24 24"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg></button>' +
            '<button class="litem__main" data-shelf="' + x.id + '" style="text-align:left">' +
            '<span class="irow__en">' + esc(x.p ? x.p.name : x.ing.en) + "</span>" +
            '<span class="irow__local">' + esc(x.ing.en) + "</span>" +
            '<span class="irow__pack mono">' + buy + (totalsLabel(t) ? " · need " + totalsLabel(t) : "") + "</span>" +
            (why.length ? '<span class="litem__why">for ' + esc(why.join(", ")) + "</span>" : "") +
            "</button>" +
            '<button class="litem__x" data-remove="' + x.id + '" aria-label="Remove ' + esc(x.ing.en) + '">×</button>' +
            "</div>";
        }).join("") +
        "</div></div>";
    }).join("");

    return '<section class="view">' +
      '<div class="section-head"><h2>Shopping list</h2>' +
      '<span class="eyebrow">' + (ids.length - done) + " left · " + esc(st.name) + "</span></div>" +
      '<p class="detail__blurb">Grouped in the order you walk the aisles. Numbers are your route, not a priority.</p>' +
      body +
      '<div class="btnrow">' +
      '<button class="btn btn--ghost" data-action="clear-done"' + (done ? "" : " disabled") + ">Clear picked up</button>" +
      '<button class="btn btn--ghost" data-action="clear-list">Empty list</button>' +
      "</div></section>";
  }

  /* ---------- view: store ---------- */

  function viewStore() {
    var byRegion = {};
    DB.stores.stores.forEach(function (s) { (byRegion[s.region] = byRegion[s.region] || []).push(s); });

    var blocks = DB.stores.regions.map(function (reg) {
      var list = byRegion[reg.code] || [];
      return '<div class="section-head"><h2>' + esc(reg.name) + "</h2>" +
        '<span class="eyebrow">' + esc(reg.language_name) + " labels</span></div>" +
        '<div class="card storelist">' + list.map(function (s) {
          var on = s.id === S.store;
          return '<button class="storeopt" aria-pressed="' + on + '" data-store="' + s.id + '">' +
            '<span class="setrow__label"><span class="storeopt__name">' + esc(s.name) + "</span>" +
            '<span class="storeopt__meta">' + esc(s.kind) + " · " + esc(s.asian_range) + "</span></span>" +
            '<svg class="storeopt__tick" viewBox="0 0 24 24"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>' +
            "</button>";
        }).join("") + "</div>";
    }).join("");

    var st = store();

    return '<section class="view">' +
      '<div class="section-head"><h2>Your store</h2></div>' +
      '<p class="detail__blurb">Every product name, package size and aisle in the app follows this choice.</p>' +
      blocks +
      '<div class="card prose"><p><b>' + esc(st.name) + " · " + esc(st.region) + "</b></p><p>" + esc(st.note) + "</p></div>" +

      '<div class="section-head"><h2>Display</h2></div>' +
      '<div class="card">' +
      '<div class="setrow"><span class="setrow__label"><b>Local name first</b>' +
      "<span>Show the " + esc(st.language === "nl" ? "Dutch" : "German") + " product name above the English one</span></span>" +
      '<button class="toggle" role="switch" aria-checked="' + S.localFirst + '" aria-pressed="' + S.localFirst +
      '" data-action="toggle-local"><span class="sr">Local name first</span></button></div>' +
      "</div>" +

      '<div class="section-head"><h2>About the product data</h2></div>' +
      '<div class="card prose">' +
      "<p>Supermarkets rotate their ranges, rename own-brand lines and change pack sizes. Treat every product name here as " +
      "<b>a strong lead, not a guarantee</b> — the aisle, the local wording and the substitute are what get you home with dinner.</p>" +
      "<p>Where a store-specific product is on file, the shelf card says so. Otherwise you get the typical " +
      esc(st.language === "nl" ? "Dutch" : "German") + " product name for that item, which is what you would show a member of staff anyway.</p>" +
      "<p>Nothing you tick, list or pick is sent anywhere. It is saved in this browser only.</p>" +
      "</div></section>";
  }

  /* ---------- shelf card sheet ---------- */

  var sheetFor = null;

  function renderSheet() {
    var host = document.getElementById("sheet");
    if (!sheetFor) { host.innerHTML = ""; return; }
    var ing = ING[sheetFor];
    var p = productFor(ing);
    var st = store();
    var inList = !!S.list[ing.id];

    var subs = (ing.substitutes || []).map(function (s) {
      var name = s.text;
      if (s.id && ING[s.id]) {
        var sp = productFor(ING[s.id]);
        name = ING[s.id].en + (sp ? " — " + sp.name : "");
      }
      return '<div class="sub"><b>' + esc(name || "") + "</b>" +
        (s.note ? "<span>" + esc(s.note) + "</span>" : "") + "</div>";
    }).join("");

    host.innerHTML = '<div class="scrim" data-action="close-sheet">' +
      '<div class="sheet" role="dialog" aria-modal="true" aria-label="Shelf card for ' + esc(ing.en) + '">' +
      '<div class="sheet__head">' +
      glyph(p, "swatch") +
      '<div style="min-width:0">' +
      '<span class="eyebrow">' + esc(ing.en) + "</span>" +
      '<div class="irow__pack mono">' + esc(aisleName(p ? p.aisle : ing.category, "en")) + " · " + esc(st.name) + "</div>" +
      "</div>" +
      '<button class="sheet__x" data-action="close-sheet" aria-label="Close">×</button>' +
      "</div>" +

      (p
        ? '<div class="shelfcard">' +
          '<div class="eyebrow">Ask for / look for</div>' +
          '<div class="shelfcard__local">' + esc(p.name) + "</div>" +
          '<div class="shelfcard__pack">' + esc(p.pack) + "</div>" +
          '<div class="detail__meta" style="margin-top:6px">' +
          '<span class="tag">' + esc(aisleName(p.aisle, st.language)) + "</span>" +
          (ing.role === "specialty" ? '<span class="tag tag--warn">Specialty</span>' : '<span class="tag tag--have">Pantry staple</span>') +
          availTag(p) + "</div>" +
          (p.shelf ? '<div class="shelfcard__where">' + esc(p.shelf) + "</div>" : "") +
          (p.exact ? "" : '<div class="shelfcard__where"><b>No store-specific match on file.</b> This is the typical ' +
            esc(st.language === "nl" ? "Dutch" : "German") + " name for it — show it to staff or scan the aisle above.</div>") +
          "</div>"
        : '<div class="shelfcard"><div class="shelfcard__local">' + esc(ing.en) + "</div>" +
          '<div class="shelfcard__where">Not mapped at this store yet. Try the substitutes below.</div></div>') +

      (ing.note ? '<div class="sheet__section"><h3>Why it matters</h3><p class="detail__blurb">' + esc(ing.note) + "</p></div>" : "") +
      (subs ? '<div class="sheet__section"><h3>If you can’t find it</h3>' + subs + "</div>" : "") +

      '<div class="sheet__section"><div class="btnrow">' +
      '<button class="btn' + (have(ing.id) ? " btn--ghost" : " btn--ghost") + '" data-pantry="' + ing.id + '">' +
      (have(ing.id) ? "In kitchen ✓" : "I have this") + "</button>" +
      '<button class="btn btn--accent" data-listadd="' + ing.id + '">' + (inList ? "On the list ✓" : "Add to list") + "</button>" +
      "</div></div></div></div>";
  }

  /* ---------- toast ---------- */

  var toastTimer = null;
  function toast(msg) {
    var host = document.getElementById("toast");
    host.innerHTML = '<div class="toast">' + esc(msg) + "</div>";
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { host.innerHTML = ""; }, 2200);
  }

  /* ---------- shell ---------- */

  var TABS = [
    { hash: "#/recipes", label: "Recipes", icon: '<path d="M4 5.5h16M4 12h16M4 18.5h10"/>' },
    { hash: "#/kitchen", label: "Kitchen", icon: '<path d="M5 9.5h14l-1.1 10a1.6 1.6 0 0 1-1.6 1.4H7.7a1.6 1.6 0 0 1-1.6-1.4L5 9.5z"/><path d="M8.5 9.5V6.2A3.2 3.2 0 0 1 11.7 3h.6a3.2 3.2 0 0 1 3.2 3.2v3.3"/>' },
    { hash: "#/list", label: "List", icon: '<path d="M8.5 6.5h11M8.5 12h11M8.5 17.5h11M4.5 6.5h.01M4.5 12h.01M4.5 17.5h.01"/>' },
    { hash: "#/store", label: "Store", icon: '<path d="M4 9.2 5.4 4.5h13.2L20 9.2M4 9.2h16M4 9.2a2.4 2.4 0 0 0 4 1.6 2.4 2.4 0 0 0 4 0 2.4 2.4 0 0 0 4 0 2.4 2.4 0 0 0 4-1.6M5.8 11.6V20h12.4v-8.4"/>' }
  ];

  function renderTabs(route) {
    var n = listCount();
    return TABS.map(function (t) {
      var on = route.indexOf(t.hash) === 0 || (t.hash === "#/recipes" && route.indexOf("#/r/") === 0);
      return '<button class="tab" data-go="' + t.hash + '"' + (on ? ' aria-current="page"' : "") + ">" +
        '<svg viewBox="0 0 24 24">' + t.icon + "</svg>" + t.label +
        (t.hash === "#/list" && n ? '<span class="tab__count">' + n + "</span>" : "") +
        "</button>";
    }).join("");
  }

  function route() {
    var h = location.hash || "#/recipes";
    if (h.indexOf("#/r/") === 0) return h;
    if (["#/recipes", "#/kitchen", "#/list", "#/store"].indexOf(h) === -1) return "#/recipes";
    return h;
  }

  function render(keepScroll) {
    var r = route();
    var y = window.scrollY;
    var main = document.getElementById("main");
    if (r.indexOf("#/r/") === 0) main.innerHTML = viewRecipe(r.slice(4));
    else if (r === "#/kitchen") main.innerHTML = viewKitchen();
    else if (r === "#/list") main.innerHTML = viewList();
    else if (r === "#/store") main.innerHTML = viewStore();
    else main.innerHTML = viewRecipes();

    document.getElementById("tabs").innerHTML = renderTabs(r);
    document.getElementById("store-btn").innerHTML =
      "Shopping at <b>" + esc(store().name) + "</b> · " + esc(store().region);
    renderSheet();
    if (keepScroll) window.scrollTo(0, y);
    else window.scrollTo(0, 0);
  }

  /* ---------- events ---------- */

  document.addEventListener("click", function (ev) {
    var el = ev.target.closest("[data-go],[data-filter],[data-action],[data-shelf],[data-serv],[data-add],[data-pantry],[data-store],[data-check],[data-remove],[data-listadd]");
    if (!el) return;

    var d = el.dataset;

    if (d.go) { location.hash = d.go; return; }

    if (d.filter) {
      var val = d.filter === "time" ? Number(d.value) : d.value;
      F[d.filter] = F[d.filter] === val ? (d.filter === "time" ? 0 : "") : val;
      render(true); return;
    }

    if (d.shelf) { sheetFor = d.shelf; renderSheet(); return; }

    if (d.serv) {
      var id = route().slice(4);
      var rec = REC[id];
      if (!rec) return;
      var cur = S.servings[id] || rec.serves;
      var next = Math.min(12, Math.max(1, cur + Number(d.serv)));
      S.servings[id] = next; save(); render(true); return;
    }

    if (d.add) {
      var rc = REC[d.add];
      var n = addRecipe(rc, d.missing === "1");
      toast(n + " item" + (n === 1 ? "" : "s") + " added to your list");
      render(true); return;
    }

    if (d.pantry) {
      var i = S.pantry.indexOf(d.pantry);
      if (i === -1) S.pantry.push(d.pantry); else S.pantry.splice(i, 1);
      save(); render(true); return;
    }

    if (d.listadd) {
      if (S.list[d.listadd]) { delete S.list[d.listadd]; toast("Removed from list"); }
      else { addToList(d.listadd, null); toast("Added to list"); }
      save(); render(true); return;
    }

    if (d.store) {
      S.store = d.store; save();
      toast("Now shopping at " + STORES[d.store].name);
      render(true); return;
    }

    if (d.check) {
      var e = S.list[d.check];
      if (e) { e.done = !e.done; save(); render(true); }
      return;
    }

    if (d.remove) { delete S.list[d.remove]; save(); render(true); return; }

    switch (d.action) {
      case "clear-filters": F = { q: "", time: 0, style: "", protein: "", diet: "" }; render(true); break;
      case "close-sheet":
        if (ev.target.closest(".sheet") && !ev.target.closest("[data-action='close-sheet']")) return;
        sheetFor = null; renderSheet(); break;
      case "toggle-local": S.localFirst = !S.localFirst; save(); render(true); break;
      case "reset-pantry": S.pantry = defaults().pantry; save(); toast("Kitchen reset to basics"); render(true); break;
      case "clear-done":
        Object.keys(S.list).forEach(function (k) { if (S.list[k].done) delete S.list[k]; });
        save(); render(true); break;
      case "clear-list": S.list = {}; save(); render(true); break;
    }
  });

  document.addEventListener("input", function (ev) {
    if (ev.target.id === "q") { F.q = ev.target.value; redrawKeepingFocus("q"); }
    if (ev.target.id === "kq") { kq = ev.target.value; redrawKeepingFocus("kq"); }
  });

  function redrawKeepingFocus(id) {
    var el = document.getElementById(id);
    var pos = el ? el.selectionStart : null;
    render(true);
    var next = document.getElementById(id);
    if (next) { next.focus(); try { next.setSelectionRange(pos, pos); } catch (e) { /* search inputs */ } }
  }

  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape" && sheetFor) { sheetFor = null; renderSheet(); }
  });

  window.addEventListener("hashchange", function () { sheetFor = null; render(false); });

  load();
  render(false);
})();
