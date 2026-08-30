"""Capteurs Whisky — v0.9.0.

Sept capteurs globaux, conformes au brief §9 :
  sensor.whisky_total              nombre total de bouteilles (exemplaires physiques)
  sensor.whisky_opened             bouteilles ouvertes (+ attribut "bottles" :
                                    détail par exemplaire ouvert avec ancienneté
                                    d'ouverture, pour les automatisations — commit 9)
  sensor.whisky_sealed             bouteilles scellées
  sensor.whisky_finished           bouteilles terminées
  sensor.whisky_distilleries       nombre de distilleries distinctes représentées
  sensor.whisky_collection_value   valeur du STOCK RESTANT (sealed+opened ; les
                                    bouteilles "finished" n'ont plus de valeur
                                    résiduelle, elles sont exclues du total)
  sensor.whisky_average_age        âge moyen (années), par FICHE (pas pondéré
                                    par nombre d'exemplaires), fiches sans âge
                                    numérique renseigné ignorées

Pas de capteurs par collection pour l'instant (une seule collection dans la
plupart des installations) — pourra être ajouté plus tard sur le modèle
multi-caves de Millésime si le besoin se présente.
"""
from __future__ import annotations

from datetime import date

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN

# Nombre maximum de clés détaillées par attribut de répartition (pays, région,
# distillerie, type, tourbe) — évite un état/attribut disproportionné sur une
# très grosse collection ; au-delà, seules les valeurs les plus représentées
# sont conservées (bonne pratique HA sur la taille des attributs).
_MAX_BREAKDOWN_KEYS = 25


def _whiskies(data: dict) -> list[dict]:
    return data.get("whiskies", []) or []


def _all_slots(data: dict) -> list[tuple[dict, dict]]:
    """(whisky, slot) pour chaque exemplaire physique, toutes fiches confondues."""
    return [(w, s) for w in _whiskies(data) for s in w.get("slots", [])]


def _count_by_status(data: dict, status: str) -> int:
    return sum(1 for _w, s in _all_slots(data) if s.get("bottle_status", "sealed") == status)


def _breakdown(data: dict, key_fn) -> dict[str, int]:
    """Répartition {clé: nombre de bouteilles}, triée par fréquence, bornée."""
    counts: dict[str, int] = {}
    for w in _whiskies(data):
        key = key_fn(w)
        if not key:
            continue
        n = len(w.get("slots", []))
        counts[key] = counts.get(key, 0) + n
    top = dict(sorted(counts.items(), key=lambda kv: -kv[1])[:_MAX_BREAKDOWN_KEYS])
    return top


def _opened_bottles(data: dict) -> list[dict]:
    """Détail des exemplaires actuellement OUVERTS, avec ancienneté d'ouverture.

    Exposé en attribut de sensor.whisky_opened (pas en entité par bouteille,
    pour ne pas faire exploser le nombre d'entités sur une grosse collection)
    afin de permettre des automatisations basées sur la durée d'ouverture —
    ex. brief §11 : "notifie-moi si une bouteille ouverte depuis plus de 6
    mois n'est toujours pas terminée" via un template Jinja lisant
    state_attr('sensor.whisky_ouvertes', 'bottles') | selectattr('days_open', 'gt', 180).
    Triée par ancienneté décroissante (les plus vieilles bouteilles ouvertes
    en premier, cas d'usage le plus courant).
    """
    today = date.today()
    out: list[dict] = []
    for w in _whiskies(data):
        for idx, s in enumerate(w.get("slots", [])):
            if s.get("bottle_status") != "opened":
                continue
            opened_date = s.get("opened_date")
            days_open = None
            if opened_date:
                try:
                    days_open = (today - date.fromisoformat(str(opened_date)[:10])).days
                except ValueError:
                    days_open = None
            out.append({
                "whisky_id": w.get("id"),
                "name": w.get("name", ""),
                "slot_idx": idx,
                "opened_date": opened_date,
                "days_open": days_open,
                "remaining_percent": s.get("remaining_percent"),
            })
    out.sort(key=lambda b: (b["days_open"] is None, -(b["days_open"] or 0)))
    return out


def _collection_value(data: dict) -> float:
    total = 0.0
    for w in _whiskies(data):
        unit = float(w.get("current_value") or 0) or float(w.get("price") or 0)
        if unit <= 0:
            continue
        n = sum(1 for s in w.get("slots", []) if s.get("bottle_status", "sealed") != "finished")
        total += unit * n
    return round(total, 2)


def _average_age(data: dict) -> float:
    ages = []
    for w in _whiskies(data):
        raw = (w.get("whisky_meta") or {}).get("age", "")
        try:
            age = float(str(raw).strip())
        except (TypeError, ValueError):
            continue
        if age > 0:
            ages.append(age)
    return round(sum(ages) / len(ages), 1) if ages else 0.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialise les sept capteurs globaux Whisky."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        WhiskyTotalSensor(hass, entry, entry_data),
        WhiskyOpenedSensor(hass, entry, entry_data),
        WhiskySealedSensor(hass, entry, entry_data),
        WhiskyFinishedSensor(hass, entry, entry_data),
        WhiskyDistilleriesSensor(hass, entry, entry_data),
        WhiskyCollectionValueSensor(hass, entry, entry_data),
        WhiskyAverageAgeSensor(hass, entry, entry_data),
    ], True)


