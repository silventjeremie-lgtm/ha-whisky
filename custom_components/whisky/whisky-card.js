// Whisky — Carte Lovelace
// Projet indépendant dérivé de Millésime (github.com/Redsklns/ha-millesime,
// licence MIT) : même style d'architecture (Web Component vanilla, Shadow
// DOM, rendu par template strings), vocabulaire entièrement whisky.
//
// Commit 12/12 : packaging final — VERSION 1.0.0, socle v1 complet. Pas de
// changement fonctionnel côté carte depuis le commit 9 (suivi du niveau
// restant) ; le commit 8 avait ajouté le panneau de statistiques et la barre
// de recherche/filtres ; le commit 7, la liste (tuiles) et la fiche détail ;
// le commit 6, le formulaire d'ajout/édition et la reconnaissance photo
// Gemini.
//
// Les fonctions PURES (sans DOM) sont exportées en fin de fichier pour être
// testées avec Node (voir tests/), sans dépendre d'un navigateur ou de HA.

const DOMAIN = "whisky";
const VERSION = "1.0.2";

// Doit rester synchronisé avec WHISKY_TYPE_VALUES dans __init__.py.
const WHISKY_TYPE_VALUES = [
  "Single Malt", "Blended Malt", "Blended Whisky", "Single Grain",
  "Bourbon", "Rye", "Tennessee Whiskey", "Corn Whiskey",
  "Irish Single Malt", "Irish Pot Still", "Japanese Whisky",
  "World Whisky", "Other",
];

// Doit rester synchronisé avec CASK_TYPE_SUGGESTIONS dans __init__.py.
const CASK_TYPE_SUGGESTIONS = [
  "Bourbon", "First Fill Bourbon", "Refill Bourbon", "Sherry", "Oloroso",
  "PX", "Port", "Madeira", "Wine", "Virgin Oak", "Mizunara",
  "Multiple Casks", "Other",
];

const BOTTLE_STATUS_LABELS = { sealed: "Scellée", opened: "Ouverte", finished: "Terminée" };

const ERROR_MESSAGES = {
  no_key: "Aucune clé Gemini configurée — ajoutez-en une dans les paramètres de l'intégration, ou saisissez les informations à la main.",
  invalid_key: "Clé Gemini invalide ou refusée par Google.",
  quota_exceeded: "Quota Gemini quotidien dépassé — réessayez demain ou saisissez à la main.",
  service_unavailable: "Service Gemini momentanément indisponible.",
  timeout: "Délai dépassé — réessayez.",
  no_model: "Aucun modèle Gemini accessible avec cette clé.",
  truncated: "Réponse coupée — réessayez avec une photo plus nette.",
  parse_error: "Réponse Gemini illisible — réessayez.",
};

// ── Champs du formulaire, groupés par section (brief §2 et §6) ──────────────
// type: "text" | "number" | "tri" | "select" | "textarea" | "checkbox"
const FORM_SECTIONS = [
  {
    title: "🥃 Identité", key: "identity",
    fields: [
      { key: "name", label: "Nom *", type: "text", required: true, placeholder: "ex. Lagavulin 16 Years Old" },
      { key: "distillery", label: "Distillerie", type: "text", placeholder: "ex. Lagavulin" },
      { key: "bottler", label: "Embouteilleur indépendant", type: "text", placeholder: "si différent de la distillerie" },
      { key: "brand", label: "Marque", type: "text" },
      { key: "expression", label: "Expression / cuvée", type: "text", placeholder: "ex. 16 Year Old" },
    ],
  },
  {
    title: "🌍 Origine", key: "origin",
    fields: [
      { key: "country", label: "Pays", type: "text", placeholder: "ex. Écosse" },
      { key: "region", label: "Région", type: "text", placeholder: "ex. Islay" },
      { key: "distillery_location", label: "Localisation de la distillerie", type: "text" },
    ],
  },
  {
    title: "🏷️ Classification", key: "classification",
    fields: [
      { key: "whisky_type", label: "Type", type: "select", options: WHISKY_TYPE_VALUES },
    ],
  },
  {
    title: "🔬 Caractéristiques", key: "characteristics",
    fields: [
      { key: "age", label: "Âge (années)", type: "text", placeholder: "ex. 16, ou vide si NAS" },
      { key: "vintage", label: "Millésime de distillation", type: "text" },
      { key: "bottling_year", label: "Année de mise en bouteille", type: "text" },
      { key: "abv", label: "Degré d'alcool (% vol)", type: "number", step: "0.1" },
      { key: "volume_ml", label: "Volume (ml)", type: "number", placeholder: "700" },
      { key: "chill_filtered", label: "Filtré à froid", type: "tri" },
      { key: "natural_colour", label: "Couleur naturelle", type: "tri" },
      { key: "peated", label: "Tourbé", type: "tri" },
      { key: "peat_level", label: "Niveau de tourbe", type: "text", placeholder: "ex. léger, moyen, fort" },
      { key: "ppm", label: "Phénols (ppm)", type: "number" },
    ],
  },
  {
    title: "🛢️ Maturation", key: "maturation",
    fields: [
      { key: "maturation", label: "Résumé de la maturation", type: "text" },
      { key: "cask_type", label: "Type de fût", type: "text", list: "whisky-cask-types" },
      { key: "cask_number", label: "Numéro de fût", type: "text" },
      { key: "finish", label: "Finition (cask finish)", type: "text" },
      { key: "maturation_years", label: "Durée de maturation (années)", type: "text" },
    ],
  },
  {
    title: "📦 Embouteillage", key: "bottling",
    fields: [
      { key: "batch", label: "Lot (batch)", type: "text" },
      { key: "edition", label: "Édition", type: "text" },
      { key: "bottle_number", label: "Numéro de bouteille", type: "text" },
      { key: "number_of_bottles", label: "Nombre total de bouteilles produites", type: "text" },
      { key: "limited_edition", label: "Édition limitée", type: "tri" },
      { key: "independent_bottler", label: "Mise en bouteille indépendante", type: "tri" },
    ],
  },
  {
    title: "👃 Dégustation", key: "tasting",
    fields: [
      { key: "tasting_notes", label: "Notes générales", type: "textarea" },
      { key: "nose_notes", label: "Nez", type: "textarea" },
      { key: "palate_notes", label: "Bouche", type: "textarea" },
      { key: "finish_notes", label: "Finale", type: "textarea" },
    ],
  },
  {
    title: "💰 Collection personnelle", key: "collection",
    fields: [
      { key: "price", label: "Prix d'achat", type: "number", step: "0.01" },
      { key: "current_value", label: "Valeur actuelle estimée", type: "number", step: "0.01" },
      { key: "currency", label: "Devise", type: "text", placeholder: "EUR" },
      { key: "purchase_date", label: "Date d'achat", type: "date" },
      { key: "purchase_location", label: "Lieu d'achat", type: "text" },
      { key: "storage_location", label: "Emplacement de rangement", type: "text", placeholder: "ex. Buffet salon" },
    ],
  },
  {
    title: "⭐ Notes & médias", key: "notes",
    fields: [
      { key: "rating", label: "Note personnelle (/5)", type: "number", step: "0.5", min: "0", max: "5" },
      { key: "favorite", label: "Coup de cœur", type: "checkbox" },
      { key: "notes", label: "Commentaires personnels", type: "textarea" },
      { key: "image_url", label: "Photo (URL)", type: "text" },
      { key: "label_image_url", label: "Photo d'étiquette (URL)", type: "text" },
    ],
  },
  {
    title: "🔗 Références externes", key: "external",
    fields: [
      { key: "barcode", label: "Code-barres", type: "text" },
      { key: "external_id", label: "Identifiant externe", type: "text" },
      { key: "external_url", label: "Lien externe", type: "text" },
      { key: "whiskybase_id", label: "ID Whiskybase (optionnel)", type: "text" },
      { key: "whiskybase_url", label: "Lien Whiskybase (optionnel)", type: "text" },
    ],
  },
];

