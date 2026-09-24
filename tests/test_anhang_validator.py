"""
test_anhang_validator.py
Tests des Anhang-Grounding-Validators (anhang.py) — das Herz der Halluzinations-
Abwehr. Prüft, dass pruefe_section eine Tatsachenbehauptung NUR durchlässt, wenn
sie centgenau aus der Wahrheit (Datenmodell/Sachverhalt) folgt, und sonst meckert:
  * Wert weicht ab            -> fehler
  * Quell-Pfad existiert nicht -> fehler
  * norm_refs leer            -> fehler
  * Typ C ohne escalation_flag -> fehler
  * Zahl in Prosa ohne Claim   -> warnung (mögliche Halluzination)
Plus: der Pfad-Resolver und die deterministische Typ-A-Tabelle (wahr per Konstruktion).
"""
from pathlib import Path

from anhang import (
    PfadFehler,
    aktive_sections,
    baue_anlagenspiegel_tabelle,
    finde_section,
    get_norm_text,
    pruefe_section,
    validate_disclosure,
    wert_aus_pfad,
)
from jahresabschluss import generate

BASE = Path(__file__).resolve().parent.parent
SALDENLISTE = BASE / "data/baeckerei_2025/Saldenliste.xlsx"
MAPPING = BASE / "mcp/config/skr03_mapping.json"
TAXONOMIE = BASE / "taxonomy"
ANLAGEN = BASE / "data/baeckerei_2025/Anlagenbuchhaltung.xlsx"


# ---- Pfad-Resolver ---------------------------------------------------------- #
def test_wert_aus_pfad_dict_index_und_filter():
    root = {"anlagenspiegel": {
        "summe": {"bw_gj": 943_000.0},
        "positionen": [{"konto": "0440", "bw_gj": 5}, {"konto": "0210", "bw_gj": 7}],
    }}
    assert wert_aus_pfad(root, "anlagenspiegel.summe.bw_gj") == 943_000.0
    assert wert_aus_pfad(root, "anlagenspiegel.positionen[0].konto") == "0440"
    assert wert_aus_pfad(root, "anlagenspiegel.positionen[konto=0210].bw_gj") == 7


def test_wert_aus_pfad_fehler():
    for bad in ("nope.gibts.nicht", "anlagenspiegel.positionen[99].konto"):
        try:
            wert_aus_pfad({"anlagenspiegel": {"positionen": []}}, bad)
        except PfadFehler:
            continue
        raise AssertionError(f"PfadFehler erwartet für {bad!r}")


# ---- get_norm_text ---------------------------------------------------------- #
def test_get_norm_text_treffer_und_fallback():
    c = get_norm_text("285", nummer="7")
    assert c is not None and c["paragraph"] == "285" and c.get("nummer") == "7"
    assert get_norm_text("9999") is None  # nicht existenter Paragraf


# ---- pruefe_section: Positiv + Negativ -------------------------------------- #
def _mitarbeiter_section(wert, text=None, refs=("§ 285 Nr. 7 HGB",)):
    block = {"typ": "prosa",
             "claims": [{"aussage": "Ø Arbeitnehmer GJ", "wert": wert,
                         "quelle": {"art": "sachverhalt", "pfad": "mitarbeiter.durchschnitt_gj"}}]}
    if text is not None:
        block["text"] = text
    return {"section_id": "mitarbeiter", "norm_refs": list(refs), "blocks": [block],
            "confidence": "hoch", "escalation_flag": False, "offene_punkte": []}


SACHVERHALT = {"mitarbeiter": {"durchschnitt_gj": 42}}


def test_pruefe_section_korrekte_claim_ok():
    res = pruefe_section(_mitarbeiter_section(42), {}, SACHVERHALT)
    assert res["ok"] is True, res["fehler"]
    assert res["geprueft"]["claims"] == 1


def test_pruefe_section_falscher_wert_fehler():
    res = pruefe_section(_mitarbeiter_section(99), {}, SACHVERHALT)
    assert res["ok"] is False
    assert any("behauptet" in f for f in res["fehler"])


def test_pruefe_section_norm_refs_leer_fehler():
    res = pruefe_section(_mitarbeiter_section(42, refs=()), {}, SACHVERHALT)
    assert res["ok"] is False
    assert any("norm_refs leer" in f for f in res["fehler"])


def test_pruefe_section_pfad_existiert_nicht_fehler():
    sec = _mitarbeiter_section(42)
    sec["blocks"][0]["claims"][0]["quelle"]["pfad"] = "mitarbeiter.gibts_nicht"
    res = pruefe_section(sec, {}, SACHVERHALT)
    assert res["ok"] is False
    assert any("existiert nicht" in f for f in res["fehler"])


def test_pruefe_section_geisterzahl_warnung():
    # Claim belegt nur 42; die 7 in der Prosa hat keine Claim -> Warnung.
    sec = _mitarbeiter_section(42, text="Durchschnittlich 42 Arbeitnehmer, davon 7 in Teilzeit.")
    res = pruefe_section(sec, {}, SACHVERHALT)
    assert any("durch keine Claim belegt" in w for w in res["warnungen"])


