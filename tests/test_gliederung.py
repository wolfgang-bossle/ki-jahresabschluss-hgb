"""
test_gliederung.py
Prüft die Darstellung nach gesetzlichem Gliederungsschema (gliederung.py):
  * GuV in Staffelform § 275 Abs. 2: Postenfolge nach Nummern, keine
    Taxonomie-Hilfssummen, kein Rohergebnis neben Nr. 1 bis 5 (§ 276)
  * Bilanz mit Bezeichnungen aus § 266, Werte unverändert aus dem Datenmodell
  * alle drei Musterfälle vollständig gegliedert
  * ein Konto-Konzept ohne Posten -> harter Fehler (kein stiller Wegfall)
Datenagnostisch: die Konzepte im Negativtest sind synthetisch.
"""
from pathlib import Path

from gliederung import gliedere
from jahresabschluss import generate

BASE = Path(__file__).resolve().parent.parent
MAPPING = BASE / "mcp/config/skr03_mapping.json"
TAXONOMIE = BASE / "taxonomy"
HILFSSUMMEN = ("Betriebsergebnis", "Gesamtleistung", "Rohergebnis", "Finanz- und Beteiligungsergebnis")


def _dm(mandant):
    d = BASE / "data" / mandant
    ab = d / "Anlagenbuchhaltung.xlsx"
    return generate(d / "Saldenliste.xlsx", MAPPING, TAXONOMIE,
                    anlagenbuchhaltung=ab if ab.exists() else None)


def test_guv_staffelform_275_abs2():
    dm = _dm("baeckerei_2025")
    posten = gliedere(dm["guv"]["positionen"], "guv")
    labels = [p["label"] for p in posten]
    assert labels[0] == "1. Umsatzerlöse"
    assert labels[-1] == "17. Jahresüberschuss/Jahresfehlbetrag"
    assert not any(h in l for l in labels for h in HILFSSUMMEN)
    nummern = [int(l.split(".")[0]) for l in labels if l.split(".")[0].isdigit()]
    assert nummern == sorted(nummern)
    assert posten[-1]["wert_gj"] == dm["guv"]["jahresueberschuss_gj"]


def test_bilanz_bezeichnungen_266_werte_unveraendert():
    dm = _dm("baeckerei_2025")
    werte = {p["konzept"]: p["wert_gj"] for p in dm["bilanz"]["passiva"]}
    posten = gliedere(dm["bilanz"]["passiva"], "passiva")
    assert [p["label"] for p in posten][:2] == ["A. Eigenkapital", "I. Gezeichnetes Kapital"]
    assert all(p["wert_gj"] == werte[p["konzept"]] for p in posten)


def test_alle_musterfaelle_gegliedert():
    for mandant in ("baeckerei_2025", "beratung_2025", "einzelhandel_2025"):
        dm = _dm(mandant)
        for teil, pos in (("aktiva", dm["bilanz"]["aktiva"]),
                          ("passiva", dm["bilanz"]["passiva"]),
                          ("guv", dm["guv"]["positionen"])):
            assert gliedere(pos, teil), (mandant, teil)


def test_konzept_ohne_posten_ist_fehler():
    gl = {"guv": [{"gliederung": "17.", "bezeichnung": "JÜ", "konzept": "x_is",
                   "posten": [{"gliederung": "a)", "bezeichnung": "A", "konzept": "x_is.a"}]}]}
    pos = [{"konzept": "x_is", "wert_gj": 2.0}, {"konzept": "x_is.a", "wert_gj": 1.0},
           {"konzept": "x_is.b", "wert_gj": 1.0}]
    try:
        gliedere(pos, "guv", gl)
    except ValueError as e:
        assert "x_is.b" in str(e)
    else:
        raise AssertionError("Konzept ohne Posten wurde stillschweigend weggelassen")