// Champs uniquement présents à la CRÉATION (pas de sens en édition, où l'état
// physique se gère bouteille par bouteille depuis la fiche détail — commit 7).
const CREATE_ONLY_SECTION = {
  title: "📥 À l'ajout", key: "creation",
  fields: [
    { key: "quantity", label: "Quantité", type: "number", min: "1", placeholder: "1" },
    { key: "initial_status", label: "État initial", type: "select", options: ["sealed", "opened", "finished"], optionLabels: BOTTLE_STATUS_LABELS },
  ],
};

// ── Fonctions pures (testables sans DOM — voir export en fin de fichier) ────

function triStateToPayload(value) {
  // "" (non renseigné) -> undefined : le champ n'est PAS envoyé, la valeur
  // par défaut (null côté backend) reste en place. "true"/"false" -> booléen.
  if (value === "true") return true;
  if (value === "false") return false;
  return undefined;
}

function triStateFromValue(value) {
  if (value === true) return "true";
  if (value === false) return "false";
  return "";
}

function numberOrUndefined(raw) {
  if (raw === undefined || raw === null || String(raw).trim() === "") return undefined;
  const n = Number(String(raw).replace(",", "."));
  return Number.isFinite(n) ? n : undefined;
}

const TRI_FIELDS = new Set(["chill_filtered", "natural_colour", "peated", "limited_edition", "independent_bottler"]);
const NUMBER_FIELDS = new Set(["abv", "volume_ml", "ppm", "price", "current_value", "rating", "quantity"]);

/**
 * Construit le payload d'appel de service (add_whisky / update_whisky) à
 * partir des valeurs BRUTES du formulaire (toutes des chaînes, comme le
 * rendrait une lecture de <input>.value). Ne renvoie QUE les champs
 * effectivement renseignés : un champ vide n'écrase jamais une valeur
 * existante côté backend (voir svc_update_whisky, qui ne touche que les
 * clés présentes dans call.data).
 */
function buildWhiskyPayload(raw) {
  const payload = {};
  for (const key of Object.keys(raw)) {
    const v = raw[key];
    if (TRI_FIELDS.has(key)) {
      const tv = triStateToPayload(v);
      if (tv !== undefined) payload[key] = tv;
    } else if (key === "favorite") {
      payload[key] = !!v;
    } else if (NUMBER_FIELDS.has(key)) {
      const n = numberOrUndefined(v);
      if (n !== undefined) payload[key] = n;
    } else if (v !== undefined && v !== null && String(v).trim() !== "") {
      payload[key] = String(v).trim();
    }
  }
  return payload;
}

const CONFIDENCE_TIERS = [
  { min: 0.8, label: "Fiable", cls: "conf-high" },
  { min: 0.5, label: "Moyenne", cls: "conf-mid" },
  { min: 0, label: "Faible", cls: "conf-low" },
];

function confidenceTier(score) {
  if (score === undefined || score === null) return { label: "Inconnue", cls: "conf-none" };
  for (const t of CONFIDENCE_TIERS) if (score >= t.min) return t;
  return CONFIDENCE_TIERS[CONFIDENCE_TIERS.length - 1];
}

/**
 * Liste des champs exploitables d'un résultat de reconnaissance (non null),
 * avec leur confiance — sert à construire l'écran de validation (brief §3 :
 * toujours présenter à l'utilisateur avant tout enregistrement).
 */
function recognitionFieldList(result) {
  if (!result) return [];
  const skip = new Set(["confidence_score", "field_confidence"]);
  const conf = result.field_confidence || {};
  return Object.keys(result)
    .filter((k) => !skip.has(k) && result[k] !== null && result[k] !== undefined && result[k] !== "")
    .map((k) => ({ key: k, value: result[k], confidence: conf[k] }));
}

/**
 * Applique les champs SÉLECTIONNÉS d'un résultat de reconnaissance à un jeu
 * de valeurs de formulaire existant, SANS jamais écraser un champ déjà
 * rempli par l'utilisateur sauf si explicitement sélectionné.
 */
function applyRecognitionSelection(currentValues, result, selectedKeys) {
  const next = { ...currentValues };
  for (const key of selectedKeys) {
    if (result[key] !== null && result[key] !== undefined) {
      next[key] = TRI_FIELDS.has(key) ? triStateFromValue(result[key]) : String(result[key]);
    }
  }
  return next;
}

// ── Fonctions pures : liste & fiche détail (commit 7) ───────────────────────

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

const STATUS_ORDER = ["sealed", "opened", "finished"];
const STATUS_DOT = { sealed: "●", opened: "◐", finished: "○" };

/** {sealed: n, opened: n, finished: n} à partir des emplacements d'une fiche. */
function statusBreakdown(slots) {
  const counts = { sealed: 0, opened: 0, finished: 0 };
  for (const s of slots || []) {
    const st = counts.hasOwnProperty(s.bottle_status) ? s.bottle_status : "sealed";
    counts[st] += 1;
  }
  return counts;
}

/** Résumé court des statuts pour l'affichage tuile, ex. "2 scellées · 1 ouverte". */
function statusSummary(slots) {
  const counts = statusBreakdown(slots);
  const labels = { sealed: "scellée", opened: "ouverte", finished: "terminée" };
  return STATUS_ORDER.filter((k) => counts[k] > 0)
    .map((k) => `${STATUS_DOT[k]} ${counts[k]} ${labels[k]}${counts[k] > 1 ? "s" : ""}`)
    .join(" · ") || "aucune bouteille";
}

/** "★★★★☆" pour une note 0-5 (arrondie à l'entier le plus proche pour l'affichage). */
function ratingStars(rating) {
  const n = Math.max(0, Math.min(5, Math.round(Number(rating) || 0)));
  return "★".repeat(n) + "☆".repeat(5 - n);
}

/** Ligne "Islay · Single Malt" / "16 ans · 43 %" pour la tuile, en omettant les champs absents. */
function metaLine(parts) {
  return parts.filter((p) => p !== null && p !== undefined && String(p).trim() !== "").join(" · ");
}

function tileHTML(w) {
  const meta = w.whisky_meta || {};
  const line1 = metaLine([meta.region || meta.country, meta.whisky_type]);
  const line2 = metaLine([meta.age ? `${meta.age} ans` : null, meta.abv ? `${meta.abv} %` : null]);
  const img = w.image_url
    ? `<img class="wc-tile-img" src="${escapeHtml(w.image_url)}" alt="" />`
    : `<div class="wc-tile-img wc-tile-img-placeholder">🥃</div>`;
  return `
    <div class="wc-tile" data-whisky-id="${escapeHtml(w.id)}">
      ${img}
      <div class="wc-tile-body">
        <div class="wc-tile-name">${w.favorite ? "★ " : ""}${escapeHtml(w.name)}</div>
        ${meta.expression ? `<div class="wc-tile-sub">${escapeHtml(meta.expression)}</div>` : ""}
        ${line1 ? `<div class="wc-tile-sub">${escapeHtml(line1)}</div>` : ""}
        ${line2 ? `<div class="wc-tile-sub">${escapeHtml(line2)}</div>` : ""}
        <div class="wc-tile-status">${escapeHtml(statusSummary(w.slots))}</div>
        ${w.rating ? `<div class="wc-tile-rating">${ratingStars(w.rating)}</div>` : ""}
      </div>
    </div>`;
}

