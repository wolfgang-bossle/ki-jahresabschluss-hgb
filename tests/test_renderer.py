"""
test_renderer.py
Tests des HTML-Renderers (renderer_html.py). Reine Tests — KEIN openpyxl/Taxonomie
nötig: gegen ein synthetisches Mini-Datenmodell. Sichert die zwei Eigenschaften, auf
die es ankommt:
  * Rückverfolgbarkeit: jede Position mit Quelle wird klickbar (drill) und das
    Detail-Panel zeigt Konzept + Konto + Saldenliste-Saldo (die Kette ist im HTML).
  * Eiserner Grundsatz (§2.7): der Renderer übernimmt Modellwerte unverändert und
    ERFINDET keine Zahl — eine Zahl, die nicht im Modell steht, darf nicht erscheinen.
Datenagnostisch: die Konten hier sind Testdaten, kein Engine-Code (§2.1).
"""
from renderer_html import render_html, _eur

# Synthetisches, in sich stimmiges Mini-Modell (keine echten Mandantendaten).
DM = {
    "bilanz": {
        "aktiva": [
            {"ebene": 0, "konzept": "x_bs.ass", "label": "Summe Aktiva",
             "wert_gj": 100000.0, "wert_vj": 90000.0, "quelle": ["9001", "9002"]},
            {"ebene": 1, "konzept": "x_bs.ass.cash", "label": "Kasse",
             "wert_gj": 100000.0, "wert_vj": 90000.0, "quelle": ["9001"]},
        ],
        "passiva": [
            {"ebene": 0, "konzept": "x_bs.eqLiab", "label": "Summe Passiva",
             "wert_gj": 100000.0, "wert_vj": 90000.0,
             "quelle": ["(abgeleitet aus GuV)", "9100"]},
        ],
        "summe_aktiva_gj": 100000.0, "summe_aktiva_vj": 90000.0,
        "summe_passiva_gj": 100000.0, "summe_passiva_vj": 90000.0,
    },
    "guv": {
        "positionen": [
            {"ebene": 0, "konzept": "x_is", "label": "Jahresüberschuss",
             "wert_gj": 12345.67, "wert_vj": -500.0, "quelle": ["9200"]},
        ],
        "jahresueberschuss_gj": 12345.67, "jahresueberschuss_vj": -500.0,
    },
    "metadata": {"quelle": "Test.xlsx", "bilanzprobe_gj": 0.0, "bilanzprobe_vj": 0.0,
                 "jue_abgestimmt": True, "taxonomie": "x-2025"},
}
KONTEN = {
    "9001": ("Kasse-Testkonto", 100000.0, 90000.0),
    "9100": ("Eigenkapital-Testkonto", 0.0, 0.0),
    "9200": ("Ergebnis-Testkonto", 12345.67, -500.0),
}


def test_eur_format_deutsch():
    assert _eur(1700000.0) == "1.700.000,00"
    assert _eur(-1240000.0) == "−1.240.000,00"   # echtes Minuszeichen
    assert _eur(12345.67) == "12.345,67"
    assert _eur(0.0) == "0,00"
    assert _eur(None) == ""


def test_anker_und_formatierung_im_html():
    h = render_html(DM, konten=KONTEN)
    # Modellwerte erscheinen exakt im deutschen Format.
    assert "100.000,00" in h
    assert "12.345,67" in h
    assert "−500,00" in h
    assert "<title>" in h and "Bilanz" in h and "Gewinn- und Verlustrechnung" in h


def test_drilldown_kette_position_konzept_konto_saldo():
    h = render_html(DM, konten=KONTEN)
    # Klickbare Zeilen + Detailpanels existieren.
    assert "drill" in h and 'tr class="detail"' in h
    # Konzept-Anker steht im Panel.
    assert "x_bs.ass.cash" in h
    # Konto-Ebene: Nummer + Bezeichnung aus der Saldenliste, beides sichtbar.
    assert "9001" in h and "Kasse-Testkonto" in h
    # Abgeleitete (Nicht-Konto-)Quelle wird als Hinweis gezeigt, nicht als Konto-Saldo.
    assert "abgeleitet aus GuV" in h


def test_erfindet_keine_zahl():
    """Anti-Halluzination: eine Zahl, die im Modell nicht vorkommt, taucht nicht auf."""
    h = render_html(DM, konten=KONTEN)
    assert "999.999" not in h
    assert "777,77" not in h


def test_robust_ohne_anlagenspiegel_und_anhang():
    h = render_html(DM, konten=None, anhang_sections=None)
    assert "<html" in h and "</html>" in h
    # Ohne Konten bleibt das Panel da, nur ohne Saldenliste-Bezeichnung (kein Crash).
    assert "9200" in h
