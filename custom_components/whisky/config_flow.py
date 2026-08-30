"""Config flow Whisky v0.1.0.

Repris du config flow Millésime (même mécanique, même tolérance de
validation de clé) : projet dérivé indépendant, voir LICENSE.
"""
from __future__ import annotations
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from . import DOMAIN

GEMINI_HELP = (
    "Optionnel mais recommandé. "
    "Obtenez votre clé gratuite ici (compte Google requis) : "
    "https://aistudio.google.com/app/apikey\n"
    "→ Cliquez 'Create API Key' → Copiez la clé → Collez-la ci-dessous.\n"
    "Limite gratuite : 1 500 requêtes/jour (gemini-1.5-flash).\n"
    "Sans clé, l'ajout de whiskies se fait uniquement à la main "
    "(aucune base de données whisky ouverte fiable en repli)."
)


def _clean_key(raw: str | None) -> str:
    """Nettoie une clé Gemini saisie (espaces, guillemets éventuels collés au copier-coller)."""
    key = (raw or "").strip()
    if len(key) >= 2 and key[0] in "\"'" and key[-1] in "\"'":
        key = key[1:-1].strip()
    return key


def _key_looks_invalid(key: str) -> bool:
    """Validation souple : la clé n'est rejetée que si elle est manifestement erronée."""
    if not key:
        return False  # vide = pas de clé, autorisé (saisie manuelle uniquement)
    if any(c.isspace() for c in key):
        return True
    if len(key) < 20:
        return True
    return False


class WhiskyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow pour Whisky."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Étape de configuration initiale."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}

        if user_input is not None:
            key = _clean_key(user_input.get("gemini_api_key"))
            if _key_looks_invalid(key):
                errors["gemini_api_key"] = "invalid_key"
            else:
                user_input["gemini_api_key"] = key
                return self.async_create_entry(
                    title=user_input.get("collection_name", "Whisky"),
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema({
                vol.Required("collection_name", default="Whisky"): str,
                vol.Optional("gemini_api_key", default=""): str,
            }),
            description_placeholders={"gemini_help": GEMINI_HELP},
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Retourne le flow d'options (modifier la clé après installation)."""
        return WhiskyOptionsFlow(config_entry)


class WhiskyOptionsFlow(config_entries.OptionsFlow):
    """Permet de modifier la clé Gemini après installation."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            key = _clean_key(user_input.get("gemini_api_key"))
            if _key_looks_invalid(key):
                errors["gemini_api_key"] = "invalid_key"
            else:
                return self.async_create_entry(
                    title="",
                    data={"gemini_api_key": key},
                )

        current_key = self._config_entry.options.get(
            "gemini_api_key",
            self._config_entry.data.get("gemini_api_key", ""),
        )

        return self.async_show_form(
            step_id="init",
            errors=errors,
            data_schema=vol.Schema({
                vol.Optional("gemini_api_key", default=current_key): str,
            }),
            description_placeholders={"gemini_help": GEMINI_HELP},
        )