/** Regroupe les champs whisky_meta en lignes label/valeur par section détail (commit 6/7 partagent FORM_SECTIONS). */
function detailRows(w) {
  const meta = w.whisky_meta || {};
  const get = (k) => (k in w ? w[k] : meta[k]);
  return FORM_SECTIONS
    .filter((s) => s.key !== "tasting")  // la dégustation a sa propre mise en page (texte long)
    .map((s) => ({
      title: s.title,
      rows: s.fields
        .map((f) => {
          let v = get(f.key);
          if (f.type === "tri") v = v === true ? "Oui" : v === false ? "Non" : "";
          if (f.type === "checkbox") v = v ? "Oui" : "";
          return { label: f.label.replace(" *", ""), value: v };
        })
        .filter((r) => r.value !== "" && r.value !== null && r.value !== undefined),
    }))
    .filter((s) => s.rows.length > 0);
}

// ── Fonctions pures : recherche, filtres & statistiques (commit 8) ─────────

/** Vrai si le texte libre `q` correspond à un champ identitaire de la fiche. */
function matchesQuery(w, q) {
  const needle = String(q || "").trim().toLowerCase();
  if (!needle) return true;
  const meta = w.whisky_meta || {};
  const haystack = [w.name, meta.distillery, meta.bottler, meta.brand, meta.expression, meta.region, meta.country]
    .filter((v) => v !== null && v !== undefined && v !== "")
    .join(" ")
    .toLowerCase();
  return haystack.includes(needle);
}

/** Vrai si la fiche possède au moins un exemplaire dans le statut demandé (ou si aucun statut n'est demandé). */
function matchesStatusFilter(w, status) {
  if (!status) return true;
  return (w.slots || []).some((s) => (s.bottle_status || "sealed") === status);
}

/**
 * Filtre la liste des fiches whisky selon {q, whisky_type, status, favorite}.
 * Filtre purement côté client (les données sont déjà toutes chargées en
 * mémoire via whisky/get_data) — aucun filtre non renseigné n'exclut rien.
 */
function filterWhiskies(whiskies, filters) {
  const f = filters || {};
  return (whiskies || []).filter((w) => {
    if (f.favorite && !w.favorite) return false;
    if (f.whisky_type && ((w.whisky_meta || {}).whisky_type || "") !== f.whisky_type) return false;
    if (!matchesStatusFilter(w, f.status)) return false;
    if (!matchesQuery(w, f.q)) return false;
    return true;
  });
}

/** Répartition {clé -> nombre de bouteilles} triée par fréquence décroissante (miroir de sensor.py _breakdown). */
function breakdownJS(whiskies, keyFn) {
  const counts = {};
  for (const w of whiskies || []) {
    const key = keyFn(w);
    if (!key) continue;
    const n = (w.slots || []).length;
    counts[key] = (counts[key] || 0) + n;
  }
  return Object.entries(counts).sort((a, b) => b[1] - a[1]);
}

/**
 * Statistiques agrégées de la collection (ou d'un sous-ensemble filtré) —
 * mêmes définitions que les capteurs HA (sensor.py), recalculées côté carte
 * pour permettre un panneau de statistiques sans dépendre d'entités HA
 * exposées sur un tableau de bord.
 */
function computeStats(whiskies) {
  const list = whiskies || [];
  const allSlots = list.flatMap((w) => w.slots || []);
  const countByStatus = (status) => allSlots.filter((s) => (s.bottle_status || "sealed") === status).length;
  const distilleries = new Set(
    list.map((w) => ((w.whisky_meta || {}).distillery || "").trim().toLowerCase()).filter(Boolean)
  );
  let value = 0;
  for (const w of list) {
    const unit = Number(w.current_value) || Number(w.price) || 0;
    if (unit <= 0) continue;
    const n = (w.slots || []).filter((s) => (s.bottle_status || "sealed") !== "finished").length;
    value += unit * n;
  }
  const ages = [];
  for (const w of list) {
    const raw = (w.whisky_meta || {}).age;
    const age = Number(String(raw === null || raw === undefined ? "" : raw).trim().replace(",", "."));
    if (Number.isFinite(age) && age > 0) ages.push(age);
  }
  const avgAge = ages.length ? ages.reduce((a, b) => a + b, 0) / ages.length : 0;
  return {
    total: allSlots.length,
    references: list.length,
    sealed: countByStatus("sealed"),
    opened: countByStatus("opened"),
    finished: countByStatus("finished"),
    distilleries: distilleries.size,
    collectionValue: Math.round(value * 100) / 100,
    averageAge: Math.round(avgAge * 10) / 10,
    byCountry: breakdownJS(list, (w) => (w.whisky_meta || {}).country),
    byRegion: breakdownJS(list, (w) => (w.whisky_meta || {}).region),
    byDistillery: breakdownJS(list, (w) => (w.whisky_meta || {}).distillery),
    byType: breakdownJS(list, (w) => (w.whisky_meta || {}).whisky_type),
    byPeat: breakdownJS(list, (w) => {
      const p = (w.whisky_meta || {}).peated;
      return p === true ? "Tourbé" : p === false ? "Non tourbé" : null;
    }),
  };
}

/** Réduit une répartition [ [label, count], ... ] aux `limit` premières entrées avec un pourcentage de barre relatif au maximum affiché. */
function topBreakdown(entries, limit = 8) {
  const top = (entries || []).slice(0, limit);
  const max = top.reduce((m, [, n]) => Math.max(m, n), 0) || 1;
  return top.map(([label, count]) => ({ label, count, pct: Math.round((count / max) * 100) }));
}

// ── Composant carte ───────────────────────────────────────────────────────

class WhiskyCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = { cellars: [], whiskies: [], tasting_log: [] };
    this._filters = { q: "", whisky_type: "", status: "", favorite: false };
  }

  setConfig(config) {
    this._config = config || {};
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._init();
  }

  getCardSize() {
    return 4;
  }

  connectedCallback() {
    if (this._hass && !this._inited) this._init();
  }

  disconnectedCallback() {
    if (this._unsubUpdated) { this._unsubUpdated(); this._unsubUpdated = null; }
  }

  async _init() {
    if (this._inited) return;
    this._inited = true;
    await this._fetchData();
    try {
      this._unsubUpdated = await this._hass.connection.subscribeEvents(
        () => this._fetchData(), `${DOMAIN}_updated`
      );
    } catch (e) {
      // Abonnement optionnel : la carte reste utilisable sans rafraîchissement auto.
    }
  }

  async _fetchData() {
    try {
      this._data = await this._hass.connection.sendMessagePromise({ type: `${DOMAIN}/get_data` });
    } catch (e) {
      this._data = { cellars: [], whiskies: [], tasting_log: [] };
    }
    this._render();
  }

  // ── Rendu principal : recherche/filtres + liste des fiches ────────────────

  _render() {
    const root = this.shadowRoot;

    // Préserve le focus/la sélection d'un champ de la barre d'outils (ex. la
    // recherche) à travers le innerHTML complet ci-dessous — sans ça, chaque
    // frappe au clavier ferait perdre le focus du champ de recherche.
    const active = root.activeElement;
    const activeId = active && active.id;
    const selStart = active && typeof active.selectionStart === "number" ? active.selectionStart : null;
    const selEnd = active && typeof active.selectionEnd === "number" ? active.selectionEnd : null;

    const allWhiskies = (this._data && this._data.whiskies) || [];
    const filters = this._filters;
    const whiskies = filterWhiskies(allWhiskies, filters);
    const total = whiskies.reduce((n, w) => n + ((w.slots && w.slots.length) || 0), 0);
    const filtered = whiskies.length !== allWhiskies.length;
    const hint = filtered
      ? `${whiskies.length} fiche(s) affichée(s) sur ${allWhiskies.length} (${total} bouteille(s))`
      : `${whiskies.length} fiche(s), ${total} bouteille(s)`;
    const tiles = allWhiskies.length === 0
      ? `<div class="wc-empty">Aucun whisky pour l'instant — cliquez sur ➕ Ajouter pour commencer votre collection.</div>`
      : whiskies.length
        ? `<div class="wc-grid-tiles">${whiskies.map((w) => tileHTML(w)).join("")}</div>`
        : `<div class="wc-empty">Aucune fiche ne correspond à ces filtres.</div>`;

    const typeOptions = WHISKY_TYPE_VALUES.map((t) =>
      `<option value="${t}" ${filters.whisky_type === t ? "selected" : ""}>${t}</option>`).join("");
    const statusOptions = STATUS_ORDER.map((s) =>
      `<option value="${s}" ${filters.status === s ? "selected" : ""}>${BOTTLE_STATUS_LABELS[s]}</option>`).join("");

    root.innerHTML = `
      <style>${CARD_CSS}</style>
      <div class="wc-card">
        <div class="wc-header">
          <div class="wc-title">🥃 Whisky — Collection</div>
          <div class="wc-header-actions">
            <button class="wc-btn" id="wc-stats-btn">📊 Statistiques</button>
            <button class="wc-btn wc-btn-primary" id="wc-add">➕ Ajouter</button>
          </div>
        </div>
        <div class="wc-toolbar">
          <input type="search" id="wc-search" class="wc-search" placeholder="🔎 Nom, distillerie, région…" value="${escapeHtml(filters.q)}" />
          <select id="wc-filter-type"><option value="">Tous les types</option>${typeOptions}</select>
          <select id="wc-filter-status"><option value="">Tous statuts</option>${statusOptions}</select>
          <label class="wc-filter-fav"><input type="checkbox" id="wc-filter-fav" ${filters.favorite ? "checked" : ""} /> Coups de cœur</label>
        </div>
        <div class="wc-hint">${hint}</div>
        ${tiles}
      </div>
    `;

    const addBtn = root.getElementById("wc-add");
    if (addBtn) addBtn.addEventListener("click", () => this._openForm(null));
    const statsBtn = root.getElementById("wc-stats-btn");
    if (statsBtn) statsBtn.addEventListener("click", () => this._openStats());
    root.querySelectorAll("[data-whisky-id]").forEach((el) => {
      el.addEventListener("click", () => {
        const w = whiskies.find((x) => x.id === el.dataset.whiskyId);
        if (w) this._openDetail(w);
      });
    });

    const searchEl = root.getElementById("wc-search");
    if (searchEl) searchEl.addEventListener("input", (e) => { this._filters.q = e.target.value; this._render(); });
    const typeEl = root.getElementById("wc-filter-type");
    if (typeEl) typeEl.addEventListener("change", (e) => { this._filters.whisky_type = e.target.value; this._render(); });
    const statusEl = root.getElementById("wc-filter-status");
    if (statusEl) statusEl.addEventListener("change", (e) => { this._filters.status = e.target.value; this._render(); });
    const favEl = root.getElementById("wc-filter-fav");
    if (favEl) favEl.addEventListener("change", (e) => { this._filters.favorite = e.target.checked; this._render(); });

    if (activeId) {
      const el = root.getElementById(activeId);
      if (el) {
        el.focus();
        if (selStart !== null && el.setSelectionRange) {
          try { el.setSelectionRange(selStart, selEnd); } catch (e) { /* type d'input sans sélection (ex. number) */ }
        }
      }
    }
  }

  // ── Statistiques (commit 8) ────────────────────────────────────────────────

  _openStats() {
    const box = this._openModal(this._statsHTML());
    const closeBtn = box.querySelector("#wc-stats-close");
    if (closeBtn) closeBtn.addEventListener("click", () => this._closeModal());
  }

  _statsHTML() {
    const allWhiskies = (this._data && this._data.whiskies) || [];
    const s = computeStats(allWhiskies);
    const barsBlock = (title, entries) => {
      const top = topBreakdown(entries, 8);
      if (!top.length) return "";
      return `
        <fieldset class="wc-section">
          <legend>${escapeHtml(title)}</legend>
          ${top.map((e) => `
            <div class="wc-stat-bar-row">
              <span class="wc-stat-bar-label">${escapeHtml(e.label)}</span>
              <span class="wc-stat-bar-track"><span class="wc-stat-bar-fill" style="width:${e.pct}%"></span></span>
              <span class="wc-stat-bar-count">${e.count}</span>
            </div>`).join("")}
        </fieldset>`;
    };
    return `
      <h2 class="wc-modal-title">📊 Statistiques de la collection</h2>
      <div class="wc-stat-grid">
        <div class="wc-stat-tile"><div class="wc-stat-num">${s.total}</div><div class="wc-stat-label">Bouteilles</div></div>
        <div class="wc-stat-tile"><div class="wc-stat-num">${s.references}</div><div class="wc-stat-label">Fiches</div></div>
        <div class="wc-stat-tile"><div class="wc-stat-num">${s.sealed}</div><div class="wc-stat-label">Scellées</div></div>
        <div class="wc-stat-tile"><div class="wc-stat-num">${s.opened}</div><div class="wc-stat-label">Ouvertes</div></div>
        <div class="wc-stat-tile"><div class="wc-stat-num">${s.finished}</div><div class="wc-stat-label">Terminées</div></div>
        <div class="wc-stat-tile"><div class="wc-stat-num">${s.distilleries}</div><div class="wc-stat-label">Distilleries</div></div>
        <div class="wc-stat-tile"><div class="wc-stat-num">${s.collectionValue} €</div><div class="wc-stat-label">Valeur (stock restant)</div></div>
        <div class="wc-stat-tile"><div class="wc-stat-num">${s.averageAge || "—"}</div><div class="wc-stat-label">Âge moyen (ans)</div></div>
      </div>
      ${barsBlock("Par pays", s.byCountry)}
      ${barsBlock("Par région", s.byRegion)}
      ${barsBlock("Par distillerie", s.byDistillery)}
      ${barsBlock("Par type", s.byType)}
      ${barsBlock("Tourbe", s.byPeat)}
      <div class="wc-actions"><button type="button" class="wc-btn" id="wc-stats-close">Fermer</button></div>
    `;
  }

  // ── Modale (hors shadow root, comme Millésime — un formulaire doit rester
  //    utilisable même si la carte est petite/en colonne latérale) ──────────

  _openModal(html) {
    this._closeModal();
    const overlay = document.createElement("div");
    overlay.className = "wc-overlay";
    overlay.innerHTML = `<style>${MODAL_CSS}</style><div class="wc-modal-box">${html}</div>`;
    overlay.addEventListener("click", (e) => { if (e.target === overlay) this._closeModal(); });
    document.body.appendChild(overlay);
    this._overlay = overlay;
    return overlay.querySelector(".wc-modal-box");
  }

  _closeModal() {
    if (this._overlay) { this._overlay.remove(); this._overlay = null; }
  }

  // ── Fiche détail ───────────────────────────────────────────────────────────

  _openDetail(w) {
    const box = this._openModal(this._detailHTML(w));
    this._bindDetail(box, w);
  }

  _detailHTML(w) {
    const meta = w.whisky_meta || {};
    const sections = detailRows(w);
    const img = w.image_url
      ? `<img class="wc-detail-img" src="${escapeHtml(w.image_url)}" alt="" />`
      : "";
    const slotsHTML = (w.slots || []).map((s, idx) => {
      const place = s.rack_id
        ? `Étagère ${escapeHtml(s.rack_id)} · emplacement ${Number(s.slot) + 1}`
        : "Non placée";
      const status = s.bottle_status || "sealed";
      const extra = [];
      if (status === "opened" && s.opened_date) extra.push(`ouverte le ${escapeHtml(s.opened_date)}`);
      if (status === "opened") extra.push(`${s.remaining_percent != null ? s.remaining_percent : 100}% restant`);
      if (status === "finished" && s.finished_date) extra.push(`terminée le ${escapeHtml(s.finished_date)}`);
      if (s.comment) extra.push(escapeHtml(s.comment));
      const actions = [];
      if (status === "sealed") actions.push(`<button type="button" class="wc-btn wc-slot-open" data-idx="${idx}">Ouvrir</button>`);
      if (status === "opened") actions.push(`<button type="button" class="wc-btn wc-slot-finish" data-idx="${idx}">Terminer</button>`);
      actions.push(`<button type="button" class="wc-btn wc-slot-remove" data-idx="${idx}">Retirer</button>`);
      // Suivi manuel du niveau restant (commit 9 : svc_update_remaining) —
      // uniquement pour un exemplaire ouvert, déclenche whisky_bottle_low
      // côté backend au franchissement du seuil bas.
      const remainingRow = status === "opened" ? `
        <div class="wc-slot-remaining-row">
          <label class="wc-slot-remaining-label">Niveau restant
            <input type="number" min="0" max="100" step="5" class="wc-slot-remaining-input"
              data-idx="${idx}" value="${s.remaining_percent != null ? s.remaining_percent : 100}" />%
          </label>
          <button type="button" class="wc-btn wc-slot-remaining-save" data-idx="${idx}">Mettre à jour</button>
        </div>` : "";
      return `
        <div class="wc-slot">
          <div class="wc-slot-row">
            <span class="wc-slot-dot">${STATUS_DOT[status] || "●"}</span>
            <span class="wc-slot-place">${place}</span>
            <span class="wc-slot-status">${escapeHtml(BOTTLE_STATUS_LABELS[status] || status)}${extra.length ? " · " + extra.join(" · ") : ""}</span>
            <span class="wc-slot-actions">${actions.join("")}</span>
          </div>
          ${remainingRow}
        </div>`;
    }).join("") || `<div class="wc-slot wc-slot-empty">Aucun exemplaire.</div>`;

    const tastingFields = [
      ["Notes générales", meta.tasting_notes], ["Nez", meta.nose_notes],
      ["Bouche", meta.palate_notes], ["Finale", meta.finish_notes],
    ].filter(([, v]) => v);
    const tastingHTML = tastingFields.length
      ? `<fieldset class="wc-section"><legend>👃 Dégustation</legend>
          ${tastingFields.map(([l, v]) => `<div class="wc-detail-row"><span class="wc-detail-label">${l}</span><span class="wc-detail-value">${escapeHtml(v)}</span></div>`).join("")}
        </fieldset>`
      : "";

    const sectionsHTML = sections.map((s) => `
      <fieldset class="wc-section">
        <legend>${s.title}</legend>
        ${s.rows.map((r) => `<div class="wc-detail-row"><span class="wc-detail-label">${escapeHtml(r.label)}</span><span class="wc-detail-value">${escapeHtml(r.value)}</span></div>`).join("")}
      </fieldset>
    `).join("");

    return `
      <div class="wc-detail-header">
        <h2 class="wc-modal-title">${w.favorite ? "★ " : ""}${escapeHtml(w.name)}</h2>
        <div class="wc-detail-actions">
          <button type="button" class="wc-btn" id="wc-detail-edit">✏️ Modifier</button>
          <button type="button" class="wc-btn" id="wc-detail-delete">🗑️ Supprimer</button>
        </div>
      </div>
      ${img}
      <div class="wc-slot-summary">${escapeHtml(statusSummary(w.slots))}</div>
      <div class="wc-slots">${slotsHTML}</div>
      <button type="button" class="wc-btn" id="wc-detail-add-slot">➕ Ajouter un exemplaire</button>
      ${sectionsHTML}
      ${tastingHTML}
    `;
  }

  _bindDetail(box, w) {
    const refresh = async () => {
      await this._fetchData();
      const updated = (this._data.whiskies || []).find((x) => x.id === w.id);
      if (!updated) { this._closeModal(); return; }
      box.innerHTML = this._detailHTML(updated);
      this._bindDetail(box, updated);
    };
    box.querySelector("#wc-detail-edit").addEventListener("click", () => {
      this._closeModal();
      this._openForm(w);
    });
    box.querySelector("#wc-detail-delete").addEventListener("click", async () => {
      if (!confirm(`Supprimer définitivement « ${w.name} » et tous ses exemplaires ?`)) return;
      try {
        await this._hass.callService(DOMAIN, "remove_whisky", { whisky_id: w.id });
        this._closeModal();
      } catch (err) {
        this._toast(box, `Erreur : ${(err && err.message) || err}`);
      }
    });
    box.querySelector("#wc-detail-add-slot").addEventListener("click", async () => {
      try {
        await this._hass.callService(DOMAIN, "add_slot", { whisky_id: w.id });
        await refresh();
      } catch (err) {
        this._toast(box, `Erreur : ${(err && err.message) || err}`);
      }
    });
    box.querySelectorAll(".wc-slot-open").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await this._hass.callService(DOMAIN, "open_bottle", { whisky_id: w.id, slot_idx: Number(btn.dataset.idx) });
          await refresh();
        } catch (err) {
          this._toast(box, `Erreur : ${(err && err.message) || err}`);
        }
      });
    });
    box.querySelectorAll(".wc-slot-finish").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await this._hass.callService(DOMAIN, "finish_bottle", { whisky_id: w.id, slot_idx: Number(btn.dataset.idx) });
          await refresh();
        } catch (err) {
          this._toast(box, `Erreur : ${(err && err.message) || err}`);
        }
      });
    });
    box.querySelectorAll(".wc-slot-remaining-save").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const idx = Number(btn.dataset.idx);
        const input = box.querySelector(`.wc-slot-remaining-input[data-idx="${idx}"]`);
        const pct = input ? Number(input.value) : NaN;
        if (!Number.isFinite(pct)) { this._toast(box, "Niveau restant invalide (0 à 100)."); return; }
        try {
          await this._hass.callService(DOMAIN, "update_remaining", { whisky_id: w.id, slot_idx: idx, remaining_percent: pct });
          await refresh();
        } catch (err) {
          this._toast(box, `Erreur : ${(err && err.message) || err}`);
        }
      });
    });
    box.querySelectorAll(".wc-slot-remove").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm("Retirer cet exemplaire ?")) return;
        try {
          await this._hass.callService(DOMAIN, "remove_slot", { whisky_id: w.id, slot_idx: Number(btn.dataset.idx) });
          await refresh();
        } catch (err) {
          this._toast(box, `Erreur : ${(err && err.message) || err}`);
        }
      });
    });
  }

  // ── Formulaire d'ajout / édition ─────────────────────────────────────────

  _openForm(existing) {
    const box = this._openModal(this._formHTML(existing));
    this._bindForm(box, existing);
  }

  _formHTML(existing) {
    const meta = (existing && existing.whisky_meta) || {};
    const val = (key) => {
      if (existing) {
        if (key in existing) return existing[key];
        if (key in meta) return meta[key];
      }
      return "";
    };
    const sections = existing ? FORM_SECTIONS : [...FORM_SECTIONS];
    const extra = existing ? [] : [CREATE_ONLY_SECTION];
    const renderField = (f) => {
      const current = val(f.key);
      const id = `wc-f-${f.key}`;
      if (f.type === "select") {
        const labels = f.optionLabels || {};
        const opts = f.options.map((o) =>
          `<option value="${o}" ${String(current) === o ? "selected" : ""}>${labels[o] || o}</option>`
        ).join("");
        return `<label class="wc-field"><span>${f.label}</span>
          <select id="${id}" data-key="${f.key}"><option value="">—</option>${opts}</select></label>`;
      }
      if (f.type === "tri") {
        const cur = triStateFromValue(current);
        return `<label class="wc-field"><span>${f.label}</span>
          <select id="${id}" data-key="${f.key}">
            <option value="" ${cur === "" ? "selected" : ""}>Non renseigné</option>
            <option value="true" ${cur === "true" ? "selected" : ""}>Oui</option>
            <option value="false" ${cur === "false" ? "selected" : ""}>Non</option>
          </select></label>`;
      }
      if (f.type === "textarea") {
        return `<label class="wc-field wc-field-wide"><span>${f.label}</span>
          <textarea id="${id}" data-key="${f.key}" rows="2">${current || ""}</textarea></label>`;
      }
      if (f.type === "checkbox") {
        return `<label class="wc-field wc-field-checkbox">
          <input type="checkbox" id="${id}" data-key="${f.key}" ${current ? "checked" : ""} />
          <span>${f.label}</span></label>`;
      }
      const listAttr = f.list ? `list="${f.list}"` : "";
      return `<label class="wc-field"><span>${f.label}</span>
        <input type="${f.type}" id="${id}" data-key="${f.key}" ${listAttr}
          step="${f.step || ""}" min="${f.min || ""}" max="${f.max || ""}"
          placeholder="${f.placeholder || ""}" value="${current === 0 ? 0 : (current || "")}" /></label>`;
    };
    const sectionsHTML = [...sections, ...extra].map((s) => `
      <fieldset class="wc-section">
        <legend>${s.title}</legend>
        <div class="wc-grid">${s.fields.map(renderField).join("")}</div>
      </fieldset>
    `).join("");

    return `
      <h2 class="wc-modal-title">${existing ? "Modifier le whisky" : "Ajouter un whisky"}</h2>
      <div class="wc-photo-row">
        <button type="button" class="wc-btn" id="wc-photo-cam">📷 Prendre une photo</button>
        <button type="button" class="wc-btn" id="wc-photo-lib">🖼️ Galerie</button>
        <span class="wc-photo-hint">Analyse l'étiquette (Gemini) — les résultats restent à valider avant tout enregistrement.</span>
        <!-- Deux inputs statiques distincts : l'attribut capture doit être présent dès la
             création (comme dans millesime-card.js) pour que l'appareil photo direct
             fonctionne de façon fiable sur Android — un seul input avec capture="environment"
             se rabat silencieusement sur la galerie sur certaines WebView. -->
        <input type="file" id="wc-photo-input" accept="image/*" hidden />
        <input type="file" id="wc-photo-input-cam" accept="image/*" capture="environment" hidden />
      </div>
      <div id="wc-recognition-panel"></div>
      <datalist id="whisky-cask-types">${CASK_TYPE_SUGGESTIONS.map((c) => `<option value="${c}">`).join("")}</datalist>
      <form id="wc-form">
        ${sectionsHTML}
        <div class="wc-actions">
          <button type="button" class="wc-btn" id="wc-cancel">Annuler</button>
          <button type="submit" class="wc-btn wc-btn-primary">${existing ? "Enregistrer" : "Ajouter à la collection"}</button>
        </div>
      </form>
    `;
  }

  _bindForm(box, existing) {
    box.querySelector("#wc-cancel").addEventListener("click", () => this._closeModal());

    const fileInput = box.querySelector("#wc-photo-input");
    const fileInputCam = box.querySelector("#wc-photo-input-cam");
    box.querySelector("#wc-photo-cam").addEventListener("click", async () => {
      // Appareil photo direct tenté en premier via getUserMedia (fiable sur
      // Android, contrairement au seul attribut capture) ; repli sur l'input
      // statique avec capture si getUserMedia est indisponible/refusé.
      const shot = await this._captureViaCamera(box);
      if (shot instanceof File) { this._onScanFile(box, shot); return; }
      if (shot === "cancel") return;
      fileInputCam.click();
    });
    box.querySelector("#wc-photo-lib").addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", (e) => this._onScanFile(box, e.target));
    fileInputCam.addEventListener("change", (e) => this._onScanFile(box, e.target));

    box.querySelector("#wc-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const raw = {};
      box.querySelectorAll("[data-key]").forEach((el) => {
        raw[el.dataset.key] = el.type === "checkbox" ? el.checked : el.value;
      });
      if (!raw.name || !String(raw.name).trim()) {
        this._toast(box, "Le nom du whisky est requis.");
        return;
      }
      const payload = buildWhiskyPayload(raw);
      try {
        if (existing) {
          await this._hass.callService(DOMAIN, "update_whisky", { whisky_id: existing.id, ...payload });
        } else {
          await this._hass.callService(DOMAIN, "add_whisky", payload);
        }
        this._closeModal();
      } catch (err) {
        this._toast(box, `Erreur : ${(err && err.message) || err}`);
      }
    });
  }

  _toast(box, message) {
    let t = box.querySelector(".wc-toast");
    if (!t) {
      t = document.createElement("div");
      t.className = "wc-toast";
      box.prepend(t);
    }
    t.textContent = message;
  }

  // ── Reconnaissance photo ──────────────────────────────────────────────────

  // Accepte soit un <input type=file> (parcours galerie / input statique
  // avec capture), soit directement un File (photo issue du modal caméra
  // getUserMedia — voir _captureViaCamera).
  _onScanFile(box, inputOrFile) {
    const file = inputOrFile instanceof File ? inputOrFile : (inputOrFile.files && inputOrFile.files[0]);
    if (!file) return;
    const reader = new FileReader();
    reader.onerror = () => this._toast(box, "Impossible de lire la photo.");
    reader.onload = async () => {
      const dataUrl = String(reader.result || "");
      const b64 = dataUrl.split(",")[1] || "";
      const mime = file.type || "image/jpeg";
      if (!b64) { this._toast(box, "Photo vide ou illisible."); return; }
      this._showRecognitionLoading(box);
      try {
        const resp = await this._hass.connection.sendMessagePromise({
          type: `${DOMAIN}/analyze_photo`, image_b64: b64, mime_type: mime,
        });
        this._showRecognitionResult(box, resp);
      } catch (err) {
        this._showRecognitionError(box, "service_unavailable");
      }
    };
    reader.readAsDataURL(file);
    if (!(inputOrFile instanceof File)) inputOrFile.value = "";
  }

  // ── Repli caméra via getUserMedia (Android) ─────────────────────────────
  // Sur certains appareils Android, la WebView ouvre la galerie même avec un
  // input statique portant l'attribut capture. getUserMedia est donc tenté
  // en premier — c'est le seul chemin qui garantit l'ouverture de l'appareil
  // photo. L'API n'existe qu'en contexte sécurisé (HTTPS / app compagnon en
  // URL externe / localhost) : en HTTP local, on prévient explicitement
  // l'utilisateur avant le repli galerie. (Porté de millesime-card.js,
  // même correctif que l'issue #7 de Millésime.)
  _cameraSupported() {
    return !!navigator.mediaDevices?.getUserMedia;
  }

  _cameraFallbackNotice(box, reason) {
    if (reason === "insecure") {
      this._toast(box,
        "Photo depuis la galerie : l'accès direct à l'appareil photo est réservé " +
        "aux connexions sécurisées (https). Ce n'est pas un défaut de Whisky — " +
        "prenez la photo avec votre appareil photo puis choisissez-la dans la galerie, " +
        "ou accédez à Home Assistant en https (URL externe / Nabu Casa) pour la prise directe.");
    } else if (reason === "denied") {
      this._toast(box,
        "Accès caméra refusé — vérifiez les permissions de l'app Home Assistant " +
        "(Réglages → Applications → Home Assistant → Autorisations → Appareil photo). " +
        "En attendant, la photo depuis la galerie fonctionne.");
    }
  }

  // Résout avec : File (photo capturée) | "cancel" (fermé par l'utilisateur)
  // | null (échec technique → l'appelant retombe sur l'input statique).
  async _captureViaCamera(box) {
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      this._cameraFallbackNotice(box, "insecure");
      return null;
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false,
      });
    } catch (err) {
      console.warn("[Whisky] getUserMedia indisponible :", err);
      this._cameraFallbackNotice(box,
        (err && (err.name === "NotAllowedError" || err.name === "SecurityError")) ? "denied" : "insecure");
      return null;
    }
    return new Promise((resolve) => {
      const overlay = document.createElement("div");
      overlay.style.cssText = "position:fixed;inset:0;z-index:100000;background:#000;display:flex;flex-direction:column;";
      const video = document.createElement("video");
      video.autoplay = true; video.playsInline = true; video.muted = true;
      video.style.cssText = "flex:1;min-height:0;width:100%;object-fit:contain;background:#000;";
      video.srcObject = stream;
      const bar = document.createElement("div");
      bar.style.cssText = "display:flex;gap:14px;justify-content:center;align-items:center;background:#111;" +
        "padding:16px 16px calc(env(safe-area-inset-bottom, 0px) + 16px);";
      const mkBtn = (txt, primary) => {
        const b = document.createElement("button");
        b.type = "button"; b.textContent = txt;
        b.style.cssText = "border:none;border-radius:999px;padding:14px 26px;font-size:1em;cursor:pointer;" +
          (primary ? "background:linear-gradient(135deg,#d97706,#92400e);color:#fff;font-weight:600;" : "background:#333;color:#ddd;");
        return b;
      };
      const btnShot = mkBtn("📷 Capturer", true);
      const btnCancel = mkBtn("Annuler", false);
      const done = (result) => {
        try { stream.getTracks().forEach((t) => t.stop()); } catch (err) { /* déjà arrêté */ }
        overlay.remove();
        resolve(result);
      };
      btnShot.addEventListener("click", () => {
        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth || 1280;
        canvas.height = video.videoHeight || 720;
        canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
        canvas.toBlob((blob) => {
          done(blob ? new File([blob], "capture.jpg", { type: "image/jpeg" }) : null);
        }, "image/jpeg", 0.92);
      });
      btnCancel.addEventListener("click", () => done("cancel"));
      bar.appendChild(btnCancel);
      bar.appendChild(btnShot);
      overlay.appendChild(video);
      overlay.appendChild(bar);
      document.body.appendChild(overlay);
    });
  }

  _showRecognitionLoading(box) {
    box.querySelector("#wc-recognition-panel").innerHTML =
      `<div class="wc-recog-panel wc-recog-loading">🔎 Analyse de la photo en cours…</div>`;
  }

  _showRecognitionError(box, code) {
    const msg = ERROR_MESSAGES[code] || "Erreur inconnue.";
    box.querySelector("#wc-recognition-panel").innerHTML =
      `<div class="wc-recog-panel wc-recog-error">⚠️ ${msg}</div>`;
  }

  _showRecognitionResult(box, resp) {
    const panel = box.querySelector("#wc-recognition-panel");
    if (resp.error) { this._showRecognitionError(box, resp.error); return; }
    if (!resp.result) {
      panel.innerHTML = `<div class="wc-recog-panel wc-recog-empty">Aucune information exploitable identifiée sur cette photo — complétez à la main.</div>`;
      return;
    }
    const result = resp.result;
    const fields = recognitionFieldList(result);
    const globalConf = confidenceTier(result.confidence_score);
    const rows = fields.map((f) => {
      const tier = confidenceTier(f.confidence);
      const currentEl = box.querySelector(`[data-key="${f.key}"]`);
      const alreadyFilled = currentEl && (currentEl.type === "checkbox" ? currentEl.checked : String(currentEl.value || "").trim() !== "");
      return `
        <label class="wc-recog-row">
          <input type="checkbox" class="wc-recog-check" data-key="${f.key}" data-value="${String(f.value).replace(/"/g, "&quot;")}" ${alreadyFilled ? "" : "checked"} />
          <span class="wc-recog-field">${f.key}</span>
          <span class="wc-recog-value">${f.value}</span>
          <span class="wc-conf-badge ${tier.cls}">${tier.label}</span>
        </label>`;
    }).join("");
    panel.innerHTML = `
      <div class="wc-recog-panel">
        <div class="wc-recog-title">Résultats de la reconnaissance
          <span class="wc-conf-badge ${globalConf.cls}">Confiance globale : ${globalConf.label}</span>
        </div>
        <p class="wc-recog-note">Décochez les champs à ne pas appliquer — rien n'est enregistré tant que vous n'avez pas cliqué sur « Appliquer » puis soumis le formulaire.</p>
        <div class="wc-recog-rows">${rows || "<em>Aucun champ exploitable.</em>"}</div>
        ${fields.length ? `<button type="button" class="wc-btn wc-btn-primary" id="wc-recog-apply">Appliquer les champs cochés</button>` : ""}
      </div>
    `;
    const applyBtn = panel.querySelector("#wc-recog-apply");
    if (applyBtn) {
      applyBtn.addEventListener("click", () => {
        const selected = [...panel.querySelectorAll(".wc-recog-check:checked")].map((c) => c.dataset.key);
        for (const key of selected) {
          const el = box.querySelector(`[data-key="${key}"]`);
          if (!el) continue;
          const value = result[key];
          if (TRI_FIELDS.has(key)) el.value = triStateFromValue(value);
          else el.value = value;
        }
        this._toast(box, `${selected.length} champ(s) appliqué(s) — vérifiez puis enregistrez.`);
      });
    }
  }
}

