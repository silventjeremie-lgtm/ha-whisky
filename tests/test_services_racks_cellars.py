"""Tests des services de structure physique (casiers/collections, commit 3/12) —
repris à l'identique de Millésime, déjà agnostiques du contenu, mais on les
couvre ici aussi car un régression y casserait le placement des whiskies."""
import pytest


def test_add_rack_default_capacity(integration):
    integration.call_sync("add_rack", name="Vitrine salon")
    d = integration.data()
    racks = d["cellars"][0]["racks"]
    assert len(racks) == 1
    rack = racks[0]
    assert rack["name"] == "Vitrine salon"
    assert rack["columns"] == 6 and rack["shelves"] == 3 and rack["levels"] == 1
    assert rack["slots"] == 6 * 3 * 1


def test_add_rack_custom_capacity_and_levels_clamped(integration):
    integration.call_sync("add_rack", name="Buffet", columns=4, shelves=2, levels=9)
    rack = integration.data()["cellars"][0]["racks"][0]
    assert rack["levels"] == 4, "levels doit être borné à 4 max"
    assert rack["slots"] == 4 * 2 * 4


def test_update_rack_recomputes_capacity(integration):
    integration.call_sync("add_rack", name="Buffet", columns=4, shelves=2, levels=1)
    rack_id = integration.data()["cellars"][0]["racks"][0]["id"]
    integration.call_sync("update_rack", rack_id=rack_id, columns=10, shelves=1)
    rack = integration.data()["cellars"][0]["racks"][0]
    assert rack["columns"] == 10 and rack["shelves"] == 1
    assert rack["slots"] == 10 * 1 * 1


def test_update_rack_unknown_id_raises(integration):
    with pytest.raises(integration.whisky.HomeAssistantError):
        integration.call_sync("update_rack", rack_id="does-not-exist", name="x")


def test_remove_rack(integration):
    integration.call_sync("add_rack", name="Buffet")
    rack_id = integration.data()["cellars"][0]["racks"][0]["id"]
    integration.call_sync("remove_rack", rack_id=rack_id)
    assert integration.data()["cellars"][0]["racks"] == []


def test_add_and_rename_cellar(integration):
    integration.call_sync("add_cellar", name="Bureau")
    cellars = integration.data()["cellars"]
    assert len(cellars) == 2
    new_id = cellars[1]["id"]
    integration.call_sync("rename_cellar", cellar_id=new_id, name="Cave du bureau")
    assert integration.data()["cellars"][1]["name"] == "Cave du bureau"


def test_remove_cellar_refuses_last_one(integration):
    with pytest.raises(integration.whisky.HomeAssistantError):
        integration.call_sync("remove_cellar", cellar_id=integration.data()["cellars"][0]["id"])


def test_remove_cellar_refuses_when_not_empty(integration):
    integration.call_sync("add_cellar", name="Bureau")
    new_id = integration.data()["cellars"][1]["id"]
    integration.call_sync("add_rack", name="Étagère", cellar_id=new_id)
    with pytest.raises(integration.whisky.HomeAssistantError):
        integration.call_sync("remove_cellar", cellar_id=new_id)


def test_remove_empty_cellar_succeeds(integration):
    integration.call_sync("add_cellar", name="Bureau")
    new_id = integration.data()["cellars"][1]["id"]
    integration.call_sync("remove_cellar", cellar_id=new_id)
    assert len(integration.data()["cellars"]) == 1
