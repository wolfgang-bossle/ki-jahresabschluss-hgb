"""
test_schema_datenmodell.py
Prüft den Engine-Output gegen das formale JSON Schema
(mcp/config/jahresabschluss.schema.json, Draft 2020-12) — macht die PROJECT-§11-
Behauptung „gegen Datenmodell validiert" zum dauerhaften Gate statt Einmal-Ereignis:
  * Bäckerei (mit Anlagenspiegel)        -> schema-konform
  * Beratung + Einzelhandel (ohne)       -> schema-konform
  * manipuliertes Modell (Feld/Typ)      -> Validierung schlägt an (Schema beißt)
Läuft über tests/run.py (Commit-Gate) und pytest gleichermaßen.
"""
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from jahresabschluss import generate

BASE = Path(__file__).resolve().parent.parent
MAPPING = BASE / "mcp/config/skr03_mapping.json"
TAXONOMIE = BASE / "taxonomy"
SCHEMA = json.loads(
    (BASE / "mcp/config/jahresabschluss.schema.json").read_text(encoding="utf-8"))


def _fehler(dm) -> list[str]:
    Draft202012Validator.check_schema(SCHEMA)
    return [f"{'/'.join(map(str, e.path))}: {e.message}"
            for e in Draft202012Validator(SCHEMA).iter_errors(dm)]


def test_baeckerei_mit_anlagenspiegel_schema_konform():
    dm = generate(BASE / "data/baeckerei_2025/Saldenliste.xlsx", MAPPING, TAXONOMIE,
                  anlagenbuchhaltung=BASE / "data/baeckerei_2025/Anlagenbuchhaltung.xlsx")
    assert _fehler(dm) == []


def test_demo_mandanten_ohne_anlagenspiegel_schema_konform():
    for mandant in ("beratung_2025", "einzelhandel_2025"):
        dm = generate(BASE / f"data/{mandant}/Saldenliste.xlsx", MAPPING, TAXONOMIE)
        assert _fehler(dm) == [], mandant


def test_schema_beisst_bei_fehlendem_pflichtfeld():
    dm = generate(BASE / "data/baeckerei_2025/Saldenliste.xlsx", MAPPING, TAXONOMIE)
    del dm["metadata"]
    assert _fehler(dm), "Schema muss fehlendes Pflichtfeld melden"


def test_schema_beisst_bei_falschem_typ():
    dm = generate(BASE / "data/baeckerei_2025/Saldenliste.xlsx", MAPPING, TAXONOMIE)
    dm["bilanz"]["summe_aktiva_gj"] = "1700000"  # String statt Zahl
    assert _fehler(dm), "Schema muss falschen Typ melden"
