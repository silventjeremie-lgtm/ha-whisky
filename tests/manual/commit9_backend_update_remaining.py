# Test manuel (commit 9) : svc_update_remaining et le franchissement du seuil
# bas (whisky_bottle_low ne se déclenche qu'au FRONT DESCENDANT, jamais à
# chaque appel). À exécuter depuis la racine du dépôt :
# `python3 tests/manual/commit9_backend_update_remaining.py`.
# Stub minimal maison de Home Assistant (async_setup_entry est appelé pour
# de vrai, avec un hass/entry factices) — sera remplacé/complété par une
# suite pytest formelle au commit 10.
import sys, types, asyncio, tempfile, os

# ── Stubs minimalistes de Home Assistant, juste ce dont __init__.py a besoin ──
ha = types.ModuleType("homeassistant")

ha_components = types.ModuleType("homeassistant.components")
ha_ws = types.ModuleType("homeassistant.components.websocket_api")
def _identity_decorator_factory(*a, **k):
    def deco(f):
        return f
    return deco
ha_ws.websocket_command = _identity_decorator_factory
ha_ws.async_response = lambda f: f
ha_ws.async_register_command = lambda hass, cmd: None
ha_components.websocket_api = ha_ws

ha_config_entries = types.ModuleType("homeassistant.config_entries")
class ConfigEntry: pass
ha_config_entries.ConfigEntry = ConfigEntry

ha_core = types.ModuleType("homeassistant.core")
class HomeAssistant: pass
class ServiceCall:
    def __init__(self, data):
        self.data = data
ha_core.HomeAssistant = HomeAssistant
ha_core.ServiceCall = ServiceCall

ha_exceptions = types.ModuleType("homeassistant.exceptions")
class HomeAssistantError(Exception): pass
ha_exceptions.HomeAssistantError = HomeAssistantError

ha_helpers = types.ModuleType("homeassistant.helpers")
ha_helpers_aiohttp = types.ModuleType("homeassistant.helpers.aiohttp_client")
ha_helpers_aiohttp.async_get_clientsession = lambda hass: None

sys.modules["homeassistant"] = ha
sys.modules["homeassistant.components"] = ha_components
sys.modules["homeassistant.components.websocket_api"] = ha_ws
sys.modules["homeassistant.config_entries"] = ha_config_entries
sys.modules["homeassistant.core"] = ha_core
sys.modules["homeassistant.exceptions"] = ha_exceptions
sys.modules["homeassistant.helpers"] = ha_helpers
sys.modules["homeassistant.helpers.aiohttp_client"] = ha_helpers_aiohttp

sys.path.insert(0, "custom_components/whisky")
import importlib.util
spec = importlib.util.spec_from_file_location("whisky_init", "custom_components/whisky/__init__.py")
whisky = importlib.util.module_from_spec(spec)
spec.loader.exec_module(whisky)

# ── Fake hass / entry ──────────────────────────────────────────────────────
tmpdir = tempfile.mkdtemp()

class FakeConfig:
    def path(self, name):
        return os.path.join(tmpdir, name)

class FakeBus:
    def __init__(self):
        self.fired = []
    def async_fire(self, event, data):
        self.fired.append((event, data))

class FakeServices:
    def __init__(self):
        self.registry = {}
    def async_register(self, domain, name, func):
        self.registry[name] = func

class FakeConfigEntries:
    async def async_forward_entry_setups(self, entry, platforms):
        return None

class FakeHass:
    def __init__(self):
        self.data = {}
        self.config = FakeConfig()
        self.bus = FakeBus()
        self.services = FakeServices()
        self.config_entries = FakeConfigEntries()
        self.http = None
    async def async_add_executor_job(self, func, *args):
        return func(*args)
    def async_create_task(self, coro):
        coro.close()  # on ne l'exécute pas, on évite juste le warning "never awaited"

class FakeEntry:
    entry_id = "test_entry"
    options = {}
    data = {}
    def async_on_unload(self, f):
        pass
    def add_update_listener(self, f):
        return lambda: None

