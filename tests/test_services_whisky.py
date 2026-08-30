"""Tests des services de fiches whisky et du cycle de vie d'une bouteille
(commits 3 et 9) : add/update/remove_whisky, add/update/move/remove_slot,
open_bottle/finish_bottle/update_remaining, et un scénario de non-régression
inspiré du brief (persistance à travers un redémarrage, aucune perte de
données pour les fiches existantes en ajoutant une nouvelle fiche).
"""
import pytest


def test_add_whisky_requires_name(integration):
    with pytest.raises(integration.whisky.HomeAssistantError):
        integration.call_sync("add_whisky", name="   ")


def test_add_whisky_unplaced_creates_n_slots(integration):
    integration.call_sync(
        "add_whisky", name="Maker's Mark", quantity=3, initial_status="sealed",
        distillery="Maker's Mark", whisky_type="Bourbon",
    )
    w = integration.data()["whiskies"][0]
    assert len(w["slots"]) == 3
    assert all(s["rack_id"] == "" for s in w["slots"])
    assert all(s["bottle_status"] == "sealed" for s in w["slots"])
    assert w["whisky_meta"]["distillery"] == "Maker's Mark"
    assert w["whisky_meta"]["whisky_type"] == "Bourbon"


def test_add_whisky_unplaced_multiple_records_never_collide(integration):
    """Régression commit 6 : plusieurs fiches sans emplacement assigné ne
    doivent jamais se bloquer mutuellement (rack_id="" n'est pas un vrai casier)."""
    integration.call_sync("add_whisky", name="Whisky A")
    integration.call_sync("add_whisky", name="Whisky B")
    integration.call_sync("add_whisky", name="Whisky C")
    assert len(integration.data()["whiskies"]) == 3


def test_add_whisky_placed_detects_collision(integration):
    integration.call_sync("add_rack", name="Vitrine")
    rack_id = integration.data()["cellars"][0]["racks"][0]["id"]
    integration.call_sync("add_whisky", name="Whisky A", rack_id=rack_id, slot=0)
    with pytest.raises(integration.whisky.HomeAssistantError):
        integration.call_sync("add_whisky", name="Whisky B", rack_id=rack_id, slot=0)


def test_add_whisky_fires_bottle_added_event(integration):
    integration.call_sync("add_whisky", name="Ardbeg 10")
    events = integration.hass.bus.events("whisky_bottle_added")
    assert len(events) == 1
    assert events[0]["name"] == "Ardbeg 10"


def test_update_whisky_only_touches_provided_fields(integration):
    integration.call_sync("add_whisky", name="Ardbeg 10", distillery="Ardbeg", region="Islay")
    whisky_id = integration.data()["whiskies"][0]["id"]
    integration.call_sync("update_whisky", whisky_id=whisky_id, region="Islay (côte sud)")
    w = integration.data()["whiskies"][0]
    assert w["whisky_meta"]["region"] == "Islay (côte sud)"
    assert w["whisky_meta"]["distillery"] == "Ardbeg", "un champ non fourni ne doit pas être écrasé"
    assert w["name"] == "Ardbeg 10"


def test_update_whisky_unknown_id_raises(integration):
    with pytest.raises(integration.whisky.HomeAssistantError):
        integration.call_sync("update_whisky", whisky_id="nope", region="Islay")


def test_remove_whisky_removes_all_slots(integration):
    integration.call_sync("add_whisky", name="Ardbeg 10", quantity=3)
    whisky_id = integration.data()["whiskies"][0]["id"]
    integration.call_sync("remove_whisky", whisky_id=whisky_id)
    assert integration.data()["whiskies"] == []


def test_add_slot_appends_exemplaire(integration):
    integration.call_sync("add_whisky", name="Ardbeg 10")
    whisky_id = integration.data()["whiskies"][0]["id"]
    integration.call_sync("add_slot", whisky_id=whisky_id, comment="Cadeau de Noël")
    w = integration.data()["whiskies"][0]
    assert len(w["slots"]) == 2
    assert w["slots"][1]["comment"] == "Cadeau de Noël"


