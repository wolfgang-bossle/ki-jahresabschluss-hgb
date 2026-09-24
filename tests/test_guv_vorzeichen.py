"""
test_guv_vorzeichen.py
Das GuV-Vorzeichen kommt aus dem XBRL-balance-Attribut der amtlichen Taxonomie
(credit = Ertrag (+), debit = Aufwand (−)) — NICHT aus einer String-Heuristik (§2.8).
Diese Tests pinnen die Klassifikation über die ECHTEN Ertrags-/Aufwandskonzepte; die
Bäckerei-Demo hat nur Umsatzerlöse, sonst bliebe eine Regression bei sonstigen
Erträgen/Zinserträgen unbemerkt. Plus ein End-to-End-Beweis: ein Mandant mit
Zinserträgen rechnet korrekt und bilanziert — mit der früheren Heuristik wäre der
Zinsertrag als Aufwand gelaufen und die Bilanz gekippt.
"""
import json
from pathlib import Path

import openpyxl

from jahresabschluss import generate, is_revenue, load_balance

BASE = Path(__file__).resolve().parent.parent
TAXONOMIE = BASE / "taxonomy"
BALANCE = load_balance(TAXONOMIE / "de-gaap-ci-2025-04-01-balance-is.json")

IS = "de-gaap-ci_is.netIncome.regular"
ERTRAEGE = [
    IS + ".operatingTC.grossTradingProfit.totalOutput.netSales",      # Umsatzerlöse
    IS + ".fin.netInterest.income",                                   # Zinserträge
    IS + ".fin.netParticipation.earnings",                            # Beteiligungserträge
    IS + ".fin.netParticipation.earningSecurities",                   # Erträge a. Wertpapieren
    IS + ".operatingTC.grossTradingProfit.totalOutput.inventoryChange",  # Bestandserhöhung
    IS + ".operatingTC.grossTradingProfit.totalOutput.ownWork",       # akt. Eigenleistungen
]
AUFWENDUNGEN = [
    IS + ".operatingTC.staff.salaries",                               # Löhne/Gehälter
    IS + ".operatingTC.deprAmort.fixAss",                             # Abschreibungen
    IS + ".operatingTC.grossTradingProfit.materialServices.material", # Materialaufwand
    IS + ".fin.netInterest.expenses",                                 # Zinsaufwand
    "de-gaap-ci_is.netIncome.tax.kst",                                # Körperschaftsteuer
]


def test_ertraege_sind_credit():
    for c in ERTRAEGE:
        assert is_revenue(c, BALANCE) is True, f"sollte Ertrag (credit) sein: {c}"


def test_aufwendungen_sind_debit():
    for c in AUFWENDUNGEN:
        assert is_revenue(c, BALANCE) is False, f"sollte Aufwand (debit) sein: {c}"


def test_unbekanntes_konzept_wirft():
    # Kein Raten: fehlt das balance, ist das Vorzeichen nicht ableitbar -> Fehler.
    try:
        is_revenue("de-gaap-ci_is.konzept.gibts.nicht", BALANCE)
    except ValueError as e:
        assert "balance" in str(e).lower()
        return
    raise AssertionError("ValueError erwartet für Konzept ohne balance-Attribut.")


def _write_xlsx(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Konto", "Bezeichnung", "Saldo GJ", "Saldo VJ"])
    for r in rows:
        ws.append(list(r))
    wb.save(path)


def test_zinsertrag_end_to_end_balanciert(tmp_path):
    # Mandant mit Umsatz (30) UND Zinsertrag (20) -> beide Ertrag (+), JÜ = 50.
    # Aktiva Bank 150 = Passiva Stammkapital 100 + JÜ 50. (Alte Heuristik: Zinsertrag
    # als Aufwand -> JÜ 10 -> Passiva 110 != 150 -> Bilanz wäre gekippt.)
    mapping = tmp_path / "map.json"
    mapping.write_text(json.dumps({"mapping": {
        "1200": {"taxonomy_concept": "de-gaap-ci_bs.ass.currAss.cashEquiv.bank"},
        "0800": {"taxonomy_concept": "de-gaap-ci_bs.eqLiab.equity.subscribed"},
        "8400": {"taxonomy_concept": IS + ".operatingTC.grossTradingProfit.totalOutput.netSales"},
        "2650": {"taxonomy_concept": IS + ".fin.netInterest.income"},
    }}), encoding="utf-8")
    sl = tmp_path / "saldenliste.xlsx"
    _write_xlsx(sl, [
        ("1200", "Bank", 150.0, 0.0),
        ("0800", "Stammkapital", 100.0, 0.0),
        ("8400", "Umsatzerlöse", 30.0, 0.0),
        ("2650", "Zinserträge", 20.0, 0.0),
    ])
    dm = generate(sl, mapping, TAXONOMIE)
    assert dm["guv"]["jahresueberschuss_gj"] == 50.0          # 30 + 20, beide Ertrag
    assert dm["metadata"]["bilanzprobe_gj"] == 0.0            # bilanziert
    assert dm["bilanz"]["summe_aktiva_gj"] == 150.0
