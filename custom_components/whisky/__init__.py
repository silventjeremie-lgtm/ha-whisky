"""Whisky v0.4.0 — Collection de whiskies pour Home Assistant.

Projet indépendant dérivé de Millésime (github.com/Redsklns/ha-millesime,
MIT) : même style d'architecture (stockage JSON local, casiers/emplacements
agnostiques, carte Lovelace auto-servie), vocabulaire et modèle de données
entièrement propres au whisky.

Commit 4/12 : + capteurs Home Assistant (sensor.py). Pas encore de
reconnaissance photo (commit 5).
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

_LOGGER = logging.getLogger(__name__)

DOMAIN    = "whisky"
PLATFORMS = ["sensor"]
DATA_FILE = "whisky_data.json"
VERSION   = "0.4.0"

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

# ── Champs éditables par les services add_whisky/update_whisky ──────────────
# Séparés en deux groupes : COMMON (niveau fiche, communs à toute future
# boisson) et META (uniquement whisky_meta). Un appel de service reste PLAT
# (comme dans Millésime) : add_whisky(distillery=..., cask_type=...) plutôt
# que d'exiger un sous-dictionnaire — plus simple à remplir depuis Outils de
# développement → Actions. Le routage vers whisky_meta est interne.
COMMON_FIELDS = [
    "image_url", "label_image_url", "price", "current_value", "currency",
    "purchase_date", "purchase_location", "storage_location", "notes",
    "favorite", "rating", "barcode", "external_id", "external_url",
]
META_FIELDS = [
    "distillery", "bottler", "brand", "expression",
    "country", "region", "distillery_location",
    "whisky_type",
    "age", "vintage", "bottling_year", "abv", "volume_ml",
    "chill_filtered", "natural_colour", "peated", "peat_level", "ppm",
    "maturation", "cask_type", "cask_number", "finish", "maturation_years",
    "batch", "edition", "bottle_number", "number_of_bottles",
    "limited_edition", "independent_bottler",
    "tasting_notes", "nose_notes", "palate_notes", "finish_notes",
    "whiskybase_id", "whiskybase_url",
]

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

    # ── Services ──────────────────────────────────────────────────────────────

    def _get() -> dict:
        return hass.data[DOMAIN][entry.entry_id]["data"]

    async def _persist(d: dict) -> None:
        hass.data[DOMAIN][entry.entry_id]["data"] = d
        await hass.async_add_executor_job(_save, hass, d)
        hass.bus.async_fire(f"{DOMAIN}_updated", {})

    def _call_rack_id(call: ServiceCall, default: str = "") -> str:
        v = call.data.get("rack_id")
        return default if v is None else v

    def _find_whisky(d: dict, whisky_id: str) -> dict | None:
        return next((w for w in d.get("whiskies", []) if w["id"] == whisky_id), None)

    # ── Casiers ───────────────────────────────────────────────────────────────

    async def svc_add_rack(call: ServiceCall) -> None:
        d = _get()
        cellar = _cellar(d, call.data.get("cellar_id"))
        cols = int(call.data.get("columns", 6))
        shelves = int(call.data.get("shelves", 3))
        levels = max(1, min(4, int(call.data.get("levels", 1))))
        rack = {
            "id":      _uid(),
            "name":    call.data.get("name", f"Étagère {len(cellar['racks']) + 1}"),
            "columns": cols, "shelves": shelves, "levels": levels,
            "slots":   cols * shelves * levels,
        }
        cellar["racks"].append(rack)
        await _persist(d)

    async def svc_update_rack(call: ServiceCall) -> None:
        d = _get()
        rid = _call_rack_id(call)
        for r in _all_racks(d):
            if r["id"] == rid:
                for k in ("name", "columns", "shelves"):
                    if k in call.data:
                        r[k] = call.data[k]
                if "levels" in call.data:
                    r["levels"] = max(1, min(4, int(call.data["levels"])))
                r["slots"] = _rack_capacity(r)
                break
        else:
            raise HomeAssistantError(f"Casier introuvable : {rid}")
        await _persist(d)

    async def svc_remove_rack(call: ServiceCall) -> None:
        d = _get()
        rid = _call_rack_id(call)
        for c in _cellars(d):
            c["racks"] = [r for r in c["racks"] if r["id"] != rid]
        for w in d["whiskies"]:
            w["slots"] = [s for s in w["slots"] if s["rack_id"] != rid]
        # Une fiche sans emplacement n'est PAS supprimée automatiquement pour le
        # whisky (contrairement au fork vin) : une bouteille "finished" peut
        # légitimement n'avoir plus d'emplacement occupé pertinent tout en
        # restant un historique de dégustation valide. Seul remove_whisky retire
        # une fiche.
        await _persist(d)

    # ── Caves / armoires ──────────────────────────────────────────────────────

    async def svc_add_cellar(call: ServiceCall) -> None:
        d = _get()
        cs = _cellars(d)
        cs.append({"id": _uid(), "name": call.data.get("name", f"Collection {len(cs) + 1}"), "racks": []})
        await _persist(d)

    async def svc_rename_cellar(call: ServiceCall) -> None:
        d = _get()
        cellar = _cellar(d, call.data.get("cellar_id"))
        cellar["name"] = call.data.get("name", "Collection")
        await _persist(d)

    async def svc_remove_cellar(call: ServiceCall) -> None:
        d = _get()
        cid = call.data.get("cellar_id")
        cs = _cellars(d)
        target = next((c for c in cs if c.get("id") == cid), None)
        if not target:
            raise HomeAssistantError(f"Collection introuvable : {cid}")
        if len(cs) <= 1:
            raise HomeAssistantError("Impossible de supprimer la dernière collection.")
        if target.get("racks"):
            raise HomeAssistantError(
                "Cette collection contient encore des étagères : déplacez ou supprimez-les d'abord."
            )
        d["cellars"] = [c for c in cs if c.get("id") != cid]
        await _persist(d)

    # ── Fiches whisky ─────────────────────────────────────────────────────────

    async def svc_add_whisky(call: ServiceCall) -> None:
        """Crée une nouvelle fiche whisky, avec un premier emplacement optionnel."""
        d = _get()
        name = str(call.data.get("name", "")).strip()
        if not name:
            raise HomeAssistantError("Le nom du whisky est requis.")
        slots = []
        rack_id = call.data.get("rack_id")
        if rack_id:
            slot = int(call.data.get("slot", 0))
            if _slot_taken(d, rack_id, slot):
                raise HomeAssistantError(f"L'emplacement n°{slot + 1} est déjà occupé dans cette étagère.")
            slots = [_mk_slot(rack_id, slot, call.data.get("slot_comment"))]
        meta = {k: call.data[k] for k in META_FIELDS if k in call.data}
        common = {k: call.data[k] for k in COMMON_FIELDS if k in call.data}
        record = _new_whisky_record(name, whisky_meta=meta, slots=slots, **common)
        d["whiskies"].append(record)
        await _persist(d)
        hass.bus.async_fire(f"{DOMAIN}_bottle_added", {"whisky_id": record["id"], "name": name})

    async def svc_update_whisky(call: ServiceCall) -> None:
        """Met à jour les métadonnées d'une fiche whisky (champs communs + whisky_meta)."""
        d = _get()
        whisky_id = call.data["whisky_id"]
        w = _find_whisky(d, whisky_id)
        if not w:
            raise HomeAssistantError(f"Whisky introuvable : {whisky_id}")
        if "name" in call.data:
            w["name"] = str(call.data["name"]).strip() or w["name"]
        for k in COMMON_FIELDS:
            if k in call.data:
                w[k] = call.data[k]
        for k in META_FIELDS:
            if k in call.data:
                w["whisky_meta"][k] = call.data[k]
        await _persist(d)

    async def svc_remove_whisky(call: ServiceCall) -> None:
        """Supprime une fiche whisky et tous ses emplacements."""
        d = _get()
        d["whiskies"] = [w for w in d["whiskies"] if w["id"] != call.data["whisky_id"]]
        await _persist(d)

    # ── Emplacements (bouteilles physiques) ──────────────────────────────────

    async def svc_add_slot(call: ServiceCall) -> None:
        """Ajoute un exemplaire physique à une fiche whisky existante."""
        d = _get()
        whisky_id = call.data["whisky_id"]
        rack_id = _call_rack_id(call)
        slot = int(call.data.get("slot", 0))
        if _slot_taken(d, rack_id, slot):
            raise HomeAssistantError(f"L'emplacement n°{slot + 1} est déjà occupé dans cette étagère.")
        w = _find_whisky(d, whisky_id)
        if not w:
            raise HomeAssistantError(f"Whisky introuvable : {whisky_id}")
        w["slots"].append(_mk_slot(rack_id, slot, call.data.get("comment"), call.data.get("size")))
        await _persist(d)

    async def svc_update_slot(call: ServiceCall) -> None:
        """Modifie le format ou le commentaire d'un exemplaire, sans le déplacer."""
        d = _get()
        w = _find_whisky(d, call.data["whisky_id"])
        if not w:
            raise HomeAssistantError(f"Whisky introuvable : {call.data['whisky_id']}")
        slot_idx = int(call.data.get("slot_idx", 0))
        if slot_idx >= len(w["slots"]):
            raise HomeAssistantError(f"Index d'emplacement {slot_idx} invalide pour ce whisky.")
        s = w["slots"][slot_idx]
        for k in ("size", "comment"):
            if k in call.data:
                v = str(call.data[k]).strip()
                if v:
                    s[k] = v
                else:
                    s.pop(k, None)
        await _persist(d)

    async def svc_move_slot(call: ServiceCall) -> None:
        """Déplace un exemplaire vers une autre étagère/emplacement."""
        d = _get()
        whisky_id = call.data["whisky_id"]
        slot_idx = int(call.data.get("slot_idx", 0))
        new_rack = _call_rack_id(call)
        new_slot = int(call.data.get("slot", 0))
        if _slot_taken(d, new_rack, new_slot, exclude_whisky_id=whisky_id, exclude_slot_idx=slot_idx):
            raise HomeAssistantError(f"L'emplacement n°{new_slot + 1} est déjà occupé dans cette étagère.")
        w = _find_whisky(d, whisky_id)
        if not w:
            raise HomeAssistantError(f"Whisky introuvable : {whisky_id}")
        if slot_idx >= len(w["slots"]):
            raise HomeAssistantError(f"Index d'emplacement {slot_idx} invalide pour ce whisky.")
        w["slots"][slot_idx] = {**w["slots"][slot_idx], "rack_id": new_rack, "slot": new_slot}
        await _persist(d)

    async def svc_remove_slot(call: ServiceCall) -> None:
        """Retire UN exemplaire. Supprime la fiche si c'était le dernier emplacement."""
        d = _get()
        w = _find_whisky(d, call.data["whisky_id"])
        if not w:
            raise HomeAssistantError(f"Whisky introuvable : {call.data['whisky_id']}")
        slot_idx = int(call.data.get("slot_idx", 0))
        if slot_idx >= len(w["slots"]):
            raise HomeAssistantError(f"Index d'emplacement {slot_idx} invalide pour ce whisky.")
        if len(w["slots"]) <= 1:
            d["whiskies"].remove(w)
        else:
            w["slots"].pop(slot_idx)
        await _persist(d)

    # ── Cycle de vie d'une bouteille : sealed → opened → finished ────────────

    async def svc_open_bottle(call: ServiceCall) -> None:
        """Marque un exemplaire comme ouvert (sealed → opened)."""
        d = _get()
        w = _find_whisky(d, call.data["whisky_id"])
        if not w:
            raise HomeAssistantError(f"Whisky introuvable : {call.data['whisky_id']}")
        slot_idx = int(call.data.get("slot_idx", 0))
        if slot_idx >= len(w["slots"]):
            raise HomeAssistantError(f"Index d'emplacement {slot_idx} invalide pour ce whisky.")
        s = w["slots"][slot_idx]
        if s.get("bottle_status", "sealed") != "sealed":
            raise HomeAssistantError("Cette bouteille n'est plus scellée.")
        s["bottle_status"] = "opened"
        s["opened_date"] = call.data.get("opened_date") or datetime.now().strftime("%Y-%m-%d")
        s["remaining_percent"] = 100
        await _persist(d)
        hass.bus.async_fire(f"{DOMAIN}_bottle_opened", {
            "whisky_id": w["id"], "slot_idx": slot_idx, "name": w.get("name", ""),
        })

    async def svc_finish_bottle(call: ServiceCall) -> None:
        """Marque un exemplaire comme terminé (opened → finished).

        Contrairement à Millésime (drink_bottle), l'emplacement N'EST PAS
        supprimé : "finished" est un état de fiche à part entière (brief §2,
        bottle_status), pas une suppression — l'historique de la bouteille
        reste consultable. Note/commentaire optionnels archivés sur l'emplacement.
        """
        d = _get()
        w = _find_whisky(d, call.data["whisky_id"])
        if not w:
            raise HomeAssistantError(f"Whisky introuvable : {call.data['whisky_id']}")
        slot_idx = int(call.data.get("slot_idx", 0))
        if slot_idx >= len(w["slots"]):
            raise HomeAssistantError(f"Index d'emplacement {slot_idx} invalide pour ce whisky.")
        s = w["slots"][slot_idx]
        s["bottle_status"] = "finished"
        s["remaining_percent"] = 0
        s["finished_date"] = call.data.get("finished_date") or datetime.now().strftime("%Y-%m-%d")
        rating = call.data.get("rating")
        if rating is not None:
            try:
                w["rating"] = round(float(str(rating).replace(",", ".")), 1)
            except (TypeError, ValueError):
                pass
        comment = call.data.get("comment")
        if comment:
            s["comment"] = str(comment)
        await _persist(d)
        hass.bus.async_fire(f"{DOMAIN}_bottle_finished", {
            "whisky_id": w["id"], "slot_idx": slot_idx, "name": w.get("name", ""),
        })

    hass.services.async_register(DOMAIN, "add_rack",       svc_add_rack)
    hass.services.async_register(DOMAIN, "update_rack",    svc_update_rack)
    hass.services.async_register(DOMAIN, "remove_rack",    svc_remove_rack)
    hass.services.async_register(DOMAIN, "add_cellar",     svc_add_cellar)
    hass.services.async_register(DOMAIN, "rename_cellar",  svc_rename_cellar)
    hass.services.async_register(DOMAIN, "remove_cellar",  svc_remove_cellar)
    hass.services.async_register(DOMAIN, "add_whisky",     svc_add_whisky)
    hass.services.async_register(DOMAIN, "update_whisky",  svc_update_whisky)
    hass.services.async_register(DOMAIN, "remove_whisky",  svc_remove_whisky)
    hass.services.async_register(DOMAIN, "add_slot",       svc_add_slot)
    hass.services.async_register(DOMAIN, "update_slot",    svc_update_slot)
    hass.services.async_register(DOMAIN, "move_slot",      svc_move_slot)
    hass.services.async_register(DOMAIN, "remove_slot",    svc_remove_slot)
    hass.services.async_register(DOMAIN, "open_bottle",    svc_open_bottle)
    hass.services.async_register(DOMAIN, "finish_bottle",  svc_finish_bottle)

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
