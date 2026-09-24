"""
test_size_classes.py
Tests des Größenklassen-Gates (hgb_size_classes.py) — § 267 Abs. 1 i. V. m. Abs. 4 HGB.
Prüft, dass "klein" aus den Daten ABGELEITET wird (nicht geglaubt) und das Gate bei
"nicht klein" hart stoppt:
  * klein in GJ und VJ                     -> ok
  * eine Grenze GJ+VJ gerissen             -> nicht ok (Erleichterungen unzulässig)
  * Wechseljahr (nur ein Jahr reißt)        -> bleibt klein (§ 267 Abs. 4)
  * höchstens eins von drei Merkmalen über -> noch klein (mind. zwei eingehalten)
  * fehlende AN-Angabe / fehlender Umsatz   -> harter Fehler (§2.7, keine stille 0)
Plus: Live-Lauf gegen die echte Bäckerei-Saldenliste (Bilanzsumme = Anker 1.700.000).
"""
from pathlib import Path

from hgb_size_classes import (
    ARBEITNEHMER_MAX,
    BILANZSUMME_MAX,
    UMSATZERLOESE_MAX,
    pruefe_groessenklasse,
)
from jahresabschluss import generate

BASE = Path(__file__).resolve().parent.parent
SALDENLISTE = BASE / "data/baeckerei_2025/Saldenliste.xlsx"
MAPPING = BASE / "mcp/config/skr03_mapping.json"
TAXONOMIE = BASE / "taxonomy"


def _dm(bs_gj, bs_vj, um_gj, um_vj):
    """Minimal-Datenmodell mit den fürs Gate relevanten Feldern."""
    return {
        "bilanz": {"summe_aktiva_gj": bs_gj, "summe_aktiva_vj": bs_vj},
        "guv": {"positionen": [
            {"konzept": "de-gaap-ci_is.x.netSales", "wert_gj": um_gj, "wert_vj": um_vj},
        ]},
    }


def _sv(an_gj, an_vj):
    return {"mitarbeiter": {"durchschnitt_gj": an_gj, "durchschnitt_vj": an_vj}}


# ---- Größenklassen-Logik ---------------------------------------------------- #
def test_klein_in_gj_und_vj():
    r = pruefe_groessenklasse(_dm(1_700_000, 1_476_500, 3_800_000, 3_420_000), _sv(38, 35))
    assert r["ok"] is True
    assert r["groessenklasse"] == "klein"
    assert r["merkmale"]["gj"]["ueberschritten"] == []


def test_nicht_klein_alle_grenzen_gj_und_vj():
    r = pruefe_groessenklasse(
        _dm(9_000_000, 8_000_000, 20_000_000, 18_000_000), _sv(80, 70))
    assert r["ok"] is False
    assert r["groessenklasse"].startswith("nicht klein")
    assert set(r["merkmale"]["gj"]["ueberschritten"]) == {
        "Bilanzsumme", "Umsatzerlöse", "Arbeitnehmer"}


def test_wechseljahr_bleibt_klein():
    # GJ reißt alle Grenzen, VJ klar klein -> § 267 Abs. 4: erst ein Stichtag -> klein
    r = pruefe_groessenklasse(
        _dm(9_000_000, 1_000_000, 20_000_000, 2_000_000), _sv(80, 10))
    assert r["ok"] is True
    assert r["merkmale"]["gj"]["klein"] is False
    assert r["merkmale"]["vj"]["klein"] is True


def test_ein_merkmal_ueber_bleibt_klein():
    # Nur Umsatz über der Grenze (2 von 3 eingehalten) -> klein, beide Jahre
    r = pruefe_groessenklasse(
        _dm(1_000_000, 1_000_000, UMSATZERLOESE_MAX + 1, UMSATZERLOESE_MAX + 1),
        _sv(10, 10))
    assert r["ok"] is True
    assert r["merkmale"]["gj"]["ueberschritten"] == ["Umsatzerlöse"]


def test_grenze_exakt_ist_eingehalten():
    # "Überschreiten" ist strikt > : exakt auf der Grenze = eingehalten
    r = pruefe_groessenklasse(
        _dm(BILANZSUMME_MAX, BILANZSUMME_MAX, UMSATZERLOESE_MAX, UMSATZERLOESE_MAX),
        _sv(ARBEITNEHMER_MAX, ARBEITNEHMER_MAX))
    assert r["ok"] is True
    assert r["merkmale"]["gj"]["ueberschritten"] == []


def test_fehlende_arbeitnehmer_angabe_ist_harter_fehler():
    try:
        pruefe_groessenklasse(_dm(1, 1, 1, 1), {"mitarbeiter": {}})
        assert False, "ValueError erwartet"
    except ValueError as e:
        assert "durchschnitt" in str(e)


def test_fehlendes_umsatzkonzept_ist_harter_fehler():
    try:
        pruefe_groessenklasse(
            {"bilanz": {"summe_aktiva_gj": 1, "summe_aktiva_vj": 1},
             "guv": {"positionen": []}}, _sv(10, 10))
        assert False, "ValueError erwartet"
    except ValueError as e:
        assert "netSales" in str(e)


# ---- Live gegen die echte Saldenliste --------------------------------------- #
def test_live_baeckerei_ist_klein():
    dm = generate(SALDENLISTE, MAPPING, TAXONOMIE)
    r = pruefe_groessenklasse(dm, _sv(38, 35))
    assert r["ok"] is True
    # Bilanzsumme = verifizierter Anker
    assert r["merkmale"]["gj"]["bilanzsumme"] == 1_700_000.0
    assert r["merkmale"]["gj"]["umsatzerloese"] == 3_800_000.0
