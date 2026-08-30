"""Whisky v0.1.0 — Collection de whiskies pour Home Assistant.

Projet indépendant dérivé de Millésime (github.com/Redsklns/ha-millesime,
MIT) : même style d'architecture (stockage JSON local, casiers/emplacements
agnostiques, carte Lovelace auto-servie), vocabulaire et modèle de données
entièrement propres au whisky.

Commit 1/12 : scaffold minimal — stockage vide, carte auto-servie, aucune
logique métier. Les commits suivants ajoutent le modèle de données (2), les
services CRUD (3), les capteurs (4), la reconnaissance Gemini (5), etc.
"""
from __future__ import annotations

import json
import logging
import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

DOMAIN    = "whisky"
PLATFORMS = ["sensor"]
DATA_FILE = "whisky_data.json"
VERSION   = "0.1.0"

# ── Modèle de données minimal (étoffé au commit 2) ───────────────────────────
# cellars[] : casiers/étagères de rangement (structure physique, réutilisée
#             telle quelle du fork Millésime — déjà agnostique du contenu).
# whiskies[]: liste des fiches whisky (vide pour l'instant).
DEFAULT_DATA: dict = {
    "cellars": [{"id": "main", "name": "Collection", "racks": []}],
    "whiskies": [],
    "tasting_log": [],
}


def _path(hass: HomeAssistant) -> str:
    return hass.config.path(DATA_FILE)


def _load(hass: HomeAssistant) -> dict:
    try:
        p = _path(hass)
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:
        _LOGGER.error("Whisky — erreur lecture : %s", exc)
    return json.loads(json.dumps(DEFAULT_DATA))


def _save(hass: HomeAssistant, data: dict) -> None:
    try:
        with open(_path(hass), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        _LOGGER.error("Whisky — erreur sauvegarde : %s", exc)


# ── Carte Lovelace : auto-service (repris à l'identique du fork Millésime) ──

_CARD_URL_PATH = "/whisky/whisky-card.js"


async def _async_register_card(hass: HomeAssistant) -> None:
    """Sert whisky-card.js depuis l'intégration et l'ajoute aux ressources Lovelace."""
    card_path = os.path.join(os.path.dirname(__file__), "whisky-card.js")
    if not os.path.exists(card_path):
        _LOGGER.error("Whisky : whisky-card.js INTROUVABLE (%s)", card_path)
        return

    url = f"{_CARD_URL_PATH}?v={VERSION}"

    served = hass.data[DOMAIN].get("_card_http_done")
    if not served:
        ok = False
        try:
            from homeassistant.components.http import HomeAssistantView
            from aiohttp import web

            class _WhiskyCardView(HomeAssistantView):
                url = _CARD_URL_PATH
                name = "whisky:card"
                requires_auth = False

                async def get(self, request):
                    return web.FileResponse(card_path)

            hass.http.register_view(_WhiskyCardView())
            ok = True
            _LOGGER.warning("Whisky : carte servie via vue HTTP sur %s", _CARD_URL_PATH)
        except Exception as exc:
            _LOGGER.warning("Whisky : vue HTTP impossible (%s), essai chemin statique", exc)
            try:
                from homeassistant.components.http import StaticPathConfig
                await hass.http.async_register_static_paths(
                    [StaticPathConfig(_CARD_URL_PATH, card_path, False)]
                )
                ok = True
                _LOGGER.warning("Whisky : carte servie via chemin statique")
            except Exception as exc2:
                _LOGGER.error("Whisky : impossible de servir la carte (%s)", exc2)

        if ok:
            hass.data[DOMAIN]["_card_http_done"] = True

    try:
        lovelace = hass.data.get("lovelace")
        resources = getattr(lovelace, "resources", None) if lovelace else None

        if resources is None:
            from homeassistant.components.frontend import add_extra_js_url
            add_extra_js_url(hass, url)
            _LOGGER.warning("Whisky : carte injectée (Lovelace mode YAML) → %s", url)
            return

        if not resources.loaded:
            await resources.async_load()

        existing = [r for r in resources.async_items() if _CARD_URL_PATH in (r.get("url") or "")]
        if existing:
            for r in existing:
                if r.get("url") != url:
                    await resources.async_update_item(r["id"], {"res_type": "module", "url": url})
                    _LOGGER.warning("Whisky : ressource mise à jour → %s", url)
        else:
            await resources.async_create_item({"res_type": "module", "url": url})
            _LOGGER.warning("Whisky : ressource créée → %s", url)
    except Exception as exc:
        _LOGGER.error("Whisky : ressource Lovelace impossible (%s) — ajoutez %s à la main",
                      exc, url)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Initialise Whisky."""
    hass.data.setdefault(DOMAIN, {})
    data = await hass.async_add_executor_job(_load, hass)

    gemini_key = (
        entry.options.get("gemini_api_key")
        or entry.data.get("gemini_api_key")
        or ""
    ).strip()

    hass.data[DOMAIN][entry.entry_id] = {
        "data":       data,
        "gemini_key": gemini_key,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    await _async_register_card(hass)

    _LOGGER.info("Whisky v%s démarré (%d fiche(s))", VERSION, len(data.get("whiskies", [])))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    new_key = (entry.options.get("gemini_api_key") or "").strip()
    hass.data[DOMAIN][entry.entry_id]["gemini_key"] = new_key
    _LOGGER.info("Whisky — clé Gemini mise à jour")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return ok