class WhiskyBaseSensor(SensorEntity):
    """Capteur de base Whisky : se met à jour sur l'événement whisky_updated."""

    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, entry_data: dict) -> None:
        self.hass = hass
        self._entry = entry
        self._ed = entry_data

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self.hass.bus.async_listen(f"{DOMAIN}_updated", self._on_update)
        )

    @callback
    def _on_update(self, _event) -> None:
        self._ed["data"] = self.hass.data[DOMAIN][self._entry.entry_id]["data"]
        self.async_write_ha_state()

    @property
    def _data(self) -> dict:
        return self._ed["data"]


class WhiskyTotalSensor(WhiskyBaseSensor):
    """Nombre total de bouteilles (exemplaires physiques), tous statuts confondus."""

    _attr_icon = "mdi:bottle-tonic"
    _attr_native_unit_of_measurement = "bouteilles"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._attr_unique_id = f"{DOMAIN}_total"
        self._attr_name = "Whisky Total"

    @property
    def native_value(self) -> int:
        return len(_all_slots(self._data))

    @property
    def extra_state_attributes(self) -> dict:
        d = self._data
        return {
            "references": len(_whiskies(d)),
            "par_pays":       _breakdown(d, lambda w: (w.get("whisky_meta") or {}).get("country", "")),
            "par_region":     _breakdown(d, lambda w: (w.get("whisky_meta") or {}).get("region", "")),
            "par_distillerie":_breakdown(d, lambda w: (w.get("whisky_meta") or {}).get("distillery", "")),
            "par_type":       _breakdown(d, lambda w: (w.get("whisky_meta") or {}).get("whisky_type", "")),
            "par_tourbe":     _breakdown(d, lambda w: (
                "Tourbé" if (w.get("whisky_meta") or {}).get("peated") is True
                else "Non tourbé" if (w.get("whisky_meta") or {}).get("peated") is False
                else "Non renseigné"
            )),
        }


class WhiskyOpenedSensor(WhiskyBaseSensor):
    """Nombre de bouteilles ouvertes."""

    _attr_icon = "mdi:bottle-tonic-outline"
    _attr_native_unit_of_measurement = "bouteilles"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._attr_unique_id = f"{DOMAIN}_opened"
        self._attr_name = "Whisky Ouvertes"

    @property
    def native_value(self) -> int:
        return _count_by_status(self._data, "opened")

    @property
    def extra_state_attributes(self) -> dict:
        return {"bottles": _opened_bottles(self._data)}


class WhiskySealedSensor(WhiskyBaseSensor):
    """Nombre de bouteilles scellées (jamais ouvertes)."""

    _attr_icon = "mdi:bottle-tonic-plus"
    _attr_native_unit_of_measurement = "bouteilles"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._attr_unique_id = f"{DOMAIN}_sealed"
        self._attr_name = "Whisky Scellées"

    @property
    def native_value(self) -> int:
        return _count_by_status(self._data, "sealed")


class WhiskyFinishedSensor(WhiskyBaseSensor):
    """Nombre de bouteilles terminées."""

    _attr_icon = "mdi:bottle-tonic-skull"
    _attr_native_unit_of_measurement = "bouteilles"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._attr_unique_id = f"{DOMAIN}_finished"
        self._attr_name = "Whisky Terminées"

    @property
    def native_value(self) -> int:
        return _count_by_status(self._data, "finished")


class WhiskyDistilleriesSensor(WhiskyBaseSensor):
    """Nombre de distilleries distinctes représentées dans la collection."""

    _attr_icon = "mdi:factory"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._attr_unique_id = f"{DOMAIN}_distilleries"
        self._attr_name = "Whisky Distilleries"

    @property
    def native_value(self) -> int:
        names = {
            (w.get("whisky_meta") or {}).get("distillery", "").strip().lower()
            for w in _whiskies(self._data)
            if (w.get("whisky_meta") or {}).get("distillery", "").strip()
        }
        return len(names)


class WhiskyCollectionValueSensor(WhiskyBaseSensor):
    """Valeur du stock restant (bouteilles scellées + ouvertes, hors terminées)."""

    _attr_icon = "mdi:currency-eur"
    _attr_native_unit_of_measurement = "€"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._attr_unique_id = f"{DOMAIN}_collection_value"
        self._attr_name = "Whisky Valeur de la collection"

    @property
    def native_value(self) -> float:
        return _collection_value(self._data)

    @property
    def extra_state_attributes(self) -> dict:
        d = self._data
        n = len(_whiskies(d))
        avg = round(self.native_value / n, 2) if n else 0.0
        return {"prix_moyen": avg}


class WhiskyAverageAgeSensor(WhiskyBaseSensor):
    """Âge moyen des whiskies de la collection (par fiche, années déclarées uniquement)."""

    _attr_icon = "mdi:calendar-clock"
    _attr_native_unit_of_measurement = "ans"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._attr_unique_id = f"{DOMAIN}_average_age"
        self._attr_name = "Whisky Âge moyen"

    @property
    def native_value(self) -> float:
        return _average_age(self._data)
