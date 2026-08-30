"""Exécute les tests Node des fonctions pures de la carte (tests/manual/*.js)
depuis pytest, pour n'avoir qu'une seule commande (`pytest -q`) à lancer en
local et en CI. Les scripts eux-mêmes ne dépendent que de Node (aucun paquet
npm) — voir tests/manual/commit*_card_*.js pour le détail des assertions.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MANUAL_JS_TESTS = sorted((REPO_ROOT / "tests" / "manual").glob("commit*_card_*.js"))

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js n'est pas installé")


@pytest.mark.parametrize("script", MANUAL_JS_TESTS, ids=[p.name for p in MANUAL_JS_TESTS])
def test_card_pure_functions_js(script):
    result = subprocess.run(
        ["node", str(script)], cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, (
        f"{script.name} a échoué :\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_card_js_syntax_is_valid():
    card = REPO_ROOT / "custom_components" / "whisky" / "whisky-card.js"
    result = subprocess.run(
        ["node", "--check", str(card)], capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
