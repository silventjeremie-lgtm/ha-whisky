const assert = require("assert");
const path = require("path");

// Stub minimal : le fichier définit une classe extends HTMLElement au niveau
// module (jamais instanciée ici, seules les fonctions pures sont testées),
// donc seule la référence globale doit exister pour que le require() réussisse.
global.HTMLElement = class {};

const {
  escapeHtml, STATUS_ORDER, STATUS_DOT, statusBreakdown, statusSummary,
  ratingStars, metaLine, tileHTML, detailRows,
} = require(path.join(process.cwd(), "custom_components/whisky/whisky-card.js"));

// 1) escapeHtml — neutralise les caractères dangereux, laisse le reste intact
assert.strictEqual(escapeHtml(`<a href="x">O'Brien & Fils</a>`),
  "&lt;a href=&quot;x&quot;&gt;O&#39;Brien &amp; Fils&lt;/a&gt;");
assert.strictEqual(escapeHtml(null), "");
assert.strictEqual(escapeHtml(undefined), "");
assert.strictEqual(escapeHtml(16), "16");

// 2) statusBreakdown — compte par statut, "sealed" par défaut si absent/invalide
assert.deepStrictEqual(
  statusBreakdown([{ bottle_status: "sealed" }, { bottle_status: "opened" }, { bottle_status: "sealed" }, {}]),
  { sealed: 3, opened: 1, finished: 0 }
);
assert.deepStrictEqual(statusBreakdown([]), { sealed: 0, opened: 0, finished: 0 });
assert.deepStrictEqual(statusBreakdown(undefined), { sealed: 0, opened: 0, finished: 0 });
assert.deepStrictEqual(STATUS_ORDER, ["sealed", "opened", "finished"]);
assert.ok(STATUS_DOT.sealed && STATUS_DOT.opened && STATUS_DOT.finished);

// 3) statusSummary — résumé lisible, ordonné, pluriel correct, vide géré
assert.strictEqual(
  statusSummary([{ bottle_status: "sealed" }, { bottle_status: "sealed" }, { bottle_status: "opened" }]),
  `${STATUS_DOT.sealed} 2 scellées · ${STATUS_DOT.opened} 1 ouverte`
);
assert.strictEqual(statusSummary([]), "aucune bouteille");
assert.strictEqual(statusSummary(undefined), "aucune bouteille");

// 4) ratingStars — arrondi et bornes 0-5
assert.strictEqual(ratingStars(4), "★★★★☆");
assert.strictEqual(ratingStars(4.6), "★★★★★");
assert.strictEqual(ratingStars(0), "☆☆☆☆☆");
assert.strictEqual(ratingStars(undefined), "☆☆☆☆☆");
assert.strictEqual(ratingStars(7), "★★★★★"); // borné à 5
assert.strictEqual(ratingStars(-2), "☆☆☆☆☆"); // borné à 0

// 5) metaLine — assemble avec séparateur, ignore null/undefined/vide
assert.strictEqual(metaLine(["Islay", "Single Malt"]), "Islay · Single Malt");
assert.strictEqual(metaLine([null, "Single Malt", "", undefined]), "Single Malt");
assert.strictEqual(metaLine([null, undefined, ""]), "");

// 6) tileHTML — contient les infos clés, échappe le HTML, gère l'absence d'image
const w1 = {
  id: "w1", name: "Lagavulin 16", favorite: true, rating: 4,
  image_url: "https://example.com/lag16.jpg",
  whisky_meta: { region: "Islay", whisky_type: "Single Malt", age: "16", abv: 43, expression: "16 Year Old" },
  slots: [{ bottle_status: "sealed" }, { bottle_status: "opened" }],
};
const tile1 = tileHTML(w1);
assert.ok(tile1.includes('data-whisky-id="w1"'));
assert.ok(tile1.includes("★ Lagavulin 16"), "le favori doit préfixer le nom d'une étoile");
assert.ok(tile1.includes("Islay · Single Malt"));
assert.ok(tile1.includes("16 ans · 43 %"));
assert.ok(tile1.includes("16 Year Old"));
assert.ok(tile1.includes('<img class="wc-tile-img"'));
assert.ok(tile1.includes("★★★★☆"));

const w2 = { id: "w2", name: 'O"Malley <test>', slots: [] };
const tile2 = tileHTML(w2);
assert.ok(tile2.includes("wc-tile-img-placeholder"), "sans image_url, la tuile utilise le placeholder verre 🥃");
assert.ok(!tile2.includes("<test>"), "le nom doit être échappé");
assert.ok(tile2.includes("aucune bouteille"));

// 7) detailRows — groupe FORM_SECTIONS en lignes label/valeur, exclut "tasting"
// et les sections/valeurs vides ; lit whisky_meta puis les champs racine.
const w3 = {
  id: "w3", name: "Ardbeg 10", favorite: false,
  whisky_meta: {
    distillery: "Ardbeg", country: "Écosse", region: "Islay",
    whisky_type: "Single Malt", age: "10", abv: 46,
    tasting_notes: "Fumé et iodé", nose_notes: "Tourbe intense",
  },
  price: 45, currency: "EUR",
};
const rows3 = detailRows(w3);
assert.ok(rows3.every((s) => s.title !== "👃 Dégustation"), "la section dégustation ne doit jamais apparaître dans detailRows");
const identitySection = rows3.find((s) => s.title.includes("Identité"));
assert.ok(identitySection, "la section Identité doit être présente (distillery renseigné)");
assert.ok(identitySection.rows.some((r) => r.label === "Nom" && r.value === "Ardbeg 10"));
assert.ok(identitySection.rows.some((r) => r.label === "Distillerie" && r.value === "Ardbeg"));
assert.ok(!identitySection.rows.some((r) => r.label === "Embouteilleur indépendant"), "les champs vides sont omis");
const collectionSection = rows3.find((s) => s.title.includes("Collection personnelle"));
assert.ok(collectionSection.rows.some((r) => r.label === "Prix d'achat" && r.value === 45));

// Fiche quasi vide : aucune section ne doit apparaître (que des valeurs vides)
const w4 = { id: "w4", name: "" };
const rows4 = detailRows(w4);
assert.ok(Array.isArray(rows4));
assert.ok(rows4.every((s) => s.rows.length > 0), "aucune section vide ne doit être renvoyée");

console.log("commit7_card_list_detail.js : OK (" + 7 + " groupes d'assertions)");
