"""
test_sachverhalt.py
Tests des Case-Facts-Loaders (sachverhalt.py): die Default-Datei lädt und
validiert; eine strukturell unvollständige Datei scheitert LAUT (Pflicht-Schema).
Fachliche Richtigkeit prüft der Mensch — hier nur die Struktur-Garantie.
"""
import json
from pathlib import Path

from sachverhalt import PFLICHT_TOP, get_sachverhalt

BASE = Path(__file__).resolve().parent.parent


def _expect_value_error(fn, marker):
    try:
        fn()
    except ValueError as e:
        assert marker.lower() in str(e).lower(), f"Falsche Meldung: {e}"
        return
    raise AssertionError(f"Erwarteter ValueError ({marker}) blieb aus.")


def test_default_sachverhalt_laedt_und_validiert():
    sv = get_sachverhalt()
    for k in PFLICHT_TOP:
        assert k in sv
    assert sv["stammdaten"].get("firma")  # Pflicht-Stammdatum vorhanden
    assert isinstance(sv["nachtragsereignisse"], list)


def test_fehlender_block_wirft(tmp_path):
    p = tmp_path / "kaputt.json"
    p.write_text(json.dumps({"stammdaten": {}}), encoding="utf-8")  # mitarbeiter/... fehlen
    _expect_value_error(lambda: get_sachverhalt(p), "unvollständig")


def test_fehlendes_stammdatum_wirft(tmp_path):
    p = tmp_path / "ohne_firma.json"
    voll = {k: ({} if k == "stammdaten" else []) for k in PFLICHT_TOP}
    voll["stammdaten"] = {"rechtsform": "GmbH"}  # firma fehlt
    p.write_text(json.dumps(voll), encoding="utf-8")
    _expect_value_error(lambda: get_sachverhalt(p), "stammdaten unvollständig")
