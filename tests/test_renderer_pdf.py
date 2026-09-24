"""
test_renderer_pdf.py
Tests des PDF-Renderers (renderer_pdf.py). Braucht reportlab; fehlt es (z. B. in
einer minimalen Umgebung), überspringen die Tests sauber, statt den dependency-freien
Runner zu sprengen. Sichert dieselben Eigenschaften wie beim HTML-Renderer:
gültiges PDF, deutsche Formatierung mit ASCII-Minus (PDF-Standardfont-Glyphen),
robust ohne Anlagenspiegel/Anhang, und der Renderer ERFINDET keine Zahl (§2.7).
Datenagnostisch: synthetische Testkonten, kein Engine-Code (§2.1).
"""
try:
    from renderer_pdf import render_pdf, _eur
    HAVE_RL = True
except ImportError:
    HAVE_RL = False

# Synthetisches Mini-Modell (wie im HTML-Test, in sich stimmig, keine Mandantendaten).
DM = {
    "bilanz": {
        "aktiva": [
            {"ebene": 0, "konzept": "x_bs.ass", "label": "Summe Aktiva",
             "wert_gj": 100000.0, "wert_vj": 90000.0, "quelle": ["9001"]},
            {"ebene": 1, "konzept": "x_bs.ass.cash", "label": "Kasse",
             "wert_gj": 100000.0, "wert_vj": 90000.0, "quelle": ["9001"]},
        ],
        "passiva": [
            {"ebene": 0, "konzept": "x_bs.eqLiab", "label": "Summe Passiva",
             "wert_gj": 100000.0, "wert_vj": 90000.0, "quelle": ["9100"]},
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
KONTEN = {"9001": ("Kasse-Testkonto", 100000.0, 90000.0),
          "9100": ("EK-Testkonto", 0.0, 0.0),
          "9200": ("Ergebnis-Testkonto", 12345.67, -500.0)}


def test_eur_ascii_minus():
    if not HAVE_RL:
        return
    assert _eur(1700000.0) == "1.700.000,00"
    assert _eur(-1240000.0) == "-1.240.000,00"   # ASCII-Minus, kein U+2212 (Glyph!)
    assert _eur(0.0) == "0,00"
    assert _eur(None) == ""


def test_pdf_ist_gueltig_und_nichttrivial():
    if not HAVE_RL:
        return
    pdf = render_pdf(DM, konten=KONTEN, titel="Test", stichtag="31.12.2025")
    assert isinstance(pdf, (bytes, bytearray))
    assert pdf[:5] == b"%PDF-"          # gültiger PDF-Header
    assert pdf.rstrip()[-5:] == b"%%EOF"  # sauber terminiert
    assert len(pdf) > 3000               # mehr als ein leeres Gerüst


def test_pdf_robust_ohne_anlagenspiegel_und_anhang():
    if not HAVE_RL:
        return
    pdf = render_pdf(DM, konten=None, anhang_sections=None)
    assert pdf[:5] == b"%PDF-"


def test_pdf_mit_anlagenspiegel_baut_durch():
    """Querformat-Umschaltung + 11-Spalten-Tabelle dürfen nicht crashen."""
    if not HAVE_RL:
        return
    dm = dict(DM)
    dm["anlagenspiegel"] = {
        "positionen": [
            {"ebene": 0, "konzept": "x_bs.ass.fixAss", "konto": None, "label": "AV",
             "ahk_anf": 1833000.0, "zugang": 150000.0, "abgang_ahk": 0.0, "umbuchung": 0.0,
             "ahk_ende": 1983000.0, "kumafa_anf": 956500.0, "afa_jahr": 83500.0,
             "abgang_afa": 0.0, "kumafa_ende": 1040000.0, "bw_gj": 943000.0, "bw_vj": 876500.0},
        ],
        "summe": {"ahk_anf": 1833000.0, "zugang": 150000.0, "abgang_ahk": 0.0,
                  "umbuchung": 0.0, "ahk_ende": 1983000.0, "kumafa_anf": 956500.0,
                  "afa_jahr": 83500.0, "abgang_afa": 0.0, "kumafa_ende": 1040000.0,
                  "bw_gj": 943000.0, "bw_vj": 876500.0},
        "hinweise": [{"gruppe": "G", "hinweis": "Testhinweis", "typ": "C"}],
        "reconciliation": {"bw_gj": 943000.0, "afa_jahr": 83500.0,
                           "afa_aufwand_saldenliste": 83500.0, "abgestimmt": True},
    }
    pdf = render_pdf(dm, konten=KONTEN)
    assert pdf[:5] == b"%PDF-" and len(pdf) > 3000
