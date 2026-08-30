# Test manuel (commit 9) : _opened_bottles() dans sensor.py — attribut
# "bottles" de sensor.whisky_opened, utilisé par les automatisations basées
# sur la durée d'ouverture d'une bouteille (brief §11). À exécuter depuis la
# racine du dépôt : `python3 tests/manual/commit9_sensor_opened_bottles.py`.
# Stub minimal maison (pas de dépendance à Home Assistant réel) — sera
# remplacé/complété par une suite pytest formelle au commit 10.
import sys, types, importlib, importlib.util

# Stub minimal homeassistant modules needed by sensor.py's imports.
ha = types.ModuleType("homeassistant")
ha_components = types.ModuleType("homeassistant.components")
ha_components_sensor = types.ModuleType("homeassistant.components.sensor")
class SensorEntity: pass
ha_components_sensor.SensorEntity = SensorEntity
ha_config_entries = types.ModuleType("homeassistant.config_entries")
class ConfigEntry: pass
ha_config_entries.ConfigEntry = ConfigEntry
ha_core = types.ModuleType("homeassistant.core")
class HomeAssistant: pass
def callback(f): return f
ha_core.HomeAssistant = HomeAssistant
ha_core.callback = callback
ha_helpers = types.ModuleType("homeassistant.helpers")
ha_helpers_entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")
class AddEntitiesCallback: pass
ha_helpers_entity_platform.AddEntitiesCallback = AddEntitiesCallback

sys.modules["homeassistant"] = ha
sys.modules["homeassistant.components"] = ha_components
sys.modules["homeassistant.components.sensor"] = ha_components_sensor
sys.modules["homeassistant.config_entries"] = ha_config_entries
sys.modules["homeassistant.core"] = ha_core
sys.modules["homeassistant.helpers"] = ha_helpers
sys.modules["homeassistant.helpers.entity_platform"] = ha_helpers_entity_platform

# Stub the whisky package's __init__ (sensor.py does `from . import DOMAIN`).
whisky_pkg = types.ModuleType("custom_components.whisky")
whisky_pkg.__path__ = ["custom_components/whisky"]
whisky_pkg.DOMAIN = "whisky"
sys.modules["custom_components"] = types.ModuleType("custom_components")
sys.modules["custom_components"].__path__ = ["custom_components"]
sys.modules["custom_components.whisky"] = whisky_pkg

spec = importlib.util.spec_from_file_location(
    "custom_components.whisky.sensor", "custom_components/whisky/sensor.py"
)
sensor = importlib.util.module_from_spec(spec)
sys.modules["custom_components.whisky.sensor"] = sensor
spec.loader.exec_module(sensor)

from datetime import date, timedelta

old_date = (date.today() - timedelta(days=200)).isoformat()
recent_date = (date.today() - timedelta(days=5)).isoformat()

data = {
    "whiskies": [
        {
            "id": "w1", "name": "Lagavulin 16",
            "slots": [
                {"bottle_status": "opened", "opened_date": old_date, "remaining_percent": 40},
                {"bottle_status": "sealed"},
            ],
        },
        {
            "id": "w2", "name": "Ardbeg 10",
            "slots": [
                {"bottle_status": "opened", "opened_date": recent_date, "remaining_percent": 90},
                {"bottle_status": "finished", "finished_date": recent_date},
            ],
        },
        {
            "id": "w3", "name": "No date whisky",
            "slots": [{"bottle_status": "opened", "remaining_percent": 10}],
        },
    ]
}

bottles = sensor._opened_bottles(data)
assert len(bottles) == 3, f"expected 3 opened bottles, got {len(bottles)}"
# Sorted by days_open descending, None (no date) sorts last.
assert bottles[0]["whisky_id"] == "w1" and bottles[0]["days_open"] == 200, bottles[0]
assert bottles[1]["whisky_id"] == "w2" and bottles[1]["days_open"] == 5, bottles[1]
assert bottles[2]["whisky_id"] == "w3" and bottles[2]["days_open"] is None, bottles[2]
assert bottles[0]["remaining_percent"] == 40
assert bottles[0]["slot_idx"] == 0

opened_sensor_count = sensor._count_by_status(data, "opened")
assert opened_sensor_count == 3, opened_sensor_count

print("smoke_commit9_sensor.py : OK (_opened_bottles + tri par ancienneté)")
