const assert = require("assert");
const path = require("path");

// Stub minimal : le fichier définit une classe extends HTMLElement au niveau
// module (jamais instanciée ici, seules les fonctions pures sont testées),
// donc seule la référence globale doit exister pour que le require() réussisse.
global.HTMLElement = class {};

const {
  buildWhiskyPayload, triStateToPayload, triStateFromValue, numberOrUndefined,
  confidenceTier, recognitionFieldList, applyRecognitionSelection,
  WHISKY_TYPE_VALUES, CASK_TYPE_SUGGESTIONS,
} = require(path.join(process.cwd(), "custom_components/whisky/whisky-card.js"));

// 1) triStateToPayload / triStateFromValue
assert.strictEqual(triStateToPayload(""), undefined);
assert.strictEqual(triStateToPayload("true"), true);
assert.strictEqual(triStateToPayload("false"), false);
assert.strictEqual(triStateFromValue(true), "true");
assert.strictEqual(triStateFromValue(false), "false");
assert.strictEqual(triStateFromValue(null), "");
assert.strictEqual(triStateFromValue(undefined), "");

// 2) numberOrUndefined
assert.strictEqual(numberOrUndefined(""), undefined);
assert.strictEqual(numberOrUndefined("  "), undefined);
assert.strictEqual(numberOrUndefined("43"), 43);
assert.strictEqual(numberOrUndefined("43,5"), 43.5);
assert.strictEqual(numberOrUndefined("abc"), undefined);

// 3) buildWhiskyPayload : champs vides omis, jamais envoyés comme "" (n'écrasent rien)
const raw1 = {
  name: "Lagavulin 16", distillery: "Lagavulin", region: "  ", abv: "43",
  peated: "true", chill_filtered: "", favorite: true, rating: "4.5",
  notes: "   ", quantity: "3", initial_status: "sealed",
};
const payload1 = buildWhiskyPayload(raw1);
assert.strictEqual(payload1.name, "Lagavulin 16");
assert.strictEqual(payload1.distillery, "Lagavulin");
assert.ok(!("region" in payload1), "un champ vide/espaces ne doit pas être envoyé");
assert.strictEqual(payload1.abv, 43);
assert.strictEqual(payload1.peated, true);
assert.ok(!("chill_filtered" in payload1), "tri-state vide ('Non renseigné') ne doit rien envoyer");
assert.strictEqual(payload1.favorite, true);
assert.strictEqual(payload1.rating, 4.5);
assert.ok(!("notes" in payload1));
assert.strictEqual(payload1.quantity, 3);
assert.strictEqual(payload1.initial_status, "sealed");

// favorite=false doit quand même être envoyé explicitement (sinon impossible
// de désactiver un coup de cœur déjà activé lors d'une édition)
const payload2 = buildWhiskyPayload({ favorite: false });
assert.strictEqual(payload2.favorite, false);

// 4) confidenceTier
assert.strictEqual(confidenceTier(0.9).label, "Fiable");
assert.strictEqual(confidenceTier(0.6).label, "Moyenne");
assert.strictEqual(confidenceTier(0.2).label, "Faible");
assert.strictEqual(confidenceTier(null).label, "Inconnue");
assert.strictEqual(confidenceTier(undefined).label, "Inconnue");

// 5) recognitionFieldList : ignore null/undefined/"" et les clés de métadonnées
const result = {
  name: "Caol Ila 11", distillery: "Caol Ila", bottler: "Signatory Vintage",
  brand: null, expression: "", country: "Écosse", abv: 46,
  confidence_score: 0.87, field_confidence: { distillery: 0.95 },
};
const fields = recognitionFieldList(result);
const keys = fields.map((f) => f.key).sort();
assert.deepStrictEqual(keys, ["abv", "bottler", "country", "distillery", "name"].sort());
const distField = fields.find((f) => f.key === "distillery");
assert.strictEqual(distField.confidence, 0.95);
const countryField = fields.find((f) => f.key === "country");
assert.strictEqual(countryField.confidence, undefined);  // pas de field_confidence fourni pour ce champ

// 6) applyRecognitionSelection : n'applique que les clés sélectionnées
const current = { name: "", distillery: "", peated: "" };
const applied = applyRecognitionSelection(current, { distillery: "Caol Ila", peated: true }, ["distillery"]);
assert.strictEqual(applied.distillery, "Caol Ila");
assert.strictEqual(applied.peated, "");  // non sélectionné -> inchangé
assert.strictEqual(current.distillery, "", "ne doit pas muter l'objet d'origine");

// 7) Cohérence des listes de référence (doivent matcher le backend __init__.py)
assert.ok(WHISKY_TYPE_VALUES.includes("Single Malt"));
assert.ok(WHISKY_TYPE_VALUES.includes("Other"));
assert.strictEqual(WHISKY_TYPE_VALUES.length, 13);
assert.ok(CASK_TYPE_SUGGESTIONS.includes("First Fill Bourbon"));

console.log("Smoke test commit 6 (fonctions pures de la carte) : TOUS LES CONTRÔLES PASSENT");
