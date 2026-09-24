"""
hgb_size_classes.py
Zweck: Größenklassen-Gate (§ 267 Abs. 1 i. V. m. Abs. 4 HGB). Verifiziert aus dem
       geerdeten Datenmodell + Sachverhaltsblatt, dass die Gesellschaft "klein" ist —
       Voraussetzung für die größenabhängigen Erleichterungen (§ 288 Abs. 1, § 326).
       Die Größenklasse wird damit ABGELEITET, nicht (wie bisher) als String geglaubt.
Status: ✅ Produktiv 2026-06-28
Abhängigkeiten: Datenmodell aus jahresabschluss.generate(), sachverhaltsblatt.json
Datenagnostisch (§2.1): KEINE Kontonummern/Mandant. Schwellen = Gesetzeswerte (§267),
       Umsatz-Konzept = Taxonomie-Konstante (de-gaap-ci) — analog NETINCOME_CONCEPT.
Letzte Änderung: 2026-06-28
"""

# Schwellenwerte § 267 Abs. 1 HGB (Stand BEG IV 2024, Geschäftsjahre ab 31.12.2023).
# "klein" = höchstens EINS der drei Merkmale überschritten (= mind. zwei eingehalten).
BILANZSUMME_MAX = 7_500_000   # € nach Abzug Fehlbetrag § 268 Abs. 3
UMSATZERLOESE_MAX = 15_000_000  # € in den 12 Monaten vor dem Stichtag (§ 277 Abs. 1)
ARBEITNEHMER_MAX = 50           # Jahresdurchschnitt (§ 267 Abs. 5)

# Umsatzerlöse-Konzept der de-gaap-ci: das GuV-Blatt, dessen Konzept-ID auf
# ".netSales" endet (GKV wie UKV). Kein Pfad-Hardcoding → robust gegen das Verfahren.
NETSALES_SUFFIX = ".netSales"


def _umsatzerloese(datenmodell: dict) -> tuple[float, float]:
    """Umsatzerlöse (GJ, VJ) aus der GuV des Datenmodells. Fehlt das Konzept, ist die
    Größe nach § 267 nicht prüfbar → harter Fehler statt stiller 0-Annahme (§2.7)."""
    for p in datenmodell.get("guv", {}).get("positionen", []):
        if p.get("konzept", "").endswith(NETSALES_SUFFIX):
            return float(p["wert_gj"]), float(p["wert_vj"])
    raise ValueError(
        "Umsatzerlöse-Konzept (…" + NETSALES_SUFFIX + ") nicht in der GuV gefunden — "
        "Größenklasse nach § 267 HGB nicht prüfbar.")


def _arbeitnehmer(sachverhalt: dict) -> tuple[float, float]:
    """AN-Durchschnitt (GJ, VJ) aus dem Sachverhaltsblatt — kein Saldenlisten-Wert,
    daher Pflichtangabe im Sachverhaltsblatt (§ 267 Abs. 5). Fehlt sie → harter Fehler."""
    m = sachverhalt.get("mitarbeiter", {})
    if "durchschnitt_gj" not in m or "durchschnitt_vj" not in m:
        raise ValueError(
            "mitarbeiter.durchschnitt_gj/_vj fehlt im Sachverhaltsblatt — "
            "Arbeitnehmer-Merkmal (§ 267 Abs. 1 Nr. 3) nicht prüfbar.")
    return float(m["durchschnitt_gj"]), float(m["durchschnitt_vj"])


def _merkmale_jahr(bilanzsumme: float, umsatz: float, arbeitnehmer: float) -> dict:
    """Drei Merkmale eines Jahres gegen die Schwellen. klein = ≤ 1 überschritten."""
    ueber = []
    if bilanzsumme > BILANZSUMME_MAX:
        ueber.append("Bilanzsumme")
    if umsatz > UMSATZERLOESE_MAX:
        ueber.append("Umsatzerlöse")
    if arbeitnehmer > ARBEITNEHMER_MAX:
        ueber.append("Arbeitnehmer")
    return {
        "bilanzsumme": round(bilanzsumme, 2),
        "umsatzerloese": round(umsatz, 2),
        "arbeitnehmer": arbeitnehmer,
        "ueberschritten": ueber,
        "klein": len(ueber) <= 1,
    }


