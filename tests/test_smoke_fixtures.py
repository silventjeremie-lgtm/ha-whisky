"""Vérifie que les fixtures conftest.py (stubs HA + intégration) fonctionnent."""


def test_integration_boots_and_registers_services(integration):
    reg = integration.hass.services.registry
    for name in (
        "add_rack", "update_rack", "remove_rack",
        "add_cellar", "rename_cellar", "remove_cellar",
        "add_whisky", "update_whisky", "remove_whisky",
        "add_slot", "update_slot", "move_slot", "remove_slot",
        "open_bottle", "finish_bottle", "update_remaining",
    ):
        assert name in reg, f"service manquant : {name}"


def test_data_starts_empty(integration):
    d = integration.data()
    assert d["whiskies"] == []
    assert len(d["cellars"]) == 1