const CARD_CSS = `
  :host { display: block; }
  .wc-card {
    position: relative;
    background: var(--card-background-color, #fff);
    color: var(--primary-text-color, #000);
    border-radius: var(--ha-card-border-radius, 12px);
    padding: 16px;
    padding-top: 20px;
    font-family: var(--paper-font-body1_-_font-family, sans-serif);
    container-type: inline-size;
    overflow: hidden;
  }
  .wc-card::before {
    content: "";
    position: absolute;
    top: 0; left: 0; right: 0; height: 4px;
    background: linear-gradient(90deg, #f2b84b, #d97706 45%, #92400e);
  }
  .wc-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
  .wc-header-actions { display: flex; gap: 8px; flex-wrap: wrap; }
  .wc-title { font-size: 1.15em; font-weight: 700; letter-spacing: .01em; }
  .wc-hint { opacity: .75; font-size: .9em; margin-top: 8px; }
  .wc-btn {
    border: 1px solid var(--divider-color, #ccc); background: var(--secondary-background-color, #f2f2f2);
    color: var(--primary-text-color, #000); border-radius: 8px; padding: 8px 14px; cursor: pointer; font-size: .95em;
    transition: border-color .15s ease, background .15s ease;
  }
  .wc-btn:hover { border-color: #d97706; }
  .wc-btn-primary {
    background: linear-gradient(135deg, #d97706, #92400e); color: #fff; border-color: transparent;
    box-shadow: 0 1px 4px rgba(146, 64, 14, .35);
  }
  .wc-btn-primary:hover { background: linear-gradient(135deg, #f2a638, #b45309); }
  .wc-toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
  .wc-toolbar .wc-search { flex: 1 1 200px; }
  .wc-toolbar input, .wc-toolbar select {
    border: 1px solid var(--divider-color, #ccc); border-radius: 8px; padding: 6px 10px; font: inherit;
    background: var(--card-background-color, #fff); color: inherit;
  }
  .wc-toolbar input:focus, .wc-toolbar select:focus { outline: none; border-color: #d97706; }
  .wc-filter-fav { display: flex; align-items: center; gap: 6px; font-size: .9em; white-space: nowrap; }
  .wc-empty { opacity: .7; padding: 24px 8px; text-align: center; font-size: .95em; }
  .wc-grid-tiles {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; margin-top: 14px;
  }
  @container (max-width: 380px) {
    .wc-grid-tiles { grid-template-columns: 1fr; }
  }
  .wc-tile {
    display: flex; flex-direction: column; border: 1px solid var(--divider-color, #ddd); border-radius: 10px;
    overflow: hidden; cursor: pointer; background: var(--secondary-background-color, #fafafa);
    transition: box-shadow .15s ease, transform .15s ease, border-color .15s ease;
  }
  .wc-tile:hover { box-shadow: 0 3px 12px rgba(146, 64, 14, .25); transform: translateY(-1px); border-color: #d97706; }
  .wc-tile-img { width: 100%; height: 120px; object-fit: cover; display: block; background: var(--divider-color, #eee); }
  .wc-tile-img-placeholder {
    display: flex; align-items: center; justify-content: center; font-size: 2.4em;
    background: linear-gradient(135deg, #f2c675, #b45309 65%, #6b3410);
  }
  .wc-tile-body { padding: 8px 10px 10px; display: flex; flex-direction: column; gap: 2px; }
  .wc-tile-name { font-weight: 600; font-size: .95em; }
  .wc-tile-sub { font-size: .82em; opacity: .75; }
  .wc-tile-status { font-size: .78em; opacity: .8; margin-top: 4px; }
  .wc-tile-rating { font-size: .85em; color: #d97706; margin-top: 2px; }
`;

