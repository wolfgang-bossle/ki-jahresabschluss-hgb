"""
server.py
Zweck: MCP-Wrapper (FastMCP) um die Jahresabschluss-Engine. Dünne Hülle —
       KEINE Buchhaltungslogik hier. Ruft generate() aus jahresabschluss.py auf
       und reicht das Datenmodell durch. Bilanzprobe-Fehler propagieren als
       Tool-Fehler (Governance: melden, nie still ausgleichen).
Status: ✅ Produktiv 2026-06-27
Abhängigkeiten: fastmcp, jsonschema, jahresabschluss.py, anhang.py, sachverhalt.py,
                hgb_size_classes.py
Start: python mcp/server.py   (stdio-Transport)
Letzte Änderung: 2026-06-28 (Größenklassen-Gate §267: Tool groessenklasse_pruefen +
                 vorgeschaltet in jahresabschluss_erstellen)
"""
from functools import lru_cache
from pathlib import Path

from fastmcp import FastMCP

from anhang import baue_kontext, pruefe_section, validate_disclosure as _validate_disclosure
from hgb_size_classes import pruefe_groessenklasse
from jahresabschluss import generate
from sachverhalt import get_sachverhalt

# Repo-Wurzel = ein Ordner über mcp/ — damit der Server von überall startbar ist.
BASE = Path(__file__).resolve().parent.parent
# Demo-Mandant als überschreibbarer Default — KEINE Anpinnung: jeder Ordner unter
# data/ ist als Mandant wählbar (datenagnostisch §2.1). Die Muster-Bäckerei ist
# nur Komfort-Einstieg, gleichberechtigt mit Muster Consulting / Muster Stadtmarkt.
DEFAULT_MANDANT = "baeckerei_2025"
DEFAULT_MAPPING = BASE / "mcp/config/skr03_mapping.json"
DEFAULT_TAXONOMIE = BASE / "taxonomy"


def _mandant_dir(mandant: str) -> Path:
    return BASE / "data" / mandant


_DEFAULT_DIR = _mandant_dir(DEFAULT_MANDANT)
DEFAULT_SALDENLISTE = _DEFAULT_DIR / "Saldenliste.xlsx"
DEFAULT_ANLAGENBUCHHALTUNG = _DEFAULT_DIR / "Anlagenbuchhaltung.xlsx"

mcp = FastMCP("jahresabschluss-hgb")

_KONTEXT_SCHEMA = {
    "type": "object",
    "required": ["section_id", "label", "typ", "render", "normtext", "daten",
                 "aufgabe", "escalation_moeglich", "output_schema"],
    "properties": {
        "section_id":              {"type": "string"},
        "label":                   {"type": "string"},
        "typ":                     {"type": "string", "enum": ["A", "B", "C"]},
        "render":                  {"type": "string", "enum": ["prosa", "tabelle"]},
        "norm_refs":               {"type": "array", "items": {"type": "string"}},
        "normtext":                {"type": "array"},
        "aufgabe":                 {"type": "string"},
        "schutzklausel":           {},
        "daten":                   {"type": "object"},
        "escalation_moeglich":     {"type": "boolean"},
        "escalation_grund_vorgabe": {"type": ["string", "null"]},
        "output_schema":           {"type": "object"},
    },
}

_PRUEFERGEBNIS_SCHEMA = {
    "type": "object",
    "required": ["ok", "fehler", "warnungen"],
    "properties": {
        "ok":           {"type": "boolean"},
        "fehler":       {"type": "array", "items": {"type": "string"}},
        "warnungen":    {"type": "array", "items": {"type": "string"}},
        "geprueft": {
            "type": "object",
            "properties": {
                "claims": {"type": "integer"},
                "blocks": {"type": "integer"},
            },
        },
        "isError":       {"type": "boolean"},
        "errorCategory": {"type": "string"},
        "isRetryable":   {"type": "boolean"},
    },
}


