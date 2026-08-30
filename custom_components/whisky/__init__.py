"""Whisky v0.2.0 — Collection de whiskies pour Home Assistant.

Projet indépendant dérivé de Millésime (github.com/Redsklns/ha-millesime,
MIT) : même style d'architecture (stockage JSON local, casiers/emplacements
agnostiques, carte Lovelace auto-servie), vocabulaire et modèle de données
entièrement propres au whisky.

Commit 2/12 : modèle de données complet (fiche whisky, casiers/emplacements,
constantes de classification) + helpers de stockage. Pas encore de services
d'écriture exposés à l'utilisateur (commit 3) ni de capteurs (commit 4).
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

DOMAIN    = "whisky"
PLATFORMS = ["sensor"]
DATA_FILE = "whisky_data.json"
VERSION   = "0.2.0"

# ── Classification whisky (brief §2) ──────────────────────────────────────────
# Liste FERMÉE utilisée pour valider whisky_meta.whisky_type. "Other" couvre
# tout style non listé sans bloquer la saisie.
WHISKY_TYPE_VALUES = [
    "Single Malt", "Blended Malt", "Blended Whisky", "Single Grain",
    "Bourbon", "Rye", "Tennessee Whiskey", "Corn Whiskey",
    "Irish Single Malt", "Irish Pot Still", "Japanese Whisky",
    "World Whisky", "Other",
]

# Exemples de fûts (brief §2) — INDICATIF seulement : le champ cask_type
# reste une chaîne libre (trop de variantes réelles pour une liste fermée,
# ex. "2nd Fill Oloroso Sherry Hogshead"), cette liste alimente uniquement
# l'autocomplétion côté carte (commit 6).
CASK_TYPE_SUGGESTIONS = [
    "Bourbon", "First Fill Bourbon", "Refill Bourbon", "Sherry", "Oloroso",
    "PX", "Port", "Madeira", "Wine", "Virgin Oak", "Mizunara",
    "Multiple Casks", "Other",
]

# État d'une bouteille PHYSIQUE (porté par chaque slot, pas par la fiche —
# voir _mk_slot ci-dessous : on peut posséder plusieurs exemplaires du même
# whisky dans des états différents).
BOTTLE_STATUS_VALUES = ("sealed", "opened", "finished")

# ── Modèle de données ─────────────────────────────────────────────────────────
# cellars[] : casiers/étagères de rangement (structure physique, réutilisée
#             telle quelle du fork Millésime — déjà agnostique du contenu).
# whiskies[]: fiches whisky. Une fiche = un produit ; slots[] = ses exemplaires
#             physiques (comme wines[]/slots[] côté Millésime).
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


def _uid() -> str:
    return str(uuid.uuid4())[:8]


# ── Helpers casiers/emplacements (repris à l'identique de Millésime : la
#    structure de rangement physique est déjà agnostique du contenu) ────────

def _cellars(d: dict) -> list[dict]:
    """Liste des caves/armoires ; garantit qu'il en existe toujours une."""
    cs = d.setdefault("cellars", [])
    if not cs:
        cs.append({"id": "main", "name": "Collection", "racks": []})
    return cs


def _cellar(d: dict, cellar_id: str | None = None) -> dict:
    """Cave d'identifiant donné, ou la première à défaut."""
    cs = _cellars(d)
    if cellar_id:
        for c in cs:
            if c.get("id") == cellar_id:
                return c
    return cs[0]


def _all_racks(d: dict) -> list[dict]:
    """Tous les casiers, toutes caves confondues (les rack_id restent uniques)."""
    return [r for c in _cellars(d) for r in c.get("racks", [])]


def _rack_capacity(rk: dict) -> int:
    """Capacité d'un casier : colonnes × étagères × niveaux (superposition)."""
    levels = max(1, min(4, int(rk.get("levels", 1) or 1)))
    return rk.get("columns", 8) * rk.get("shelves", 2) * levels


def _slot_taken(d: dict, rack_id: str, slot: int,
                exclude_whisky_id: str | None = None,
                exclude_slot_idx: int | None = None) -> bool:
    """Retourne True si l'emplacement est déjà occupé dans ce casier."""
    for w in d.get("whiskies", []):
        for i, s in enumerate(w.get("slots", [])):
            if s["rack_id"] == rack_id and s["slot"] == slot:
                if w["id"] == exclude_whisky_id and exclude_slot_idx is not None and i == exclude_slot_idx:
                    continue
                return True
    return False


def _mk_slot(rack_id: str, slot: int, comment=None, size=None,
             bottle_status: str = "sealed") -> dict:
    """Construit un emplacement = UNE bouteille physique.

    bottle_status/opened_date/remaining_percent vivent ICI (par exemplaire),
    pas sur la fiche whisky : on peut posséder plusieurs bouteilles du même
    whisky dans des états différents (une ouverte, deux scellées).
    """
    s: dict = {
        "rack_id": rack_id,
        "slot": slot,
        "bottle_status": bottle_status if bottle_status in BOTTLE_STATUS_VALUES else "sealed",
    }
    if comment:
        s["comment"] = str(comment)
    if size:
        s["size"] = str(size)
    return s


def _new_whisky_record(name: str, whisky_meta: dict | None = None, **fields) -> dict:
    """Construit une fiche whisky vierge (champs communs + whisky_meta imbriqué).

    Utilisé par les services (commit 3) et par les tests (commit 10) — centralise
    la forme exacte de l'objet pour éviter toute divergence entre les deux.
    """
    record = {
        "id":               _uid(),
        "beverage_type":    "whisky",
        "name":             name,
        "image_url":        fields.get("image_url", ""),
        "label_image_url":  fields.get("label_image_url", ""),
        "price":            float(fields.get("price", 0) or 0),
        "current_value":    float(fields.get("current_value", 0) or 0),
        "currency":         fields.get("currency", "EUR"),
        "purchase_date":    fields.get("purchase_date", ""),
        "purchase_location":fields.get("purchase_location", ""),
        "storage_location": fields.get("storage_location", ""),
        "notes":            fields.get("notes", ""),
        "favorite":         bool(fields.get("favorite", False)),
        "rating":           float(fields.get("rating", 0) or 0),
        "barcode":          fields.get("barcode", ""),
        "external_id":      fields.get("external_id", ""),
        "external_url":     fields.get("external_url", ""),
        "added_date":       fields.get("added_date") or datetime.now().strftime("%Y-%m-%d"),
        "slots":            fields.get("slots", []),
        "whisky_meta": {
            "distillery":          "",
            "bottler":              "",
            "brand":                "",
            "expression":           "",
            "country":              "",
            "region":               "",
            "distillery_location":  "",
            "whisky_type":          "",
            "age":                  "",
            "vintage":              "",
            "bottling_year":        "",
            "abv":                  0.0,
            "volume_ml":            700,
            "chill_filtered":       None,
            "natural_colour":       None,
            "peated":               None,
            "peat_level":           "",
            "ppm":                  0,
            "maturation":           "",
            "cask_type":            "",
            "cask_number":          "",
            "finish":               "",
            "maturation_years":     "",
            "batch":                "",
            "edition":              "",
            "bottle_number":        "",
            "number_of_bottles":    "",
            "limited_edition":      False,
            "independent_bottler":  False,
            "tasting_notes":        "",
            "nose_notes":           "",
            "palate_notes":         "",
            "finish_notes":         "",
            "whiskybase_id":        "",
            "whiskybase_url":       "",
            **(whisky_meta or {}),
        },
    }
    return record


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
