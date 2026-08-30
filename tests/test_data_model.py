"""Tests du modèle de données bas niveau (commit 2/12) : _mk_slot,
_new_whisky_record, _slot_taken — utilisés par tous les services.
"""


def test_mk_slot_defaults_to_sealed(whisky_init):
    s = whisky_init._mk_slot("rack1", 2)
    assert s == {"rack_id": "rack1", "slot": 2, "bottle_status": "sealed"}


def test_mk_slot_invalid_status_falls_back_to_sealed(whisky_init):
    s = whisky_init._mk_slot("rack1", 0, bottle_status="not-a-status")
    assert s["bottle_status"] == "sealed"


def test_mk_slot_comment_and_size_only_set_when_truthy(whisky_init):
    s = whisky_init._mk_slot("rack1", 0, comment="", size=None)
    assert "comment" not in s and "size" not in s
    s2 = whisky_init._mk_slot("rack1", 0, comment="Coffret cadeau", size="70cl")
    assert s2["comment"] == "Coffret cadeau"
    assert s2["size"] == "70cl"


def test_new_whisky_record_shape(whisky_init):
    record = whisky_init._new_whisky_record(
        "Lagavulin 16", whisky_meta={"distillery": "Lagavulin"}, slots=[], price=45.5
    )
    assert record["name"] == "Lagavulin 16"
    assert record["beverage_type"] == "whisky"
    assert record["price"] == 45.5
    assert record["whisky_meta"]["distillery"] == "Lagavulin"
    # Les champs whisky_meta non fournis existent quand même, vides (pas de KeyError
    # côté carte/capteurs quand ils lisent w["whisky_meta"][...]).
    assert record["whisky_meta"]["region"] == ""
    assert record["favorite"] is False
    assert "id" in record and record["id"]


def test_slot_taken_detects_real_collisions(whisky_init):
    d = {"whiskies": [
        {"id": "w1", "slots": [{"rack_id": "shelf-A", "slot": 0, "bottle_status": "sealed"}]},
    ]}
    assert whisky_init._slot_taken(d, "shelf-A", 0) is True
    assert whisky_init._slot_taken(d, "shelf-A", 1) is False
    assert whisky_init._slot_taken(d, "shelf-B", 0) is False


def test_slot_taken_ignores_unplaced_bottles(whisky_init):
    """Régression commit 6 : un rack_id vide/falsy ('' ou None) ne doit JAMAIS
    entrer en collision avec un autre exemplaire non placé, sinon une seule
    bouteille "sans emplacement" pourrait exister dans toute la collection."""
    d = {"whiskies": [
        {"id": "w1", "slots": [{"rack_id": "", "slot": 0, "bottle_status": "sealed"}]},
        {"id": "w2", "slots": [{"rack_id": "", "slot": 0, "bottle_status": "sealed"}]},
    ]}
    assert whisky_init._slot_taken(d, "", 0) is False
    assert whisky_init._slot_taken(d, None, 0) is False


def test_slot_taken_exclusion_for_move(whisky_init):
    """move_slot doit pouvoir « déplacer » un exemplaire vers son propre
    emplacement actuel sans se bloquer lui-même."""
    d = {"whiskies": [
        {"id": "w1", "slots": [{"rack_id": "shelf-A", "slot": 0, "bottle_status": "sealed"}]},
    ]}
    assert whisky_init._slot_taken(d, "shelf-A", 0) is True
    assert whisky_init._slot_taken(
        d, "shelf-A", 0, exclude_whisky_id="w1", exclude_slot_idx=0
    ) is False
