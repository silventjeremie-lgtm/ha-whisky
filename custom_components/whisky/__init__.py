"""Whisky — Collection de whiskies pour Home Assistant.

Projet indépendant dérivé de Millésime (github.com/Redsklns/ha-millesime,
MIT) : même style d'architecture (stockage JSON local, casiers/emplacements
agnostiques, carte Lovelace auto-servie), vocabulaire et modèle de données
entièrement propres au whisky.

Commit 12/12 : packaging final — socle v1 complet (modèle de données,
reconnaissance photo, formulaire, liste/détail, statistiques/filtres,
entités et services HA, tests, documentation). Pas de visualisation 3D ni de
sommelier IA dans cette v1 (voir README, Limites connues). Aucune
dépendance à Whiskybase ou toute autre base fermée (brief §2/§18) — sans
clé Gemini, saisie manuelle uniquement, aucun repli automatique (documenté
comme limitation).
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import uuid
from datetime import datetime

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

DOMAIN    = "whisky"
PLATFORMS = ["sensor"]
DATA_FILE = "whisky_data.json"


def _read_manifest_version() -> str:
    """Lit la version depuis manifest.json — source UNIQUE de vérité pour le
    cache-busting de la carte (voir _async_register_card, url = .../whisky-
    card.js?v=VERSION). RÉGRESSION CORRIGÉE ICI : une constante VERSION
    dupliquée à la main restait figée à "1.0.0" alors que manifest.json et
    whisky-card.js avançaient normalement à chaque version (1.0.1, 1.0.2,
    1.1.0, 1.2.0) — l'URL de la ressource Lovelace ne changeait donc JAMAIS,
    et le navigateur continuait de servir indéfiniment le tout premier
    whisky-card.js mis en cache, quelle que soit la mise à jour réellement
    installée. En dérivant VERSION de manifest.json, une seule valeur à
    bumper par version (déjà fait à chaque release) suffit désormais."""
    try:
        manifest_path = os.path.join(os.path.dirname(__file__), "manifest.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f).get("version") or "0.0.0"
    except Exception:
        return "0.0.0"


VERSION = _read_manifest_version()

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
    """Retourne True si l'emplacement est déjà occupé dans ce casier.

    Un rack_id vide/falsy signifie "sans emplacement assigné" (bouteille
    comptée dans la collection sans placement physique — le formulaire v1 de
    la carte ne propose pas encore de sélecteur d'étagère, voir commit 6) :
    ces exemplaires ne peuvent jamais entrer en collision entre eux, sinon
    une seule bouteille "non placée" pourrait exister dans toute la
    collection avant que le service ne refuse les suivantes.
    """
    if not rack_id:
        return False
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


# ── Gemini : découverte de modèles + appel unifié ────────────────────────────
# Infrastructure reprise quasiment à l'identique de Millésime (composant
# éprouvé : repli de modèle, gestion du "thinking", récupération de réponse
# tronquée) — seuls les libellés de log changent. Voir Millésime __init__.py
# pour l'historique des correctifs (v7.1.3 à v7.1.8) qui ont amené cette forme.

GEMINI_TEXT_MODEL      = "gemini-2.5-flash"
GEMINI_VISION_MODEL    = "gemini-2.5-flash"
GEMINI_TEXT_FALLBACK   = "gemini-2.5-flash-lite"
GEMINI_VISION_FALLBACK = "gemini-2.5-flash-lite"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/"

_PREF_TEXT = [
    "gemini-3.5-flash", "gemini-3.1-flash", "gemini-3-flash",
    "gemini-2.5-flash", "gemini-3.1-flash-lite", "gemini-2.5-flash-lite",
]
_PREF_VISION = [
    "gemini-3.5-flash", "gemini-3.1-flash", "gemini-3-flash",
    "gemini-2.5-flash", "gemini-2.5-flash-lite",
]
_GEMINI_MODELS: dict = {"text": None, "vision": None, "discovered": False}

ERR_QUOTA_EXCEEDED = "quota_exceeded"
ERR_INVALID_KEY    = "invalid_key"
ERR_UNAVAILABLE    = "service_unavailable"
ERR_PARSE_ERROR    = "parse_error"
ERR_NO_MODEL       = "no_model"
ERR_TIMEOUT        = "timeout"
ERR_TRUNCATED      = "truncated"
ERR_NO_KEY         = "no_key"


async def _discover_gemini_models(hass: HomeAssistant, api_key: str) -> None:
    """Sélectionne les meilleurs modèles texte/vision réellement disponibles
    pour la clé donnée. Silencieux et non bloquant : en cas d'échec, les
    modèles de repli stables (2.5) restent en vigueur."""
    if not api_key:
        return
    session = async_get_clientsession(hass)
    try:
        async with session.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key, "pageSize": "200"},
            timeout=15,
        ) as resp:
            if resp.status != 200:
                _LOGGER.warning("Whisky — découverte modèles Gemini : HTTP %s, repli stable", resp.status)
                return
            data = await resp.json(content_type=None)
    except Exception as exc:
        _LOGGER.warning("Whisky — découverte modèles Gemini impossible (%s), repli stable", exc)
        return

    available: set[str] = set()
    for m in data.get("models", []):
        name = (m.get("name") or "").split("/")[-1]
        methods = m.get("supportedGenerationMethods") or m.get("supportedActions") or []
        if name and (not methods or "generateContent" in methods):
            available.add(name)
    if not available:
        _LOGGER.warning("Whisky — découverte modèles : liste vide, repli stable")
        return

    def _pick(prefs: list[str], fallback: str) -> list[str]:
        chosen = [m for m in prefs if m in available]
        if fallback in available and fallback not in chosen:
            chosen.append(fallback)
        if not chosen:
            chosen = [m for m in sorted(available) if "flash" in m][:2] or sorted(available)[:1]
        return chosen

    _GEMINI_MODELS["text"] = _pick(_PREF_TEXT, GEMINI_TEXT_FALLBACK)
    _GEMINI_MODELS["vision"] = _pick(_PREF_VISION, GEMINI_VISION_FALLBACK)
    _GEMINI_MODELS["discovered"] = True
    _LOGGER.info("Whisky — modèles Gemini découverts : texte=%s | vision=%s",
                 _GEMINI_MODELS["text"], _GEMINI_MODELS["vision"])


def _thinking_cfg(model: str) -> dict:
    m = (model or "").lower()
    if "2.5" in m:
        return {"thinkingConfig": {"thinkingBudget": 0}}
    if m.startswith("gemini-3"):
        return {"thinkingConfig": {"thinkingLevel": "low"}}
    return {}


def _gen_cfg(model: str, base: dict) -> dict:
    return {**base, **_thinking_cfg(model)}


def _text_models() -> list[str]:
    return _GEMINI_MODELS["text"] or [GEMINI_TEXT_MODEL, GEMINI_TEXT_FALLBACK]


def _vision_models() -> list[str]:
    return _GEMINI_MODELS["vision"] or [GEMINI_VISION_MODEL, GEMINI_VISION_FALLBACK]


def _gemini_error_code(status: int) -> str:
    if status == 429:
        return ERR_QUOTA_EXCEEDED
    if status in (400, 401, 403):
        return ERR_INVALID_KEY
    return ERR_UNAVAILABLE


async def _gemini_call(
    hass: HomeAssistant, api_key: str, models: list[str], body_base: dict,
    gen_cfg: dict, timeout: int, label: str, session=None,
) -> tuple[dict | None, str | None]:
    """Appel Gemini unifié : repli de modèle sur 404/5xx, réessai sans
    "thinking" sur 400/500/503, arrêt immédiat sur 429/clé invalide."""
    session = session or async_get_clientsession(hass)
    saw_404 = saw_timeout = saw_other = False

    for model in models:
        for attempt in (0, 1):
            cfg = _gen_cfg(model, gen_cfg) if attempt == 0 else dict(gen_cfg)
            body = {**body_base, "generationConfig": cfg}
            try:
                async with session.post(
                    f"{GEMINI_BASE_URL}{model}:generateContent",
                    params={"key": api_key},
                    json=body,
                    headers={"Content-Type": "application/json"},
                    timeout=timeout,
                ) as resp:
                    status = resp.status
                    if status == 200:
                        data = await resp.json(content_type=None)
                        _LOGGER.debug("%s : réponse de %s", label, model)
                        return data, None
                    if status in (400, 500, 503) and attempt == 0 and _thinking_cfg(model):
                        _LOGGER.warning(
                            "%s : HTTP %s avec thinkingConfig (%s) → réessai sans ce réglage",
                            label, status, model)
                        continue
                    if status == 404:
                        saw_404 = True
                        _LOGGER.warning("%s : modèle %s indisponible (404), repli", label, model)
                        break
                    if status in (429, 400, 401, 403):
                        saw_other = True
                        _LOGGER.warning("%s : HTTP %s sur %s", label, status, model)
                        return None, _gemini_error_code(status)
                    saw_other = True
                    _LOGGER.warning("%s : HTTP %s sur %s, repli", label, status, model)
                    break
            except asyncio.TimeoutError:
                saw_timeout = True
                _LOGGER.warning("%s : délai dépassé (%s, %ss)", label, model, timeout)
                break
            except Exception as exc:
                saw_other = True
                _LOGGER.warning("%s : erreur (%s) %s", label, model, exc)
                break

    if saw_404 and not saw_other and not saw_timeout:
        _LOGGER.error(
            "%s : AUCUN modèle utilisable (%s). Vérifiez l'accès de votre clé "
            "Gemini aux modèles sur aistudio.google.com.", label, ", ".join(models))
        if not _GEMINI_MODELS["discovered"] and api_key:
            hass.async_create_task(_discover_gemini_models(hass, api_key))
        return None, ERR_NO_MODEL
    if saw_timeout and not saw_other:
        return None, ERR_TIMEOUT
    return None, ERR_UNAVAILABLE


def _gemini_text(data: dict) -> tuple[str, str]:
    """Texte utile d'une réponse Gemini + finishReason (écarte les parties
    de réflexion "thought", ne prend jamais qu'un premier fragment vide)."""
    cand = (data.get("candidates") or [{}])[0] or {}
    finish = cand.get("finishReason") or ""
    parts = (cand.get("content") or {}).get("parts") or []
    chunks = []
    for p in parts:
        if not isinstance(p, dict) or p.get("thought"):
            continue
        t = p.get("text")
        if isinstance(t, str) and t.strip():
            chunks.append(t)
    return "".join(chunks), finish


def _json_salvage(txt: str):
    """Récupère les objets JSON complets d'une réponse tronquée par la limite
    de tokens, plutôt que de tout rejeter pour un dernier objet coupé."""
    if not txt:
        return None
    s = txt.strip()
    if s.startswith("["):
        objs, depth, start, in_str, esc = [], 0, None, False, False
        for i, ch in enumerate(s):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start is not None:
                    frag = s[start:i + 1]
                    try:
                        objs.append(json.loads(frag))
                    except Exception:
                        pass
                    start = None
        return objs or None
    if s.startswith("{"):
        for cut in range(len(s), 0, -1):
            frag = s[:cut].rstrip().rstrip(",")
            for suffix in ("", "}", '"}', "]}", '"]}'):
                try:
                    return json.loads(frag + suffix)
                except Exception:
                    continue
            if len(s) - cut > 4000:
                break
    return None


def _gemini_payload(data: dict):
    """JSON d'une réponse Gemini, tolérant aux enrobages (```json, texte
    parasite, réponse tronquée récupérée partiellement)."""
    raw, finish = _gemini_text(data)
    if not raw.strip():
        raise ValueError(f"réponse vide (finishReason={finish or '?'})")
    txt = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    txt = re.sub(r"\s*```$", "", txt).strip()
    try:
        return json.loads(txt)
    except Exception:
        pass
    for op, cl in (("{", "}"), ("[", "]")):
        i, j = txt.find(op), txt.rfind(cl)
        if i != -1 and j > i:
            try:
                return json.loads(txt[i:j + 1])
            except Exception:
                continue
    salvaged = _json_salvage(txt)
    if salvaged:
        _LOGGER.warning("Gemini — réponse coupée (finishReason=%s), contenu partiel récupéré", finish or "?")
        return salvaged
    raise ValueError(f"JSON introuvable (finishReason={finish or '?'}, {len(raw)} car.)")


# ── Prompt Gemini WHISKY (distinct du prompt vin de Millésime) ──────────────
# Point critique du brief §4 : un embouteilleur indépendant (Signatory
# Vintage, Gordon & MacPhail, Cadenhead's, Douglas Laing, Berry Bros. & Rudd,
# That Boutique-y Whisky Company...) N'EST PAS la distillerie. Le prompt liste
# des exemples explicites pour éviter cette confusion très fréquente sur les
# étiquettes de mise en bouteille indépendante.
_GEMINI_SYSTEM_WHISKY = """\
Tu es un expert mondial du whisky (single malt, blended, bourbon, rye, \
whisky japonais...), capable de lire des étiquettes de bouteilles.

Analyse la ou les photos fournies : étiquette principale, contre-étiquette, \
capsule/scellé, tube ou coffret si visible. Retourne UNIQUEMENT un objet \
JSON valide {}, sans markdown ni backticks, avec exactement ces champs :
  name, distillery, bottler, brand, expression,
  country, region, whisky_type,
  age, vintage, bottling_year, abv, volume_ml,
  cask_type, finish, batch, edition, cask_number, bottle_number,
  limited_edition, peated,
  confidence_score, field_confidence

RÈGLE ABSOLUE — NE JAMAIS INVENTER : pour CHAQUE champ que tu ne peux pas \
lire avec certitude sur l'image ou déduire sans ambiguïté, retourne JSON \
null pour ce champ. Un champ null vaut toujours mieux qu'une supposition. \
N'utilise JAMAIS une valeur plausible mais non lue sur l'étiquette.

DISTINCTION CRITIQUE distillery / bottler — une bouteille de mise en \
bouteille INDÉPENDANTE porte le nom de l'embouteilleur bien plus gros que \
celui de la distillerie d'origine (parfois même absente du visuel). \
N'assimile JAMAIS automatiquement le nom le plus visible à la distillerie. \
Exemples d'embouteilleurs indépendants connus, à mettre dans "bottler" et \
JAMAIS dans "distillery" : Signatory Vintage, Gordon & MacPhail, \
Cadenhead's, Douglas Laing (Old Particular, Xtra Old Particular...), \
Berry Bros. & Rudd, That Boutique-y Whisky Company, Hunter Laing, \
The Single Cask, Adelphi. Exemple : une étiquette "Signatory Vintage — \
Caol Ila 2012, 11 Year Old" donne bottler="Signatory Vintage" et \
distillery="Caol Ila" — jamais l'inverse. Si aucun nom de distillerie \
n'est identifiable alors qu'un embouteilleur l'est, laisse "distillery" à \
null plutôt que de recopier le nom de l'embouteilleur.

Règles par champ :
- name : nom complet tel qu'il apparaîtrait sur une fiche (ex. "Caol Ila 11 \
  Year Old — Signatory Vintage"), jamais null si une étiquette est lisible
- whisky_type : UNIQUEMENT l'une de ces valeurs, ou null si incertain : \
  "Single Malt", "Blended Malt", "Blended Whisky", "Single Grain", \
  "Bourbon", "Rye", "Tennessee Whiskey", "Corn Whiskey", \
  "Irish Single Malt", "Irish Pot Still", "Japanese Whisky", \
  "World Whisky", "Other"
- age : nombre d'années en chaîne (ex. "16"), null si non-millésimé (NAS)
- vintage / bottling_year : année à 4 chiffres en chaîne, ou null
- abv : nombre décimal (% vol, ex. 43.0), null si illisible
- volume_ml : nombre entier (700 le plus courant), null si illisible
- cask_type : type de fût en texte libre (ex. "First Fill Oloroso Sherry \
  Butt"), null si non mentionné
- peated : true/false uniquement si mentionné ou déductible avec certitude \
  (ex. distillerie notoirement tourbée ET rien ne l'indique autrement) ; \
  null dans le doute — NE DEVINE PAS à partir du seul nom de distillerie
- limited_edition : true si "limited edition"/"édition limitée"/numérotation \
  explicite visible, sinon null
- confidence_score : nombre décimal 0.0 à 1.0, confiance GLOBALE de \
  l'identification
- field_confidence : objet {"champ": 0.0-1.0, ...} — confiance uniquement \
  pour les champs que tu as renseignés (non null) ; omets les champs null

Si l'image n'est manifestement pas une bouteille de whisky, retourne \
{"name": null, "confidence_score": 0.0, "field_confidence": {}} et laisse \
tous les autres champs à null.\
"""


def _safe_float_or_none(value):
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _safe_bool_or_none(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in ("true", "1", "oui", "yes"):
        return True
    if s in ("false", "0", "non", "no"):
        return False
    return None


def _clean_str_or_none(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


_WHISKY_RESULT_FIELDS = (
    "name", "distillery", "bottler", "brand", "expression",
    "country", "region", "whisky_type",
    "age", "vintage", "bottling_year",
    "cask_type", "finish", "batch", "edition", "cask_number", "bottle_number",
)
_WHISKY_RESULT_FLOAT_FIELDS = ("abv",)
_WHISKY_RESULT_INT_FIELDS = ("volume_ml",)
_WHISKY_RESULT_BOOL_FIELDS = ("limited_edition", "peated")


def _parse_gemini_whisky_response(raw: str, source: str, finish: str = "") -> tuple[dict | None, str | None]:
    """Parse la réponse JSON Gemini whisky.

    Contrairement au parseur vin de Millésime (qui force une valeur par
    défaut sur chaque champ), CHAQUE CHAMP RESTE None quand l'IA a répondu
    null ou a omis le champ — jamais de valeur inventée pour "faire propre"
    (brief §3 : null plutôt qu'une hallucination). C'est à l'écran de
    validation utilisateur (commit 6) de présenter ces trous, pas à ce
    parseur de les combler.

    Retourne (résultat | None, code_erreur | None).
    """
    if not raw:
        _LOGGER.warning("Gemini whisky — réponse vide (%s, finishReason=%s)", source, finish or "?")
        return None, ERR_TRUNCATED if finish == "MAX_TOKENS" else ERR_PARSE_ERROR

    txt = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    txt = re.sub(r"\s*```$", "", txt)

    try:
        parsed = json.loads(txt)
    except json.JSONDecodeError:
        parsed = _json_salvage(txt)
        if not parsed:
            _LOGGER.warning(
                "Gemini whisky — JSON illisible (%s, finishReason=%s, %d car.) : %.200s",
                source, finish or "?", len(txt), txt,
            )
            return None, ERR_TRUNCATED if finish == "MAX_TOKENS" else ERR_PARSE_ERROR

    if isinstance(parsed, list):
        parsed = parsed[0] if parsed else {}
    if not isinstance(parsed, dict):
        return None, ERR_PARSE_ERROR

    result: dict = {}
    for f in _WHISKY_RESULT_FIELDS:
        result[f] = _clean_str_or_none(parsed.get(f))
    for f in _WHISKY_RESULT_FLOAT_FIELDS:
        result[f] = _safe_float_or_none(parsed.get(f))
    for f in _WHISKY_RESULT_INT_FIELDS:
        v = _safe_float_or_none(parsed.get(f))
        result[f] = int(v) if v is not None else None
    for f in _WHISKY_RESULT_BOOL_FIELDS:
        result[f] = _safe_bool_or_none(parsed.get(f))

    if result.get("whisky_type") and result["whisky_type"] not in WHISKY_TYPE_VALUES:
        # Normalisation souple (casse/espaces) avant d'abandonner à "Other"
        match = next((v for v in WHISKY_TYPE_VALUES
                      if v.lower() == result["whisky_type"].strip().lower()), None)
        result["whisky_type"] = match  # None si aucune correspondance : on ne force pas "Other"

    score = _safe_float_or_none(parsed.get("confidence_score"))
    result["confidence_score"] = max(0.0, min(1.0, score)) if score is not None else None

    field_conf = parsed.get("field_confidence")
    result["field_confidence"] = (
        {k: max(0.0, min(1.0, v)) for k, v in field_conf.items() if isinstance(v, (int, float))}
        if isinstance(field_conf, dict) else {}
    )

    if not result.get("name") and not any(
        result.get(f) for f in _WHISKY_RESULT_FIELDS if f != "name"
    ):
        # Rien d'exploitable : image non reconnue comme whisky, ou vide
        return None, None

    return result, None


async def _gemini_analyze_whisky_photo(
    hass: HomeAssistant, image_b64: str, mime_type: str, api_key: str
) -> tuple[dict | None, str | None]:
    """Analyse une photo d'étiquette de whisky via Gemini Vision."""
    body = {
        "system_instruction": {"parts": [{"text": _GEMINI_SYSTEM_WHISKY}]},
        "contents": [{
            "parts": [
                {"text": "Identifie ce whisky à partir de cette photo."},
                {"inline_data": {"mime_type": mime_type, "data": image_b64}},
            ]
        }],
    }
    gen = {"temperature": 0.1, "maxOutputTokens": 2048, "responseMimeType": "application/json"}
    data, last_code = None, ERR_UNAVAILABLE
    for attempt in range(2):
        data, last_code = await _gemini_call(
            hass, api_key, _vision_models(), body, gen, 45, "Gemini whisky photo",
        )
        if data is not None or last_code not in (ERR_UNAVAILABLE, ERR_TIMEOUT):
            break
        if attempt == 0:
            await asyncio.sleep(3.0)

    if data is None:
        _LOGGER.warning("Gemini whisky photo : échec sur tous les modèles (%s)", last_code)
        return None, last_code or ERR_UNAVAILABLE

    raw, finish = _gemini_text(data)
    try:
        result, err = _parse_gemini_whisky_response(raw, "photo", finish)
    except Exception as exc:
        _LOGGER.warning("Gemini whisky photo : erreur de lecture (%s)", exc)
        return None, ERR_TRUNCATED if finish == "MAX_TOKENS" else ERR_PARSE_ERROR
    _LOGGER.info("Gemini whisky photo : %s", "résultat trouvé" if result else "rien d'exploitable")
    return result, err


async def _gemini_search_whisky_text(
    hass: HomeAssistant, query: str, api_key: str
) -> tuple[dict | None, str | None]:
    """Recherche Gemini par nom (pas d'équivalent Open Food Facts pour le
    whisky : sans clé, cette fonction n'est pas appelée, voir websocket)."""
    body = {
        "system_instruction": {"parts": [{"text": _GEMINI_SYSTEM_WHISKY}]},
        "contents": [{"parts": [{"text": f'Identifie ce whisky : "{query}"'}]}],
    }
    gen = {"temperature": 0.2, "maxOutputTokens": 2048, "responseMimeType": "application/json"}
    data, code = await _gemini_call(
        hass, api_key, _text_models(), body, gen, 30, f"Gemini whisky texte '{query}'",
    )
    if data is None:
        return None, code or ERR_UNAVAILABLE
    raw, finish = _gemini_text(data)
    try:
        result, err = _parse_gemini_whisky_response(raw, f"texte:'{query}'", finish)
        return result, err
    except Exception as exc:
        _LOGGER.warning("Gemini whisky texte erreur pour '%s': %s", query, exc)
        return None, ERR_UNAVAILABLE


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

    # Découverte des modèles Gemini en tâche de fond (repli stable tant que
    # non résolue) — voir _discover_gemini_models.
    if gemini_key:
        hass.async_create_task(_discover_gemini_models(hass, gemini_key))

    await _async_register_card(hass)

    # ── WebSocket : reconnaissance photo / texte ─────────────────────────────

    @websocket_api.websocket_command({
        vol.Required("type"):      "whisky/analyze_photo",
        vol.Required("image_b64"): str,
        vol.Required("mime_type"): str,
    })
    @websocket_api.async_response
    async def ws_analyze_photo(hass: HomeAssistant, connection, msg: dict) -> None:
        gkey = hass.data[DOMAIN][entry.entry_id]["gemini_key"]
        if not gkey:
            connection.send_result(msg["id"], {"result": None, "error": ERR_NO_KEY})
            return
        result, err = await _gemini_analyze_whisky_photo(hass, msg["image_b64"], msg["mime_type"], gkey)
        connection.send_result(msg["id"], {"result": result, "error": err})

    websocket_api.async_register_command(hass, ws_analyze_photo)

    @websocket_api.websocket_command({
        vol.Required("type"):  "whisky/search_whisky",
        vol.Required("query"): str,
    })
    @websocket_api.async_response
    async def ws_search_whisky(hass: HomeAssistant, connection, msg: dict) -> None:
        gkey = hass.data[DOMAIN][entry.entry_id]["gemini_key"]
        query = (msg.get("query") or "").strip()
        if not gkey:
            connection.send_result(msg["id"], {"result": None, "error": ERR_NO_KEY})
            return
        if len(query) < 3:
            connection.send_result(msg["id"], {"result": None, "error": None})
            return
        result, err = await _gemini_search_whisky_text(hass, query, gkey)
        connection.send_result(msg["id"], {"result": result, "error": err})

    websocket_api.async_register_command(hass, ws_search_whisky)

    # ── WebSocket : get_data (chargement complet côté carte) ──────────────────

    @websocket_api.websocket_command({vol.Required("type"): "whisky/get_data"})
    @websocket_api.async_response
    async def ws_get_data(hass: HomeAssistant, connection, msg: dict) -> None:
        result = await hass.async_add_executor_job(_load, hass)
        connection.send_result(msg["id"], result)

    websocket_api.async_register_command(hass, ws_get_data)

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
        """Crée une nouvelle fiche whisky.

        Deux modes de placement, non combinables dans un même appel :
        - rack_id fourni : UN exemplaire précisément placé (slot).
        - rack_id absent : `quantity` exemplaires SANS emplacement assigné
          (rack_id=""), tous au statut `initial_status` — c'est le chemin
          emprunté par le formulaire v1 de la carte (commit 6), qui ne
          propose pas encore de sélecteur d'étagère.
        """
        d = _get()
        name = str(call.data.get("name", "")).strip()
        if not name:
            raise HomeAssistantError("Le nom du whisky est requis.")
        initial_status = call.data.get("initial_status", "sealed")
        if initial_status not in BOTTLE_STATUS_VALUES:
            initial_status = "sealed"
        rack_id = call.data.get("rack_id")
        if rack_id:
            slot = int(call.data.get("slot", 0))
            if _slot_taken(d, rack_id, slot):
                raise HomeAssistantError(f"L'emplacement n°{slot + 1} est déjà occupé dans cette étagère.")
            slots = [_mk_slot(rack_id, slot, call.data.get("slot_comment"), bottle_status=initial_status)]
        else:
            qty = max(1, int(call.data.get("quantity", 1)))
            slots = [_mk_slot("", 0, bottle_status=initial_status) for _ in range(qty)]
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

    async def svc_update_remaining(call: ServiceCall) -> None:
        """Met à jour le niveau restant (%) d'un exemplaire OUVERT.

        Permet un suivi manuel (pesée, estimation visuelle) entre l'ouverture
        (100%, fixé par open_bottle) et la fin (0%, fixé par finish_bottle).
        Déclenche whisky_bottle_low UNIQUEMENT au franchissement du seuil bas
        (front descendant : la valeur PRÉCÉDENTE était au-dessus du seuil, la
        NOUVELLE est à ou en dessous) — pas à chaque appel, pour rester
        directement utilisable dans une automatisation sans déclenchement
        répété à chaque mise à jour (brief §11 : services prêts pour
        l'automatisation).
        """
        d = _get()
        w = _find_whisky(d, call.data["whisky_id"])
        if not w:
            raise HomeAssistantError(f"Whisky introuvable : {call.data['whisky_id']}")
        slot_idx = int(call.data.get("slot_idx", 0))
        if slot_idx >= len(w["slots"]):
            raise HomeAssistantError(f"Index d'emplacement {slot_idx} invalide pour ce whisky.")
        s = w["slots"][slot_idx]
        if s.get("bottle_status", "sealed") != "opened":
            raise HomeAssistantError("Seul un exemplaire ouvert a un niveau restant à suivre.")
        try:
            raw_pct = float(str(call.data["remaining_percent"]).replace(",", "."))
        except (KeyError, TypeError, ValueError):
            raise HomeAssistantError("remaining_percent doit être un nombre entre 0 et 100.")
        pct = max(0, min(100, round(raw_pct)))
        threshold = max(0, min(100, int(call.data.get("low_threshold", 20))))
        previous = s.get("remaining_percent")
        s["remaining_percent"] = pct
        await _persist(d)
        crossed_down = (previous is None or previous > threshold) and pct <= threshold
        if crossed_down:
            hass.bus.async_fire(f"{DOMAIN}_bottle_low", {
                "whisky_id": w["id"], "slot_idx": slot_idx, "name": w.get("name", ""),
                "remaining_percent": pct, "threshold": threshold,
            })

    async def svc_add_tasting(call: ServiceCall) -> None:
        """Ajoute une dégustation SANS lien avec la collection.

        Contrairement à finish_bottle (qui clôt un exemplaire réellement
        possédé), cette entrée sert à noter un whisky simplement GOÛTÉ —
        chez un ami, en bar, lors d'une dégustation — sans jamais avoir
        possédé de bouteille. Alimente le même onglet "Whisky bu" côté
        carte, mais dans une liste séparée (tasting_log), jamais dans
        whiskies[] : aucun impact sur les capteurs de collection
        (sensor.whisky_total, whisky_collection_value, etc.).
        """
        d = _get()
        name = str(call.data.get("name", "")).strip()
        if not name:
            raise HomeAssistantError("Le nom du whisky est requis.")
        rating = call.data.get("rating", 0)
        try:
            rating = round(float(str(rating).replace(",", ".")), 1)
        except (TypeError, ValueError):
            rating = 0
        entry = {
            "id":           _uid(),
            "name":         name,
            "distillery":   str(call.data.get("distillery", "") or "").strip(),
            "whisky_type":  call.data.get("whisky_type", ""),
            "region":       str(call.data.get("region", "") or "").strip(),
            "country":      str(call.data.get("country", "") or "").strip(),
            "place":        str(call.data.get("place", "") or "").strip(),
            "tasted_date":  call.data.get("tasted_date") or datetime.now().strftime("%Y-%m-%d"),
            "rating":       rating,
            "comment":      str(call.data.get("comment", "") or "").strip(),
        }
        log = d.setdefault("tasting_log", [])
        log.append(entry)
        # Garder les 1000 dernières dégustations (même limite que Millésime).
        d["tasting_log"] = log[-1000:]
        await _persist(d)
        hass.bus.async_fire(f"{DOMAIN}_tasting_added", {"tasting_id": entry["id"], "name": name})

    async def svc_remove_tasting(call: ServiceCall) -> None:
        """Supprime une entrée du journal de dégustation (whisky goûté hors collection)."""
        d = _get()
        tid = call.data["tasting_id"]
        d["tasting_log"] = [t for t in d.get("tasting_log", []) if t.get("id") != tid]
        await _persist(d)

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
    hass.services.async_register(DOMAIN, "update_remaining", svc_update_remaining)
    hass.services.async_register(DOMAIN, "add_tasting",    svc_add_tasting)
    hass.services.async_register(DOMAIN, "remove_tasting", svc_remove_tasting)

    _LOGGER.info("Whisky v%s démarré (%d fiche(s))", VERSION, len(data.get("whiskies", [])))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    new_key = (entry.options.get("gemini_api_key") or "").strip()
    hass.data[DOMAIN][entry.entry_id]["gemini_key"] = new_key
    # La clé a changé → re-découvrir les modèles disponibles pour elle
    _GEMINI_MODELS["text"] = _GEMINI_MODELS["vision"] = None
    _GEMINI_MODELS["discovered"] = False
    if new_key:
        hass.async_create_task(_discover_gemini_models(hass, new_key))
    _LOGGER.info("Whisky — clé Gemini mise à jour, modèles à redécouvrir")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return ok