@mcp.tool(title="Jahresabschluss erstellen (§ 266/§ 275 HGB)")
def jahresabschluss_erstellen(
    saldenliste: str = "",
    mapping: str = "",
    taxonomie: str = "",
    anlagenbuchhaltung: str = "",
) -> dict:
    """Erstellt aus einer Saldenliste den HGB-Jahresabschluss: Bilanz (§266 HGB)
    + GuV (§275 HGB) als vollständiges Datenmodell mit Rückverfolgbarkeit je
    Position (bis aufs Konto). Die Bilanzprobe wird hart geprüft — ist sie nicht
    0,00 €, schlägt der Aufruf fehl (Aktiva ≠ Passiva wird gemeldet, nie still
    korrigiert).

    Vorgeschaltetes Größenklassen-Gate (§ 267 Abs. 1/4 HGB): nach dem Aufbau wird
    geprüft, ob die Gesellschaft "klein" ist (Voraussetzung der größenabhängigen
    Erleichterungen). Ist sie es nicht, schlägt der Aufruf fehl (isError, validation)
    statt mit unzulässigen Erleichterungen weiterzulaufen.

    Ohne Argumente läuft die Muster-Bäckerei-Demo (SKR03). Alle Pfade lassen
    sich überschreiben, um andere Mandanten oder Kontenrahmen-Mappings zu fahren.

    Args:
        saldenliste: Pfad zur Saldenlisten-Excel (.xlsx, 4-Spalten-Format
            Konto/Bezeichnung/Saldo-GJ/Saldo-VJ). Leer = Demo.
        mapping: Pfad zur Tabelle-B-JSON (Konto → XBRL-Konzept). Leer = SKR03-Demo.
        taxonomie: Pfad zum Taxonomie-Ordner (de-gaap-ci Linkbasen). Leer = Demo.
        anlagenbuchhaltung: Pfad zur Anlagenbuchhaltungs-Excel (Brutto-Format) für
            den Anlagenspiegel (§284 Abs. 3 HGB). Leer = Bäckerei-Demo. Wird die
            Datei eingebunden, prüft die Engine hart gegen die Saldenliste
            (BW Ende = Anlagekonten, Σ AfA = AfA-Aufwandskonto); Abweichung = Fehler.

    Returns:
        Datenmodell mit Schlüsseln:
          - "bilanz":   aktiva/passiva (geordnete Positionslisten mit Quelle),
                        summe_aktiva_gj/vj, summe_passiva_gj/vj
          - "guv":      positionen (§275 GKV), jahresueberschuss_gj/vj
          - "anlagenspiegel": positionen (Brutto-Bewegungen), summe, hinweise,
                        reconciliation (nur wenn Anlagenbuchhaltung eingebunden)
          - "metadata": quelle, bilanzprobe_gj/vj (=0,00), jue_abgestimmt, taxonomie
        Bei Fehler: {"isError": true, "errorCategory": ..., "isRetryable": ..., "message": ...}
    """
    try:
        # Anlagenbuchhaltung-Default nur im reinen Demo-Modus (keine eigene Saldenliste)
        # und nur wenn sachverhaltsblatt.json → anlagenspiegel.erstellen = true.
        # Explizit übergebener Pfad überschreibt den Flag immer.
        sv = get_sachverhalt()
        anlagen_flag = sv.get("anlagenspiegel", {}).get("erstellen", False)
        _anlagen = anlagenbuchhaltung or (
            DEFAULT_ANLAGENBUCHHALTUNG if (not saldenliste and anlagen_flag) else None
        )
        modell = generate(
            saldenliste or DEFAULT_SALDENLISTE,
            mapping or DEFAULT_MAPPING,
            taxonomie or DEFAULT_TAXONOMIE,
            anlagenbuchhaltung=_anlagen,
        )
        # Größenklassen-Gate (§ 267): die Erleichterungen des Scopes (verkürzte Bilanz,
        # reduzierter Anhang, PDF-Offenlegung) setzen "klein" voraus. Nicht klein →
        # hart stoppen, nicht still mit unzulässigen Erleichterungen weiterlaufen.
        gk = pruefe_groessenklasse(modell, sv)
        if not gk["ok"]:
            return {"isError": True, "errorCategory": "validation",
                    "isRetryable": False, "message": gk["begruendung"],
                    "groessenklasse": gk}
        return modell
    except FileNotFoundError as e:
        return {"isError": True, "errorCategory": "not_found",
                "isRetryable": True, "message": str(e)}
    except ValueError as e:
        return {"isError": True, "errorCategory": "validation",
                "isRetryable": False, "message": str(e)}
    except Exception as e:
        return {"isError": True, "errorCategory": "internal",
                "isRetryable": False, "message": f"Unerwarteter Fehler: {e}"}


