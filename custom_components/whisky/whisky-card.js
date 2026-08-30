// Whisky — Carte Lovelace
// Commit 1/12 : squelette minimal. Le contenu réel arrive aux commits 6-8
// (formulaire, liste/détail, statistiques/filtres).
//
// Projet indépendant dérivé de Millésime (github.com/Redsklns/ha-millesime,
// licence MIT) : même style d'architecture (Web Component vanilla, Shadow
// DOM, rendu par template strings), vocabulaire entièrement whisky.

const DOMAIN = "whisky";
const VERSION = "0.1.0";

class WhiskyCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  setConfig(config) {
    this._config = config || {};
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._rendered) this._render();
  }

  getCardSize() {
    return 3;
  }

  _render() {
    this._rendered = true;
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        .mm-card {
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color, #000);
          border-radius: var(--ha-card-border-radius, 12px);
          padding: 16px;
          font-family: var(--paper-font-body1_-_font-family, sans-serif);
        }
        .mm-title { font-size: 1.1em; font-weight: 600; margin-bottom: 8px; }
        .mm-hint { opacity: .7; font-size: .9em; }
      </style>
      <div class="mm-card">
        <div class="mm-title">🥃 Whisky — Collection</div>
        <div class="mm-hint">Carte en construction (v${VERSION}) — le contenu arrive dans les prochains commits.</div>
      </div>
    `;
  }
}

customElements.define("whisky-card", WhiskyCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "whisky-card",
  name: "Whisky — Collection",
  description: "Gestion d'une collection de whiskies : fiches détaillées, reconnaissance photo, statistiques.",
});
