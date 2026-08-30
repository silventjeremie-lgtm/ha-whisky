const assert = require("assert");
const path = require("path");

global.HTMLElement = class {};

const {
  matchesQuery, matchesStatusFilter, filterWhiskies, breakdownJS,
  computeStats, topBreakdown,
} = require(path.join(process.cwd(), "custom_components/whisky/whisky-card.js"));

// Jeu de données de test : 3 fiches, plusieurs exemplaires par fiche.
const wLagavulin = {
  id: "w1", name: "Lagavulin 16 Years Old", favorite: true, price: 60, current_value: 75,
  whisky_meta: { distillery: "Lagavulin", region: "Islay", country: "Écosse", whisky_type: "Single Malt", age: "16", peated: true },
  slots: [{ bottle_status: "sealed" }, { bottle_status: "opened" }],
};
const wArdbeg = {
  id: "w2", name: "Ardbeg 10", favorite: false, price: 45,
  whisky_meta: { distillery: "Ardbeg", region: "Islay", country: "Écosse", whisky_type: "Single Malt", age: "10", peated: true },
  slots: [{ bottle_status: "finished" }],
};
const wMakers = {
  id: "w3", name: "Maker's Mark", favorite: false, current_value: 30,
  whisky_meta: { distillery: "Maker's Mark", region: "Kentucky", country: "USA", whisky_type: "Bourbon", peated: false },
  slots: [{ bottle_status: "sealed" }, { bottle_status: "sealed" }],
};
const all = [wLagavulin, wArdbeg, wMakers];

// 1) matchesQuery — insensible à la casse, cherche dans nom/distillerie/région/pays
assert.strictEqual(matchesQuery(wLagavulin, "lagavulin"), true);
assert.strictEqual(matchesQuery(wLagavulin, "ISLAY"), true);
assert.strictEqual(matchesQuery(wLagavulin, "bourbon"), false);
assert.strictEqual(matchesQuery(wLagavulin, ""), true);
assert.strictEqual(matchesQuery(wLagavulin, "   "), true);
assert.strictEqual(matchesQuery(wMakers, "maker"), true);

// 2) matchesStatusFilter — vrai si au moins un exemplaire a ce statut
assert.strictEqual(matchesStatusFilter(wLagavulin, "opened"), true);
assert.strictEqual(matchesStatusFilter(wLagavulin, "finished"), false);
assert.strictEqual(matchesStatusFilter(wLagavulin, ""), true);
assert.strictEqual(matchesStatusFilter(wLagavulin, undefined), true);

// 3) filterWhiskies — combine tous les filtres (ET logique)
assert.deepStrictEqual(filterWhiskies(all, {}).map((w) => w.id), ["w1", "w2", "w3"]);
assert.deepStrictEqual(filterWhiskies(all, { favorite: true }).map((w) => w.id), ["w1"]);
assert.deepStrictEqual(filterWhiskies(all, { whisky_type: "Single Malt" }).map((w) => w.id), ["w1", "w2"]);
assert.deepStrictEqual(filterWhiskies(all, { status: "finished" }).map((w) => w.id), ["w2"]);
assert.deepStrictEqual(filterWhiskies(all, { q: "islay" }).map((w) => w.id), ["w1", "w2"]);
assert.deepStrictEqual(
  filterWhiskies(all, { whisky_type: "Single Malt", status: "sealed" }).map((w) => w.id),
  ["w1"],
  "Ardbeg n'a qu'un exemplaire 'finished', donc exclu du filtre statut=sealed"
);
assert.deepStrictEqual(filterWhiskies(all, { q: "islay", favorite: true }).map((w) => w.id), ["w1"]);

// 4) breakdownJS — compte par nombre d'EXEMPLAIRES (pas par fiche), trié décroissant
const byType = breakdownJS(all, (w) => (w.whisky_meta || {}).whisky_type);
assert.deepStrictEqual(byType, [["Single Malt", 3], ["Bourbon", 2]]);
// Lagavulin (2 slots) + Ardbeg (1 slot) = 3 pour Single Malt ; Maker's Mark (2 slots) = 2 pour Bourbon.

// 5) computeStats — miroir des définitions de sensor.py
const stats = computeStats(all);
assert.strictEqual(stats.total, 5, "5 exemplaires physiques au total (2+1+2)");
assert.strictEqual(stats.references, 3);
assert.strictEqual(stats.sealed, 3);
assert.strictEqual(stats.opened, 1);
assert.strictEqual(stats.finished, 1);
assert.strictEqual(stats.distilleries, 3);
// Valeur = prix unitaire × nombre d'exemplaires NON "finished" (miroir _collection_value) :
// Lagavulin (unit=75, 2 exemplaires sealed+opened) = 150 ; Ardbeg (unit=45, 0 exemplaire
// non-finished, son seul exemplaire est "finished") = 0 ; Maker's Mark (unit=30, 2 sealed) = 60.
assert.strictEqual(stats.collectionValue, 150 + 0 + 60, "les bouteilles 'finished' n'entrent pas dans la valeur du stock");
assert.strictEqual(stats.averageAge, 13, "moyenne des âges renseignés (16+10)/2 = 13 ; Maker's Mark sans âge est ignoré");
assert.deepStrictEqual(stats.byPeat, [["Tourbé", 3], ["Non tourbé", 2]]);

// Sur un sous-ensemble filtré (favoris uniquement)
const favStats = computeStats(filterWhiskies(all, { favorite: true }));
assert.strictEqual(favStats.references, 1);
assert.strictEqual(favStats.total, 2);

// Collection vide : aucune division par zéro
const emptyStats = computeStats([]);
assert.strictEqual(emptyStats.total, 0);
assert.strictEqual(emptyStats.averageAge, 0);
assert.strictEqual(emptyStats.collectionValue, 0);
assert.deepStrictEqual(emptyStats.byCountry, []);

// 6) topBreakdown — limite et calcule un pourcentage relatif au maximum affiché
const bars = topBreakdown([["Islay", 3], ["Kentucky", 2], ["Speyside", 1]], 2);
assert.deepStrictEqual(bars, [
  { label: "Islay", count: 3, pct: 100 },
  { label: "Kentucky", count: 2, pct: 67 },
]);
assert.deepStrictEqual(topBreakdown([], 8), []);

console.log("commit8_card_stats_filters.js : OK (6 groupes d'assertions)");
