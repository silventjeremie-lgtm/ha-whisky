"""Capteurs Whisky — squelette (commit 1). Étoffé au commit 4."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Aucun capteur pour l'instant — voir commit 4."""
    async_add_entities([], True)