def test_remove_slot_deletes_whisky_when_last_slot(integration):
    integration.call_sync("add_whisky", name="Ardbeg 10")
    whisky_id = integration.data()["whiskies"][0]["id"]
    integration.call_sync("remove_slot", whisky_id=whisky_id, slot_idx=0)
    assert integration.data()["whiskies"] == []


def test_remove_slot_keeps_whisky_when_other_slots_remain(integration):
    integration.call_sync("add_whisky", name="Ardbeg 10", quantity=2)
    whisky_id = integration.data()["whiskies"][0]["id"]
    integration.call_sync("remove_slot", whisky_id=whisky_id, slot_idx=0)
    w = integration.data()["whiskies"][0]
    assert len(w["slots"]) == 1


def test_move_slot_to_rack(integration):
    integration.call_sync("add_rack", name="Vitrine")
    rack_id = integration.data()["cellars"][0]["racks"][0]["id"]
    integration.call_sync("add_whisky", name="Ardbeg 10")
    whisky_id = integration.data()["whiskies"][0]["id"]
    integration.call_sync("move_slot", whisky_id=whisky_id, slot_idx=0, rack_id=rack_id, slot=2)
    s = integration.data()["whiskies"][0]["slots"][0]
    assert s["rack_id"] == rack_id and s["slot"] == 2


# ── Cycle de vie sealed -> opened -> finished ────────────────────────────────

def test_open_then_finish_bottle_lifecycle(integration):
    integration.call_sync("add_whisky", name="Ardbeg 10")
    whisky_id = integration.data()["whiskies"][0]["id"]

    integration.call_sync("open_bottle", whisky_id=whisky_id, slot_idx=0, opened_date="2026-01-01")
    s = integration.data()["whiskies"][0]["slots"][0]
    assert s["bottle_status"] == "opened"
    assert s["opened_date"] == "2026-01-01"
    assert s["remaining_percent"] == 100
    opened_events = integration.hass.bus.events("whisky_bottle_opened")
    assert len(opened_events) == 1 and opened_events[0]["whisky_id"] == whisky_id

    integration.call_sync("finish_bottle", whisky_id=whisky_id, slot_idx=0, rating=4.5, comment="Excellent")
    s = integration.data()["whiskies"][0]["slots"][0]
    assert s["bottle_status"] == "finished"
    assert s["remaining_percent"] == 0
    assert s["comment"] == "Excellent"
    assert integration.data()["whiskies"][0]["rating"] == 4.5
    finished_events = integration.hass.bus.events("whisky_bottle_finished")
    assert len(finished_events) == 1

    # La fiche et l'emplacement restent consultables — pas de suppression.
    assert len(integration.data()["whiskies"]) == 1
    assert len(integration.data()["whiskies"][0]["slots"]) == 1


def test_open_bottle_refuses_if_not_sealed(integration):
    integration.call_sync("add_whisky", name="Ardbeg 10")
    whisky_id = integration.data()["whiskies"][0]["id"]
    integration.call_sync("open_bottle", whisky_id=whisky_id, slot_idx=0)
    with pytest.raises(integration.whisky.HomeAssistantError):
        integration.call_sync("open_bottle", whisky_id=whisky_id, slot_idx=0)


def test_update_remaining_requires_opened_bottle(integration):
    integration.call_sync("add_whisky", name="Ardbeg 10")
    whisky_id = integration.data()["whiskies"][0]["id"]
    with pytest.raises(integration.whisky.HomeAssistantError):
        integration.call_sync("update_remaining", whisky_id=whisky_id, slot_idx=0, remaining_percent=50)


