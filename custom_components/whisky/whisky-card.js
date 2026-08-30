// Whisky — Carte Lovelace
// Projet indépendant dérivé de Millésime (github.com/Redsklns/ha-millesime,
// licence MIT) : même style d'architecture (Web Component vanilla, Shadow
// DOM, rendu par template strings), vocabulaire entièrement whisky.
//
// Commit 6/12 : formulaire d'ajout/édition complet (9 sections) + intégration
// de la reconnaissance photo Gemini, avec écran de validation utilisateur
// avant tout enregistrement (brief §3). La liste/fiche détail arrivent au
// commit 7, les statistiques/filtres au commit 8.
//
// Les fonctions PURES (sans DOM) sont exportées en fin de fichier pour être
// testées avec Node (voir tests/), sans dépendre d'un navigateur ou de HA.

const DOMAIN = "whisky";
const VERSION = "0.6.0";

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

// ── Composant carte ───────────────────────────────────────────────────────

class WhiskyCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = { cellars: [], whiskies: [], tasting_log: [] };
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

  // ── Rendu principal (squelette — la vraie liste arrive au commit 7) ──────

  _render() {
    const whiskies = (this._data && this._data.whiskies) || [];
    const total = whiskies.reduce((n, w) => n + ((w.slots && w.slots.length) || 0), 0);
    this.shadowRoot.innerHTML = `
      <style>${CARD_CSS}</style>
      <div class="wc-card">
        <div class="wc-header">
          <div class="wc-title">🥃 Whisky — Collection</div>
          <button class="wc-btn wc-btn-primary" id="wc-add">➕ Ajouter</button>
        </div>
        <div class="wc-hint">${whiskies.length} fiche(s), ${total} bouteille(s) — vue liste et statistiques à venir (commits 7-8).</div>
      </div>
    `;
    const addBtn = this.shadowRoot.getElementById("wc-add");
    if (addBtn) addBtn.addEventListener("click", () => this._openForm(null));
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
        <button type="button" class="wc-btn" id="wc-photo-btn">📷 Identifier par photo</button>
        <span class="wc-photo-hint">Analyse l'étiquette (Gemini) — les résultats restent à valider avant tout enregistrement.</span>
        <input type="file" id="wc-photo-input" accept="image/*" capture="environment" hidden />
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
    box.querySelector("#wc-photo-btn").addEventListener("click", () => box.querySelector("#wc-photo-input").click());
    box.querySelector("#wc-photo-input").addEventListener("change", (e) => this._onScanFile(box, e.target));

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

  _onScanFile(box, input) {
    const file = input.files && input.files[0];
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
    input.value = "";
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
    background: var(--card-background-color, #fff);
    color: var(--primary-text-color, #000);
    border-radius: var(--ha-card-border-radius, 12px);
    padding: 16px;
    font-family: var(--paper-font-body1_-_font-family, sans-serif);
    container-type: inline-size;
  }
  .wc-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .wc-title { font-size: 1.15em; font-weight: 700; }
  .wc-hint { opacity: .75; font-size: .9em; margin-top: 8px; }
  .wc-btn {
    border: 1px solid var(--divider-color, #ccc); background: var(--secondary-background-color, #f2f2f2);
    color: var(--primary-text-color, #000); border-radius: 8px; padding: 8px 14px; cursor: pointer; font-size: .95em;
  }
  .wc-btn-primary { background: var(--primary-color, #7B1D2E); color: #fff; border-color: transparent; }
`;

const MODAL_CSS = `
  * { box-sizing: border-box; }
  .wc-modal-box {
    background: var(--card-background-color, #fff); color: var(--primary-text-color, #000);
    border-radius: 12px; padding: 20px; max-width: 720px; width: 100%; max-height: 90vh; overflow: auto;
    font-family: var(--paper-font-body1_-_font-family, sans-serif);
  }
  .wc-modal-title { margin: 0 0 12px; font-size: 1.2em; }
  .wc-section { border: 1px solid var(--divider-color, #ddd); border-radius: 10px; margin-bottom: 12px; padding: 10px 14px; }
  .wc-section legend { font-weight: 600; padding: 0 6px; }
  .wc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
  .wc-field { display: flex; flex-direction: column; gap: 4px; font-size: .85em; }
  .wc-field span { opacity: .8; }
  .wc-field input, .wc-field select, .wc-field textarea {
    border: 1px solid var(--divider-color, #ccc); border-radius: 6px; padding: 6px 8px; font: inherit;
    background: var(--card-background-color, #fff); color: inherit;
  }
  .wc-field-wide { grid-column: 1 / -1; }
  .wc-field-checkbox { flex-direction: row; align-items: center; gap: 8px; }
  .wc-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 12px; }
  .wc-photo-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
  .wc-photo-hint { font-size: .8em; opacity: .7; }
  .wc-recog-panel { border: 1px dashed var(--primary-color, #7B1D2E); border-radius: 10px; padding: 10px 12px; margin-bottom: 14px; font-size: .88em; }
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
  };
}