def pruefe_groessenklasse(datenmodell: dict, sachverhalt: dict) -> dict:
    """Verifiziert die Größenklasse "klein" (§ 267 Abs. 1) über GJ und VJ und wendet
    die Zwei-Jahres-Regel (§ 267 Abs. 4) an.

    Datenquellen (eiserner Grundsatz §2.7):
      - Bilanzsumme: datenmodell.bilanz.summe_aktiva_gj/_vj (aus Saldenliste abgeleitet)
      - Umsatzerlöse: GuV-Konzept …netSales (aus Saldenliste abgeleitet)
      - Arbeitnehmer: sachverhalt.mitarbeiter.durchschnitt_gj/_vj (Sachverhaltsblatt)

    § 267 Abs. 4: Die Rechtsfolge (Klassenwechsel) tritt erst ein, wenn die Grenzen an
    ZWEI aufeinanderfolgenden Stichtagen über-/unterschritten werden. Annahme im Scope:
    bisherige Einstufung = klein → "nicht mehr klein" nur, wenn GJ UND VJ die Grenzen
    reißen. Ein einzelnes Überschreitungsjahr (Wechseljahr) bleibt klein.
    (Neugründungs-Sonderfall nach Abs. 4 S. 2 ist nicht im Scope.)

    Returns: dict mit ok, groessenklasse, schwellen, merkmale{gj,vj}, begruendung.
    ok=False heißt: die Erleichterungen für kleine Gesellschaften sind unzulässig.
    """
    bs = datenmodell.get("bilanz", {})
    bs_gj = float(bs["summe_aktiva_gj"])
    bs_vj = float(bs["summe_aktiva_vj"])
    um_gj, um_vj = _umsatzerloese(datenmodell)
    an_gj, an_vj = _arbeitnehmer(sachverhalt)

    gj = _merkmale_jahr(bs_gj, um_gj, an_gj)
    vj = _merkmale_jahr(bs_vj, um_vj, an_vj)

    ist_klein = gj["klein"] or vj["klein"]  # Abs. 4: Wechsel braucht beide Jahre

    if ist_klein and gj["klein"] and vj["klein"]:
        begr = ("Klein nach § 267 Abs. 1 HGB: in GJ und VJ jeweils höchstens ein "
                "Merkmal überschritten — Erleichterungen (§ 288 Abs. 1, § 326) zulässig.")
    elif ist_klein:
        wechsel = "GJ" if not gj["klein"] else "VJ"
        begr = (f"Klein nach § 267 Abs. 1 HGB. Im {wechsel} sind die Grenzen erstmals "
                f"überschritten; nach § 267 Abs. 4 (Zwei-Jahres-Regel) tritt der "
                f"Klassenwechsel erst bei Überschreitung an zwei aufeinanderfolgenden "
                f"Stichtagen ein — Einstufung bleibt klein.")
    else:
        begr = ("NICHT klein: Größengrenzen des § 267 Abs. 1 HGB in GJ und VJ "
                "überschritten (§ 267 Abs. 4). Größenabhängige Erleichterungen "
                "(§ 288 Abs. 1, § 326) sind unzulässig — außerhalb des Scopes "
                "(kleine Kapitalgesellschaft).")

    return {
        "ok": ist_klein,
        "groessenklasse": "klein" if ist_klein else "nicht klein (mittelgroß/groß)",
        "schwellen_267_abs1": {
            "bilanzsumme": BILANZSUMME_MAX,
            "umsatzerloese": UMSATZERLOESE_MAX,
            "arbeitnehmer": ARBEITNEHMER_MAX,
        },
        "merkmale": {"gj": gj, "vj": vj},
        "begruendung": begr,
    }
