"""Fixtures pytest pour la suite de tests Whisky (commit 10/12).

Pas de dépendance à `pytest-homeassistant-custom-component` (paquet lourd,
tire l'intégralité de Home Assistant) : on stub ici, une seule fois par
session de test, uniquement les quelques symboles de `homeassistant.*`
réellement importés par `custom_components/whisky/__init__.py` et
`sensor.py`. C'est le même principe que les scripts `tests/manual/*.py`
ad-hoc des commits précédents, formalisé en fixtures réutilisables.

Limite connue (documentée aussi dans le README/limitations) : ce ne sont pas
de vrais objets Home Assistant, donc certains comportements réels de HA
(validation de schéma voluptuous stricte via `homeassistant.helpers.config_validation`,
cycle de vie réel des entités, etc.) ne sont pas exercés. Les tests portent
sur la LOGIQUE MÉTIER de l'intégration (modèle de données, services,
capteurs), qui est la partie spécifique à ce projet et donc celle qui a le
plus besoin d'être couverte.
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import tempfile
import types

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WHISKY_DIR = os.path.join(REPO_ROOT, "custom_components", "whisky")


def _install_ha_stubs() -> None:
    """Enregistre des modules homeassistant.* minimaux dans sys.modules.

    Idempotent : ne réinstalle rien si déjà fait (utile si plusieurs modules
    de test importent le package dans la même session pytest).
    """
    if getattr(_install_ha_stubs, "_done", False):
        return

    ha = types.ModuleType("homeassistant")

    ha_components = types.ModuleType("homeassistant.components")

    ha_components_sensor = types.ModuleType("homeassistant.components.sensor")

    class SensorEntity:  # noqa: D101 - stub
        pass

    ha_components_sensor.SensorEntity = SensorEntity

    ha_ws = types.ModuleType("homeassistant.components.websocket_api")

    def _decorator_factory(*_a, **_k):
        def deco(f):
            return f
        return deco

    ha_ws.websocket_command = _decorator_factory
    ha_ws.async_response = lambda f: f
    ha_ws.async_register_command = lambda hass, cmd: None
    ha_components.websocket_api = ha_ws

    ha_config_entries = types.ModuleType("homeassistant.config_entries")

    class ConfigEntry:  # noqa: D101 - stub
        pass

    ha_config_entries.ConfigEntry = ConfigEntry

    ha_core = types.ModuleType("homeassistant.core")

    class HomeAssistant:  # noqa: D101 - stub
        pass

    class ServiceCall:
        def __init__(self, data: dict | None = None) -> None:
            self.data = data or {}

    def callback(f):
        return f

    ha_core.HomeAssistant = HomeAssistant
    ha_core.ServiceCall = ServiceCall
    ha_core.callback = callback

    ha_exceptions = types.ModuleType("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        pass

    ha_exceptions.HomeAssistantError = HomeAssistantError

    ha_helpers = types.ModuleType("homeassistant.helpers")
    ha_helpers_aiohttp = types.ModuleType("homeassistant.helpers.aiohttp_client")
    ha_helpers_aiohttp.async_get_clientsession = lambda hass: None
    ha_helpers_entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")

    class AddEntitiesCallback:  # noqa: D101 - stub
        pass

    ha_helpers_entity_platform.AddEntitiesCallback = AddEntitiesCallback

    sys.modules["homeassistant"] = ha
    sys.modules["homeassistant.components"] = ha_components
    sys.modules["homeassistant.components.sensor"] = ha_components_sensor
    sys.modules["homeassistant.components.websocket_api"] = ha_ws
    sys.modules["homeassistant.config_entries"] = ha_config_entries
    sys.modules["homeassistant.core"] = ha_core
    sys.modules["homeassistant.exceptions"] = ha_exceptions
    sys.modules["homeassistant.helpers"] = ha_helpers
    sys.modules["homeassistant.helpers.aiohttp_client"] = ha_helpers_aiohttp
    sys.modules["homeassistant.helpers.entity_platform"] = ha_helpers_entity_platform

    # Le package `custom_components.whisky` doit exister dans sys.modules
    # AVANT de charger sensor.py, qui fait `from . import DOMAIN`.
    cc_pkg = types.ModuleType("custom_components")
    cc_pkg.__path__ = [os.path.join(REPO_ROOT, "custom_components")]
    sys.modules.setdefault("custom_components", cc_pkg)

    _install_ha_stubs._done = True


def _load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def whisky_init():
    """Module custom_components/whisky/__init__.py, chargé une fois par session."""
    _install_ha_stubs()
    whisky_pkg = types.ModuleType("custom_components.whisky")
    whisky_pkg.__path__ = [WHISKY_DIR]
    sys.modules["custom_components.whisky"] = whisky_pkg
    module = _load_module("custom_components.whisky", os.path.join(WHISKY_DIR, "__init__.py"))
    return module


@pytest.fixture(scope="session")
def whisky_sensor(whisky_init):
    """Module sensor.py — dépend de whisky_init pour que `from . import DOMAIN` fonctionne."""
    return _load_module("custom_components.whisky.sensor", os.path.join(WHISKY_DIR, "sensor.py"))


class FakeConfig:
    def __init__(self, config_dir: str) -> None:
        self._dir = config_dir

    def path(self, name: str) -> str:
        return os.path.join(self._dir, name)


class FakeBus:
    def __init__(self) -> None:
        self.fired: list[tuple[str, dict]] = []

    def async_fire(self, event: str, data: dict) -> None:
        self.fired.append((event, dict(data)))

    def events(self, event_type: str) -> list[dict]:
        return [data for evt, data in self.fired if evt == event_type]


class FakeServices:
    def __init__(self) -> None:
        self.registry: dict[str, object] = {}

    def async_register(self, domain: str, name: str, func) -> None:
        self.registry[name] = func

    async def call(self, name: str, data: dict, ServiceCall):
        return await self.registry[name](ServiceCall(data))


class FakeConfigEntries:
    async def async_forward_entry_setups(self, entry, platforms) -> None:
        return None


class FakeEntry:
    def __init__(self) -> None:
        self.entry_id = "test_entry"
        self.options: dict = {}
        self.data: dict = {}

    def async_on_unload(self, _f) -> None:
        return None

    def add_update_listener(self, _f):
        return lambda: None


class FakeHass:
    def __init__(self, config_dir: str) -> None:
        self.data: dict = {}
        self.config = FakeConfig(config_dir)
        self.bus = FakeBus()
        self.services = FakeServices()
        self.config_entries = FakeConfigEntries()
        self.http = None

    async def async_add_executor_job(self, func, *args):
        return func(*args)

    def async_create_task(self, coro):
        # On n'exécute jamais réellement la découverte Gemini en tâche de
        # fond dans les tests (pas de clé configurée par défaut) — on ferme
        # juste la coroutine pour éviter l'avertissement "never awaited".
        coro.close()


@pytest.fixture
def hass(tmp_path):
    return FakeHass(str(tmp_path))


@pytest.fixture
def entry():
    return FakeEntry()


@pytest.fixture
def integration(whisky_init, hass, entry):
    """Intégration Whisky initialisée (async_setup_entry déjà appelé).

    Retourne un petit objet avec `.whisky` (le module), `.hass`, `.entry` et
    `.call(name, data)` pour appeler un service enregistré comme le ferait
    Home Assistant (`hass.services.async_call`).
    """
    asyncio.run(whisky_init.async_setup_entry(hass, entry))

    class Integration:
        def __init__(self) -> None:
            self.whisky = whisky_init
            self.hass = hass
            self.entry = entry

        def data(self) -> dict:
            return hass.data[whisky_init.DOMAIN][entry.entry_id]["data"]

        async def call(self, service_name: str, **data):
            await hass.services.registry[service_name](whisky_init.ServiceCall(data))

        def call_sync(self, service_name: str, **data):
            """Variante synchrone de call() — pratique dans des tests non-async
            (pas de dépendance à pytest-asyncio pour un projet de cette taille).
            Le premier paramètre s'appelle `service_name` (pas `name`) car
            plusieurs services Whisky ont eux-mêmes un champ `name` (add_rack,
            add_cellar, add_whisky…) qui doit pouvoir être passé en kwarg."""
            asyncio.run(self.call(service_name, **data))

    return Integration()
