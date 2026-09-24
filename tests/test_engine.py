"""
test_engine.py
Tests der Bilanz/GuV/Anlagenspiegel-Engine (jahresabschluss.py + anlagenspiegel.py).
Deckt den bisher nur von verify.py abgedeckten Happy-Path als echte Tests ab UND —
neu — die Negativpfade (der eiserne Grundsatz muss LAUT scheitern, nie still):
  * fehlende Tabelle-B-Zuordnung  -> ValueError
  * unausgeglichene Bilanz        -> ValueError (Bilanzprobe != 0)
Datenagnostisch: die Synthetik-Konten hier sind Testdaten, kein Engine-Code (§2.1).
"""
from pathlib import Path

import openpyxl

from jahresabschluss import generate

BASE = Path(__file__).resolve().parent.parent
SALDENLISTE = BASE / "data/baeckerei_2025/Saldenliste.xlsx"
MAPPING = BASE / "mcp/config/skr03_mapping.json"
TAXONOMIE = BASE / "taxonomy"
ANLAGEN = BASE / "data/baeckerei_2025/Anlagenbuchhaltung.xlsx"

# Centgenau verifizierte Anker (Spiegel von scripts/verify.py, hier als Test gefasst)
ANKER_AKTIVA_GJ = 1_700_000.0
ANKER_JUE_GJ = 200_000.0
ANKER_BW_GJ = 943_000.0
ANKER_AFA = 83_500.0


def _expect_value_error(fn, marker):
    """Hilfs-Assert: fn() muss ValueError werfen, dessen Text 'marker' enthält."""
    try:
        fn()
    except ValueError as e:
        assert marker.lower() in str(e).lower(), f"Falsche ValueError-Meldung: {e}"
        return
    raise AssertionError(f"Erwarteter ValueError ({marker}) blieb aus.")


def _write_saldenliste(path, rows):
    """Schreibt eine Mini-Saldenliste im 4-Spalten-Format (Konto/Bez./GJ/VJ)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Konto", "Bezeichnung", "Saldo GJ", "Saldo VJ"])  # Kopfzeile (min_row=2)
    for r in rows:
        ws.append(list(r))
    wb.save(path)


def test_demo_bilanz_balanciert_und_anker_centgenau():
    dm = generate(SALDENLISTE, MAPPING, TAXONOMIE, anlagenbuchhaltung=ANLAGEN)
    b, m = dm["bilanz"], dm["metadata"]
    # Bilanzprobe hart = 0
    assert m["bilanzprobe_gj"] == 0.0 and m["bilanzprobe_vj"] == 0.0
    assert round(b["summe_aktiva_gj"], 2) == round(b["summe_passiva_gj"], 2)
    # Anker
    assert round(b["summe_aktiva_gj"], 2) == ANKER_AKTIVA_GJ
    assert round(dm["guv"]["jahresueberschuss_gj"], 2) == ANKER_JUE_GJ
    assert dm["metadata"]["jue_abgestimmt"] is True


def test_anlagenspiegel_reconciliation():
    dm = generate(SALDENLISTE, MAPPING, TAXONOMIE, anlagenbuchhaltung=ANLAGEN)
    rc = dm["anlagenspiegel"]["reconciliation"]
    assert rc["abgestimmt"] is True
    assert round(rc["bw_gj"], 2) == ANKER_BW_GJ
    # Σ AfA Anlagenspiegel == AfA-Aufwand Saldenliste (centgenau)
    assert round(rc["afa_jahr"], 2) == round(rc["afa_aufwand_saldenliste"], 2) == ANKER_AFA


def test_jue_fliesst_in_passiva_und_haelt_bilanz():
    # Ohne JÜ-Einstellung wäre die Bilanz nicht ausgeglichen -> JÜ-Ableitung ist die Brücke.
    dm = generate(SALDENLISTE, MAPPING, TAXONOMIE, anlagenbuchhaltung=ANLAGEN)
    passiva_konzepte = {p["konzept"] for p in dm["bilanz"]["passiva"]}
    assert any("netIncome" in c for c in passiva_konzepte)


def test_konto_ohne_mapping_wirft(tmp_path):
    # Konto 9999 existiert nicht in der Tabelle B -> harter Fehler, kein stilles Ignorieren.
    sl = tmp_path / "saldenliste_unmapped.xlsx"
    _write_saldenliste(sl, [("9999", "Unbekanntes Konto", 100.0, 0.0)])
    _expect_value_error(
        lambda: generate(sl, MAPPING, TAXONOMIE),
        "ohne Tabelle-B-Zuordnung",
    )


def test_keine_guv_konten_wirft(tmp_path):
    # Nur ein Bilanzkonto, keine GuV -> JÜ nicht ableitbar -> sauberer Fehler
    # (statt nacktem StopIteration).
    sl = tmp_path / "saldenliste_ohne_guv.xlsx"
    _write_saldenliste(sl, [("0210", "Grundstücke", 500_000.0, 0.0)])
    _expect_value_error(
        lambda: generate(sl, MAPPING, TAXONOMIE),
        "keine GuV-Konten",
    )


def test_unausgeglichene_bilanz_wirft(tmp_path):
    # Aktivkonto 500k, dazu ein Ertrag 100k (-> JÜ 100k in die Passiva). Aktiva 500k
    # != Passiva 100k -> Bilanzprobe scheitert (eiserner Grundsatz, nie still).
    sl = tmp_path / "saldenliste_unbalanced.xlsx"
    _write_saldenliste(sl, [
        ("0210", "Grundstücke", 500_000.0, 0.0),
        ("8400", "Umsatzerlöse", 100_000.0, 0.0),
    ])
    _expect_value_error(
        lambda: generate(sl, MAPPING, TAXONOMIE),
        "nicht ausgeglichen",
    )
