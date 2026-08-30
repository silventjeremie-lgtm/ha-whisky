"""Tests des fonctions de calcul de sensor.py (commits 4 et 9)."""
from datetime import date, timedelta


def _data(whiskies):
    return {"whiskies": whiskies}


def test_count_by_status(whisky_sensor):
    d = _data([
        {"slots": [{"bottle_status": "sealed"}, {"bottle_status": "opened"}]},
        {"slots": [{"bottle_status": "sealed"}]},
    ])
    assert whisky_sensor._count_by_status(d, "sealed") == 2
    assert whisky_sensor._count_by_status(d, "opened") == 1
    assert whisky_sensor._count_by_status(d, "finished") == 0


def test_breakdown_counts_by_slot_not_by_fiche(whisky_sensor):
    d = _data([
        {"whisky_meta": {"country": "Écosse"}, "slots": [{}, {}]},
        {"whisky_meta": {"country": "USA"}, "slots": [{}]},
        {"whisky_meta": {"country": ""}, "slots": [{}, {}, {}]},  # ignoré (clé vide)
    ])
    breakdown = whisky_sensor._breakdown(d, lambda w: (w.get("whisky_meta") or {}).get("country", ""))
    assert breakdown == {"Écosse": 2, "USA": 1}


def test_breakdown_caps_at_max_keys(whisky_sensor):
    whiskies = [
        {"whisky_meta": {"country": f"Pays {i}"}, "slots": [{}]}
        for i in range(whisky_sensor._MAX_BREAKDOWN_KEYS + 10)
    ]
    breakdown = whisky_sensor._breakdown(_data(whiskies), lambda w: (w.get("whisky_meta") or {}).get("country", ""))
    assert len(breakdown) == whisky_sensor._MAX_BREAKDOWN_KEYS


def test_collection_value_excludes_finished_bottles(whisky_sensor):
    d = _data([
        {"current_value": 75, "slots": [{"bottle_status": "sealed"}, {"bottle_status": "opened"}]},
        {"price": 45, "slots": [{"bottle_status": "finished"}]},
        {"current_value": 30, "slots": [{"bottle_status": "sealed"}, {"bottle_status": "sealed"}]},
    ])
    # 75*2 (sealed+opened) + 45*0 (le seul exemplaire est fini) + 30*2 = 210
    assert whisky_sensor._collection_value(d) == 210.0


def test_collection_value_prefers_current_value_over_price(whisky_sensor):
    d = _data([{"current_value": 100, "price": 40, "slots": [{"bottle_status": "sealed"}]}])
    assert whisky_sensor._collection_value(d) == 100.0


def test_average_age_ignores_non_numeric_and_missing(whisky_sensor):
    d = _data([
        {"whisky_meta": {"age": "16"}},
        {"whisky_meta": {"age": "10"}},
        {"whisky_meta": {"age": "NAS"}},  # non-numérique, ignoré
        {"whisky_meta": {}},              # absent, ignoré
    ])
    assert whisky_sensor._average_age(d) == 13.0


def test_average_age_empty_collection_is_zero(whisky_sensor):
    assert whisky_sensor._average_age(_data([])) == 0.0


def test_opened_bottles_computes_days_open_and_sorts_oldest_first(whisky_sensor):
    old_date = (date.today() - timedelta(days=200)).isoformat()
    recent_date = (date.today() - timedelta(days=5)).isoformat()
    d = _data([
        {
            "id": "w1", "name": "Lagavulin 16",
            "slots": [
                {"bottle_status": "opened", "opened_date": old_date, "remaining_percent": 40},
                {"bottle_status": "sealed"},
            ],
        },
        {
            "id": "w2", "name": "Ardbeg 10",
            "slots": [{"bottle_status": "opened", "opened_date": recent_date, "remaining_percent": 90}],
        },
        {
            "id": "w3", "name": "Sans date",
            "slots": [{"bottle_status": "opened", "remaining_percent": 10}],
        },
    ])
    bottles = whisky_sensor._opened_bottles(d)
    assert [b["whisky_id"] for b in bottles] == ["w1", "w2", "w3"]
    assert bottles[0]["days_open"] == 200
    assert bottles[1]["days_open"] == 5
    assert bottles[2]["days_open"] is None
    assert bottles[0]["remaining_percent"] == 40
    assert bottles[0]["slot_idx"] == 0


def test_opened_bottles_ignores_non_opened_slots(whisky_sensor):
    d = _data([{"id": "w1", "name": "X", "slots": [
        {"bottle_status": "sealed"}, {"bottle_status": "finished"},
    ]}])
    assert whisky_sensor._opened_bottles(d) == []


def test_whisky_opened_sensor_exposes_bottles_attribute(whisky_sensor, integration):
    """Vérifie l'intégration bout-en-bout : le service open_bottle change bien
    l'état vu par le capteur (via les mêmes helpers que ci-dessus)."""
    integration.call_sync("add_whisky", name="Talisker 10")
    whisky_id = integration.data()["whiskies"][0]["id"]
    integration.call_sync("open_bottle", whisky_id=whisky_id, slot_idx=0, opened_date="2026-01-01")
    bottles = whisky_sensor._opened_bottles(integration.data())
    assert len(bottles) == 1
    assert bottles[0]["whisky_id"] == whisky_id
    assert bottles[0]["opened_date"] == "2026-01-01"