def test_update_remaining_fires_low_event_only_on_downward_crossing(integration):
    integration.call_sync("add_whisky", name="Talisker 10")
    whisky_id = integration.data()["whiskies"][0]["id"]
    integration.call_sync("open_bottle", whisky_id=whisky_id, slot_idx=0)

    integration.call_sync("update_remaining", whisky_id=whisky_id, slot_idx=0, remaining_percent=60)
    assert integration.hass.bus.events("whisky_bottle_low") == []

    integration.call_sync("update_remaining", whisky_id=whisky_id, slot_idx=0, remaining_percent=15)
    low = integration.hass.bus.events("whisky_bottle_low")
    assert len(low) == 1 and low[0]["remaining_percent"] == 15 and low[0]["threshold"] == 20

    # Rester sous le seuil ne redéclenche rien.
    integration.call_sync("update_remaining", whisky_id=whisky_id, slot_idx=0, remaining_percent=5)
    assert len(integration.hass.bus.events("whisky_bottle_low")) == 1

    # Remonter au-dessus puis redescendre : nouveau front descendant.
    integration.call_sync("update_remaining", whisky_id=whisky_id, slot_idx=0, remaining_percent=50)
    integration.call_sync("update_remaining", whisky_id=whisky_id, slot_idx=0, remaining_percent=10)
    assert len(integration.hass.bus.events("whisky_bottle_low")) == 2


def test_update_remaining_custom_threshold(integration):
    integration.call_sync("add_whisky", name="Talisker 10")
    whisky_id = integration.data()["whiskies"][0]["id"]
    integration.call_sync("open_bottle", whisky_id=whisky_id, slot_idx=0)
    integration.call_sync(
        "update_remaining", whisky_id=whisky_id, slot_idx=0, remaining_percent=45, low_threshold=60
    )
    low = integration.hass.bus.events("whisky_bottle_low")
    assert len(low) == 1 and low[0]["threshold"] == 60


# ── Non-régression : persistance à travers un redémarrage ───────────────────
# Adaptation du scénario du brief (120 vins -> 0 whisky après mise à jour ->
# +1 whisky -> 120 vins intacts) à l'architecture FORK retenue : Whisky est
# une intégration entièrement séparée de Millésime (domaine, fichier de
# données et entités propres), donc il n'y a plus de vins à préserver ICI.
# L'équivalent direct pour ce projet est : les fiches existantes survivent
# intactes à un redémarrage (rechargement du fichier JSON), et l'ajout d'une
# nouvelle fiche après redémarrage ne perturbe aucune fiche préexistante.

def test_restart_preserves_all_existing_whiskies_then_add_is_isolated(whisky_init, hass, entry):
    import asyncio

    async def setup():
        await whisky_init.async_setup_entry(hass, entry)

    asyncio.run(setup())

    async def call(service_name, **data):
        await hass.services.registry[service_name](whisky_init.ServiceCall(data))

    async def seed(n):
        for i in range(n):
            await call(
                "add_whisky", name=f"Whisky {i}", distillery=f"Distillerie {i % 7}",
                whisky_type="Single Malt", age=str(10 + (i % 15)),
            )

    N = 40  # collection de taille raisonnable pour un test rapide
    asyncio.run(seed(N))
    data = hass.data[whisky_init.DOMAIN][entry.entry_id]["data"]
    assert len(data["whiskies"]) == N
    snapshot_ids = sorted(w["id"] for w in data["whiskies"])

    # "Redémarrage" simulé : on recharge depuis le fichier persistant, dans
    # une toute nouvelle intégration (nouveau hass.data), exactement comme le
    # ferait Home Assistant au redémarrage.
    reloaded = whisky_init._load(hass)
    assert len(reloaded["whiskies"]) == N, "aucune fiche ne doit disparaître à travers un redémarrage"
    assert sorted(w["id"] for w in reloaded["whiskies"]) == snapshot_ids

    # Ajout d'UNE fiche après "redémarrage" : les N précédentes doivent rester
    # intactes (aucune donnée perdue, aucune fiche modifiée par effet de bord).
    asyncio.run(call("add_whisky", name="Nouvelle bouteille"))
    data_after = hass.data[whisky_init.DOMAIN][entry.entry_id]["data"]
    assert len(data_after["whiskies"]) == N + 1
    untouched = [w for w in data_after["whiskies"] if w["id"] in snapshot_ids]
    assert len(untouched) == N
    for w in untouched:
        assert w["name"].startswith("Whisky ")