const MODAL_CSS = `
  * { box-sizing: border-box; }
  .wc-modal-box {
    background: var(--card-background-color, #fff); color: var(--primary-text-color, #000);
    border-radius: 12px; padding: 20px; max-width: 720px; width: 100%; max-height: 90vh; overflow: auto;
    font-family: var(--paper-font-body1_-_font-family, sans-serif);
    border-top: 4px solid #d97706;
  }
  .wc-modal-title { margin: 0 0 12px; font-size: 1.2em; }
  .wc-section { border: 1px solid var(--divider-color, #ddd); border-radius: 10px; margin-bottom: 12px; padding: 10px 14px; }
  .wc-section legend { font-weight: 600; padding: 0 6px; color: #b45309; }
  .wc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
  .wc-field { display: flex; flex-direction: column; gap: 4px; font-size: .85em; }
  .wc-field span { opacity: .8; }
  .wc-field input, .wc-field select, .wc-field textarea {
    border: 1px solid var(--divider-color, #ccc); border-radius: 6px; padding: 6px 8px; font: inherit;
    background: var(--card-background-color, #fff); color: inherit;
  }
  .wc-field input:focus, .wc-field select:focus, .wc-field textarea:focus { outline: none; border-color: #d97706; }
  .wc-field-wide { grid-column: 1 / -1; }
  .wc-field-checkbox { flex-direction: row; align-items: center; gap: 8px; }
  .wc-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 12px; }
  .wc-photo-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
  .wc-photo-hint { font-size: .8em; opacity: .7; }
  .wc-recog-panel { border: 1px dashed #b45309; border-radius: 10px; padding: 10px 12px; margin-bottom: 14px; font-size: .88em; background: rgba(217, 119, 6, .06); }
  .wc-recog-title { font-weight: 600; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .wc-recog-note { opacity: .75; margin: 6px 0; }
  .wc-recog-row { display: grid; grid-template-columns: auto 140px 1fr auto; align-items: center; gap: 8px; padding: 4px 0; }
  .wc-recog-field { opacity: .7; }
  .wc-conf-badge { font-size: .75em; padding: 2px 8px; border-radius: 999px; white-space: nowrap; }
  .conf-high { background: #1e7e34; color: #fff; }
  .conf-mid { background: #b8860b; color: #fff; }
  .conf-low { background: #a33; color: #fff; }
  .conf-none { background: #888; color: #fff; }
  .wc-toast { background: #a33; color: #fff; border-radius: 8px; padding: 8px 12px; margin-bottom: 10px; font-size: .9em; }
  .wc-overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,.5); display: flex; align-items: center; justify-content: center;
    z-index: 1000; padding: 16px;
  }
  .wc-detail-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
  .wc-detail-actions { display: flex; gap: 8px; flex-wrap: wrap; }
  .wc-detail-img { width: 100%; max-height: 220px; object-fit: cover; border-radius: 10px; margin: 10px 0; display: block; }
  .wc-slot-summary { opacity: .8; font-size: .9em; margin: 6px 0; }
  .wc-slots { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; }
  .wc-slot {
    border: 1px solid var(--divider-color, #ddd); border-radius: 8px; padding: 6px 10px; font-size: .85em;
  }
  .wc-slot.wc-slot-empty { opacity: .7; border-style: dashed; }
  .wc-slot-row { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 8px; }
  .wc-slot-dot { color: #d97706; font-weight: 700; }
  .wc-slot-place { grid-column: 2; }
  .wc-slot-status { grid-column: 1 / -1; opacity: .75; font-size: .92em; }
  .wc-slot-actions { grid-column: 3; display: flex; gap: 6px; flex-wrap: wrap; justify-self: end; }
  .wc-slot-actions .wc-btn { padding: 4px 10px; font-size: .85em; }
  .wc-slot-remaining-row {
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: 6px; padding-top: 6px;
    border-top: 1px dashed var(--divider-color, #ddd); font-size: .88em;
  }
  .wc-slot-remaining-label { display: flex; align-items: center; gap: 6px; opacity: .85; }
  .wc-slot-remaining-input { width: 4.5em; padding: 3px 6px; }
  .wc-slot-remaining-save { padding: 3px 10px; font-size: .85em; }
  .wc-detail-row { display: flex; justify-content: space-between; gap: 12px; padding: 3px 0; font-size: .88em; }
  .wc-detail-label { opacity: .7; }
  .wc-detail-value { text-align: right; }
  .wc-stat-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 10px; margin: 14px 0; }
  .wc-stat-tile {
    border: 1px solid var(--divider-color, #ddd); border-radius: 10px; padding: 10px; text-align: center;
    background: var(--secondary-background-color, #fafafa);
  }
  .wc-stat-num { font-size: 1.4em; font-weight: 700; color: #b45309; }
  .wc-stat-label { font-size: .78em; opacity: .75; margin-top: 2px; }
  .wc-stat-bar-row { display: grid; grid-template-columns: 130px 1fr auto; align-items: center; gap: 8px; padding: 3px 0; font-size: .85em; }
  .wc-stat-bar-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .wc-stat-bar-track { height: 8px; border-radius: 999px; background: var(--divider-color, #eee); overflow: hidden; }
  .wc-stat-bar-fill { display: block; height: 100%; background: linear-gradient(90deg, #f2b84b, #92400e); }
  .wc-stat-bar-count { opacity: .75; min-width: 2ch; text-align: right; }
`;

if (typeof customElements !== "undefined") {
  customElements.define("whisky-card", WhiskyCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "whisky-card",
    name: "Whisky — Collection",
    description: "Gestion d'une collection de whiskies : fiches détaillées, reconnaissance photo, statistiques.",
  });
}

// ── Export pour les tests Node (voir tests/) — sans effet en navigateur ────
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    WHISKY_TYPE_VALUES, CASK_TYPE_SUGGESTIONS, TRI_FIELDS, NUMBER_FIELDS,
    triStateToPayload, triStateFromValue, numberOrUndefined,
    buildWhiskyPayload, confidenceTier, recognitionFieldList,
    applyRecognitionSelection, FORM_SECTIONS, CREATE_ONLY_SECTION,
    escapeHtml, STATUS_ORDER, STATUS_DOT, statusBreakdown, statusSummary,
    ratingStars, metaLine, tileHTML, detailRows,
    matchesQuery, matchesStatusFilter, filterWhiskies, breakdownJS,
    computeStats, topBreakdown,
  };
}