def test_pruefe_section_typ_c_ohne_flag_fehler():
    # Der Katalog hat keinen Typ-C-Fall; künstliche Section, damit die Regel getestet bleibt.
    typ_c = {**finde_section("grundanteil_hinweis"), "typ": "C"}
    sec = {"section_id": "grundanteil_hinweis", "norm_refs": ["§ 284 Abs. 2 Nr. 1 HGB"],
           "blocks": [], "confidence": "hoch", "escalation_flag": False, "offene_punkte": []}
    res = pruefe_section(sec, {}, {}, sections=[typ_c])
    assert res["ok"] is False
    assert any("Typ C" in f for f in res["fehler"])


# ---- Größenklassen-Filter (§288 Abs. 1) ------------------------------------- #
def test_aktive_sections_klein_ohne_anlagenspiegel():
    # Kleine GmbH: Anlagenspiegel (freiwillig) + organbezuege/nachtragsereignisse
    # (entfallen) tauchen NICHT im Pflicht-Anhang auf; Definitionen bleiben erhalten.
    ids = [s["id"] for s in aktive_sections("klein")]
    assert "anlagenspiegel" not in ids
    assert "organbezuege" not in ids
    assert "nachtragsereignisse" not in ids
    assert "bilanzierungs_bewertungsmethoden" in ids
    assert "allgemeine_angaben" in ids


def test_aktive_sections_klein_mit_freiwilligen_holt_anlagenspiegel():
    ids = [s["id"] for s in aktive_sections("klein", einschluss=("pflicht", "freiwillig"))]
    assert "anlagenspiegel" in ids  # Wissen bleibt abrufbar, nur nicht im Pflicht-Set


def test_aktive_sections_gross_laesst_alles_durch():
    # Erweiterungspfad: bei 'gross' sind Anlagenspiegel/organbezuege Pflicht.
    ids = [s["id"] for s in aktive_sections("gross")]
    assert "anlagenspiegel" in ids and "organbezuege" in ids


def test_aktive_sections_unbekannte_stufe_fehler():
    try:
        aktive_sections("klein", einschluss=("quatsch",))
    except ValueError:
        return
    raise AssertionError("ValueError für unbekannte Geltungs-Stufe erwartet")


# ---- Typ-A-Tabelle: wahr per Konstruktion ----------------------------------- #
def test_anlagenspiegel_tabelle_ist_geerdet():
    dm = generate(SALDENLISTE, MAPPING, TAXONOMIE, anlagenbuchhaltung=ANLAGEN)
    section = baue_anlagenspiegel_tabelle(dm)
    res = pruefe_section(section, dm, {})
    assert res["ok"] is True, res["fehler"]
    assert res["geprueft"]["claims"] > 0


# ---- validate_disclosure (§288 Abs. 1 Gating) ------------------------------ #
def test_validate_disclosure_leeres_verzeichnis_alle_fehlend():
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        res = validate_disclosure(tmpdir, "klein")
        assert res["ok"] is False
        assert res["fehlend"] == res["pflicht_sections"]
        assert res["vorhanden"] == []


def test_validate_disclosure_alle_vorhanden():
    import json
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmpdir:
        pflicht_ids = [s["id"] for s in aktive_sections("klein")]
        for sid in pflicht_ids:
            # Nicht-leeres Section-Objekt mit passender section_id (Platzhalter "{}"
            # erfüllt das gehärtete §288-Gate bewusst NICHT mehr).
            (Path(tmpdir) / f"{sid}.json").write_text(json.dumps({"section_id": sid}))
        res = validate_disclosure(tmpdir, "klein")
        assert res["ok"] is True
        assert res["fehlend"] == []
        assert res["ungueltig"] == []
        assert set(res["vorhanden"]) == set(pflicht_ids)


def test_validate_disclosure_leere_datei_ist_ungueltig():
    # Härtung Punkt 11: ein leeres {} oder JSON mit falscher section_id darf die
    # Vollständigkeit NICHT austricksen — Datei da, aber zählt als 'ungueltig'.
    import json
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmpdir:
        pflicht_ids = [s["id"] for s in aktive_sections("klein")]
        (Path(tmpdir) / f"{pflicht_ids[0]}.json").write_text("{}")               # leer
        (Path(tmpdir) / f"{pflicht_ids[1]}.json").write_text(json.dumps({"section_id": "falsch"}))  # falsche id
        for sid in pflicht_ids[2:]:
            (Path(tmpdir) / f"{sid}.json").write_text(json.dumps({"section_id": sid}))
        res = validate_disclosure(tmpdir, "klein")
        assert res["ok"] is False
        assert set(res["ungueltig"]) == {pflicht_ids[0], pflicht_ids[1]}
        assert res["fehlend"] == []