hass = FakeHass()
entry = FakeEntry()

asyncio.run(whisky.async_setup_entry(hass, entry))

svc = hass.services.registry
assert "update_remaining" in svc, "le service update_remaining doit être enregistré"
assert "open_bottle" in svc and "finish_bottle" in svc

# ── Prépare une fiche avec un exemplaire ouvert ──────────────────────────────
d = hass.data[whisky.DOMAIN][entry.entry_id]["data"]
d["whiskies"].append({
    "id": "w1", "name": "Talisker 10",
    "slots": [{"rack_id": "", "slot": 0, "bottle_status": "opened",
               "opened_date": "2026-01-01", "remaining_percent": 100}],
    "whisky_meta": {},
})

async def call(name, data):
    await svc[name](ServiceCall(data))

async def main():
    # 1) Descente 100 -> 60 : pas de franchissement du seuil par défaut (20)
    await call("update_remaining", {"whisky_id": "w1", "slot_idx": 0, "remaining_percent": 60})
    assert d["whiskies"][0]["slots"][0]["remaining_percent"] == 60
    low0 = [e for e in hass.bus.fired if e[0] == "whisky_bottle_low"]
    assert not low0, f"pas de whisky_bottle_low attendu à 60% (seuil 20) : {hass.bus.fired}"

    # 2) Descente 60 -> 15 : franchissement du seuil -> whisky_bottle_low
    await call("update_remaining", {"whisky_id": "w1", "slot_idx": 0, "remaining_percent": 15})
    assert d["whiskies"][0]["slots"][0]["remaining_percent"] == 15
    low_events = [e for e in hass.bus.fired if e[0] == "whisky_bottle_low"]
    assert len(low_events) == 1, f"un seul événement whisky_bottle_low attendu : {hass.bus.fired}"
    assert low_events[0][1]["remaining_percent"] == 15
    assert low_events[0][1]["threshold"] == 20

    # 3) Re-descente 15 -> 5 : toujours sous le seuil, PAS de nouveau front descendant
    await call("update_remaining", {"whisky_id": "w1", "slot_idx": 0, "remaining_percent": 5})
    low_events2 = [e for e in hass.bus.fired if e[0] == "whisky_bottle_low"]
    assert len(low_events2) == 1, f"aucun nouvel événement tant qu'on reste sous le seuil : {hass.bus.fired}"

    # 4) Remontée 5 -> 50 (ex. erreur de saisie corrigée) puis redescente sous 20 :
    #    nouveau front descendant -> nouvel événement.
    await call("update_remaining", {"whisky_id": "w1", "slot_idx": 0, "remaining_percent": 50})
    await call("update_remaining", {"whisky_id": "w1", "slot_idx": 0, "remaining_percent": 10})
    low_events3 = [e for e in hass.bus.fired if e[0] == "whisky_bottle_low"]
    assert len(low_events3) == 2, f"un nouveau franchissement doit re-déclencher l'événement : {hass.bus.fired}"

    # 5) update_remaining refusé sur une bouteille scellée
    d["whiskies"][0]["slots"].append({"rack_id": "", "slot": 1, "bottle_status": "sealed"})
    try:
        await call("update_remaining", {"whisky_id": "w1", "slot_idx": 1, "remaining_percent": 50})
        raise SystemExit("devrait avoir levé HomeAssistantError")
    except whisky.HomeAssistantError:
        pass

    # 6) seuil personnalisé (low_threshold)
    d["whiskies"][0]["slots"][0]["remaining_percent"] = 70
    hass.bus.fired.clear()
    await call("update_remaining", {"whisky_id": "w1", "slot_idx": 0, "remaining_percent": 45, "low_threshold": 60})
    low_events4 = [e for e in hass.bus.fired if e[0] == "whisky_bottle_low"]
    assert len(low_events4) == 1 and low_events4[0][1]["threshold"] == 60

    print("smoke_commit9_backend.py : OK (svc_update_remaining + franchissement de seuil)")

asyncio.run(main())