@lru_cache(maxsize=8)
def _live_datenmodell(mandant: str = DEFAULT_MANDANT) -> dict:
    """Datenmodell eines Mandanten aus data/<mandant>/ — In-Memory-Cache pro Mandant
    für die Prozess-Laufzeit. Jeder MCP-Server-Neustart (= neue Session) liest die
    Dateien frisch; zwischen Tool-Aufrufen innerhalb einer Session bleibt die Wahrheit
    stabil. Die Anlagenbuchhaltung wird nur eingebunden, wenn die Datei existiert UND
    sachverhaltsblatt.json → anlagenspiegel.erstellen = true (Mandanten ohne Anlage-
    vermögen liefern ein Modell ohne Anlagenspiegel-Block — Schema erlaubt das)."""
    d = _mandant_dir(mandant)
    sv = get_sachverhalt(d / "sachverhaltsblatt.json")
    anlagen_flag = sv.get("anlagenspiegel", {}).get("erstellen", False)
    ab = d / "Anlagenbuchhaltung.xlsx"
    return generate(
        d / "Saldenliste.xlsx",
        DEFAULT_MAPPING,
        DEFAULT_TAXONOMIE,
        anlagenbuchhaltung=ab if (anlagen_flag and ab.exists()) else None,
    )


@mcp.tool(title="Anhang-Kontext assemblieren (Phase 1)", output_schema=_KONTEXT_SCHEMA)
def anhang_section_kontext(section_id: str, mandant: str = DEFAULT_MANDANT) -> dict:
    """Anhang-Phase 1 (deterministisch): assembliert den vollständigen Kontext für
    einen Anhang-Abschnitt — HGB-Normtext, die relevanten Ausschnitte aus dem
    geerdeten Datenmodell und dem Sachverhaltsblatt, die Aufgabe und den
    Ausgabe-Vertrag (Schema). Generiert KEINEN Text; der Text entsteht erst in
    Phase 2 (LLM) und wird in Phase 3 (anhang_section_pruefen) geerdet.

    Args:
        section_id: ID aus mcp/config/anhang_sections.json
            (z. B. "anlagenspiegel", "organbezuege", "mitarbeiter").
        mandant: Ordner unter data/ (Standard: baeckerei_2025). Bestimmt Saldenliste
            und Sachverhaltsblatt der Erdung — jeder Demo-Mandant ist wählbar.

    Returns:
        Kontext-Objekt mit normtext, daten (nur sektionsrelevante Ausschnitte),
        aufgabe, norm_refs, schutzklausel, escalation-Vorgaben und output_schema.
    """
    sv = get_sachverhalt(_mandant_dir(mandant) / "sachverhaltsblatt.json")
    return baue_kontext(section_id, _live_datenmodell(mandant), sv)


@mcp.tool(title="Anhang-Section erden (Phase 3)", output_schema=_PRUEFERGEBNIS_SCHEMA)
def anhang_section_pruefen(section: dict, mandant: str = DEFAULT_MANDANT) -> dict:
    """Anhang-Phase 3 (deterministisch): erdet eine generierte Anhang-Section gegen
    die Wahrheit. Prüft jede Claim centgenau gegen ihren Quell-Pfad im Datenmodell
    bzw. Sachverhaltsblatt, verlangt Norm-Referenzen, erkennt unbelegte Zahlen in
    der Prosa (mögliche Halluzination) und erzwingt das Eskalations-Flag bei Typ C.

    Args:
        section: das von Phase 2 erzeugte Section-Objekt (Schema siehe
            output_schema aus anhang_section_kontext).
        mandant: Ordner unter data/ (Standard: baeckerei_2025). Muss derselbe sein,
            gegen den der Kontext assembliert wurde — sonst erdet die Prüfung gegen
            die falsche Wahrheit.

    Returns:
        {ok, fehler[], warnungen[], geprueft{claims, blocks}}. ok=False bedeutet:
        der Text behauptet etwas, das nicht aus der Wahrheit folgt — nicht abgeben.
        Wenn ok=False: zusätzlich isError=True, errorCategory="validation", isRetryable=True.
    """
    sv = get_sachverhalt(_mandant_dir(mandant) / "sachverhaltsblatt.json")
    result = pruefe_section(section, _live_datenmodell(mandant), sv)
    if not result.get("ok", True):
        result["isError"] = True
        result["errorCategory"] = "validation"
        result["isRetryable"] = True
    return result


@mcp.tool(title="Größenklasse prüfen (§ 267 Abs. 1 HGB)")
def groessenklasse_pruefen(mandant: str = DEFAULT_MANDANT) -> dict:
    """Vorgeschaltetes Gate: verifiziert, dass der Mandant eine KLEINE Kapitalgesellschaft
    nach § 267 Abs. 1 HGB ist — Voraussetzung für die größenabhängigen Erleichterungen
    (verkürzte Bilanz § 266 Abs. 1, reduzierter Anhang § 288 Abs. 1, PDF-Offenlegung
    § 326). Prüft die drei Merkmale (Bilanzsumme, Umsatzerlöse, Arbeitnehmer-Durchschnitt)
    für GJ und VJ und wendet die Zwei-Jahres-Regel (§ 267 Abs. 4) an.

    Die Größenklasse wird damit aus den Daten ABGELEITET (Bilanzsumme/Umsatz aus der
    Saldenliste, AN-Durchschnitt aus dem Sachverhaltsblatt) — nicht als String geglaubt.

    Args:
        mandant: Ordner unter data/ (Standard: baeckerei_2025).

    Returns:
        {ok, groessenklasse, schwellen_267_abs1, merkmale{gj,vj}, begruendung}.
        ok=True nur bei "klein". Bei "nicht klein": zusätzlich isError=True,
        errorCategory="validation", isRetryable=False — die Erstellung darf nicht
        mit Erleichterungen fortgesetzt werden (hart stoppen, melden).
    """
    try:
        sv = get_sachverhalt(_mandant_dir(mandant) / "sachverhaltsblatt.json")
        result = pruefe_groessenklasse(_live_datenmodell(mandant), sv)
        if not result.get("ok", False):
            result["isError"] = True
            result["errorCategory"] = "validation"
            result["isRetryable"] = False
        return result
    except FileNotFoundError as e:
        return {"isError": True, "errorCategory": "not_found",
                "isRetryable": True, "message": str(e)}
    except ValueError as e:
        return {"isError": True, "errorCategory": "validation",
                "isRetryable": False, "message": str(e)}


@mcp.tool(title="Vollständigkeit Pflicht-Anhang prüfen (§ 288 Abs. 1 HGB)")
def validate_disclosure(mandant: str = "baeckerei_2025",
                        groessenklasse: str = "klein") -> dict:
    """Prüft, ob alle Pflicht-Anhangangaben (§ 288 Abs. 1 HGB) als validierte
    Section-Dateien in output/<mandant>/anhang/ vorliegen. Vergleicht die aktiven
    Pflicht-Sections der Größenklasse gegen vorhandene JSON-Dateien.

    Args:
        mandant: Unterordner in output/ (Standard: baeckerei_2025).
        groessenklasse: "klein" | "mittelgross" | "gross" (Standard: "klein").

    Returns:
        {ok, groessenklasse, pflicht_sections, vorhanden, fehlend}.
        ok=True nur wenn fehlend leer (alle Pflicht-Sections vorhanden).
    """
    return _validate_disclosure(BASE / f"output/{mandant}/anhang", groessenklasse)


if __name__ == "__main__":
    mcp.run()
