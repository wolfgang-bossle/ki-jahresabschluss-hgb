"""
anhang.py
Zweck: Anhang-Generierung — Phase 1 (Kontext-Assembly) + Phase 3 (Grounding-Validator)
       + Validierungs-Stempel (persistiert das Phase-3-Ergebnis auf der Section-JSON
       für den PDF-Beleg). Deterministisch, datenagnostisch, KEINE Buchhaltungslogik,
       KEINE Kontonummern im Code. Phase 2 (LLM-Formulierung) läuft außerhalb
       (LLM-Seam §2.3, Desktop-now/API-ready).
Status: ✅ Produktiv 2026-06-27, Stempel-Funktion 2026-07-03
Bezug: docs/ANHANG.md — die KI formuliert nur, sie behauptet nichts, was nicht aus
       dem Datenmodell (Wahrheit) oder dem Sachverhaltsblatt stammt (eiserner Grundsatz §2.5/§2.7).
"""
from __future__ import annotations

import json
import jsonschema
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SECTIONS_CONFIG = BASE / "mcp/config/anhang_sections.json"
CHUNKS = BASE / "rag/chunks.json"
_SCHEMA_PATH = BASE / "mcp/config/section_output.schema.json"

# Vertrag für die LLM-Ausgabe (Phase 2). Wird im Kontext mitgegeben und in Phase 3
# hart nachgeprüft: erst Strukturvalidierung (jsonschema), dann Grounding. ⟦D4⟧
with open(_SCHEMA_PATH, encoding="utf-8") as _f:
    SECTION_OUTPUT_SCHEMA: dict = json.load(_f)


# --------------------------------------------------------------------------- #
# Normtext (get_norm_text) — aus rag/chunks.json, mit Fallback                 #
# --------------------------------------------------------------------------- #
def lade_chunks(path: str | Path = CHUNKS) -> list[dict]:
    with open(Path(path), encoding="utf-8") as f:
        return json.load(f)


def get_norm_text(paragraph, absatz=None, nummer=None, buchstabe=None, chunks=None) -> dict | None:
    """Liefert den passendsten Normtext-Chunk. Exakte Übereinstimmung zuerst,
    danach Fallback auf (Paragraf+Absatz), dann (Paragraf). None, wenn nichts passt."""
    if chunks is None:
        chunks = lade_chunks()
    para = str(paragraph)

    def passt(c, exakt):
        if c["paragraph"] != para:
            return False
        if exakt:
            return (
                (absatz is None or c.get("absatz") == absatz)
                and (nummer is None or c.get("nummer") == nummer)
                and (buchstabe is None or c.get("buchstabe") == buchstabe)
            )
        return c.get("absatz") == absatz if absatz is not None else True

    for c in chunks:
        if passt(c, exakt=True):
            return c
    for c in chunks:
        if passt(c, exakt=False):
            return c
    for c in chunks:
        if c["paragraph"] == para:
            return c
    return None


# --------------------------------------------------------------------------- #
# Sections                                                                     #
# --------------------------------------------------------------------------- #
def lade_sections(path: str | Path = SECTIONS_CONFIG) -> list[dict]:
    with open(Path(path), encoding="utf-8") as f:
        return json.load(f)


def finde_section(section_id: str, sections=None) -> dict:
    if sections is None:
        sections = lade_sections()
    for s in sections:
        if s["id"] == section_id:
            return s
    raise ValueError(f"Section '{section_id}' nicht in anhang_sections.json gefunden.")


# Größenklassen-Filter (§288 Abs. 1): die Section-Definitionen bleiben vollständig
# erhalten — welche davon in den Anhang einer konkreten Größenklasse gehören, ist
# DATEN (Feld 'geltung'), nicht Code. Bei 'klein' fällt z.B. der Anlagenspiegel
# (freiwillig) und entfallene Pflichten heraus; bei 'gross' lässt derselbe Filter
# sie wieder durch — null Code-Änderung, nur Input wechselt (§2.4).
GELTUNG_WERTE = ("pflicht", "freiwillig", "entfaellt")


def aktive_sections(groessenklasse: str, einschluss=("pflicht",), sections=None) -> list[dict]:
    """Liefert die für eine Größenklasse anwendbaren Sections (Reihenfolge erhalten).
    'einschluss' steuert, welche Geltungs-Stufen aufgenommen werden — Default nur
    'pflicht'; ('pflicht', 'freiwillig') nimmt z.B. den Anlagenspiegel bewusst dazu."""
    if sections is None:
        sections = lade_sections()
    unbekannt = set(einschluss) - set(GELTUNG_WERTE)
    if unbekannt:
        raise ValueError(f"Unbekannte Geltungs-Stufe(n): {sorted(unbekannt)}; erlaubt: {GELTUNG_WERTE}")
    out = []
    for s in sections:
        geltung = s.get("geltung", {})
        if groessenklasse not in geltung:
            raise ValueError(
                f"Section '{s['id']}' hat keine Geltung für Größenklasse '{groessenklasse}'."
            )
        if geltung[groessenklasse] in einschluss:
            out.append(s)
    return out


# --------------------------------------------------------------------------- #
# Pfad-Resolver — adressiert Werte im Datenmodell / Sachverhaltsblatt          #
#   "anlagenspiegel.summe.bw_gj"                                               #
#   "anlagenspiegel.positionen[konto=0440].bw_gj"  (Filter rein DATEN-seitig)  #
#   "bilanz.aktiva[0].wert_gj"                                                  #
# --------------------------------------------------------------------------- #
_TEIL = re.compile(r"([^.\[\]]+)|\[([^\]]+)\]")


class PfadFehler(KeyError):
    pass


def wert_aus_pfad(root, pfad: str):
    cur = root
    for name, klammer in _TEIL.findall(pfad):
        if name:
            if not isinstance(cur, dict) or name not in cur:
                raise PfadFehler(pfad)
            cur = cur[name]
        elif klammer:
            if "=" in klammer:  # Listen-Filter [feld=wert]
                feld, _, soll = klammer.partition("=")
                if not isinstance(cur, list):
                    raise PfadFehler(pfad)
                treffer = [e for e in cur if str(e.get(feld)) == soll]
                if not treffer:
                    raise PfadFehler(pfad)
                cur = treffer[0]
            else:  # Index [n]
                try:
                    cur = cur[int(klammer)]
                except (ValueError, IndexError, TypeError):
                    raise PfadFehler(pfad)
    return cur


# --------------------------------------------------------------------------- #
# PHASE 1 — Kontext-Assembly (deterministisch, keine Generierung)             #
# --------------------------------------------------------------------------- #
def baue_kontext(section_id: str, datenmodell: dict, sachverhalt: dict,
                 sections=None, chunks=None) -> dict:
    """Assembliert den vollständigen Kontext für eine Anhang-Section: Normtext +
    relevante Datenmodell-/Sachverhalts-Ausschnitte + Aufgabe + Ausgabe-Vertrag.
    Gibt NIE Text zurück — nur Kontext für Phase 2 (LLM-Seam)."""
    s = finde_section(section_id, sections)

    norm_texte = []
    for ref in s["norm"]["refs"]:
        c = get_norm_text(ref.get("paragraph"), ref.get("absatz"),
                          ref.get("nummer"), ref.get("buchstabe"), chunks)
        norm_texte.append({
            "zitat": ref.get("zitat"),
            "titel": c["titel"] if c else None,
            "text": c["text"] if c else None,
        })

    daten = {}
    for pfad in s["quellen"].get("datenmodell", []):
        try:
            daten[pfad] = wert_aus_pfad(datenmodell, pfad)
        except PfadFehler:
            daten[pfad] = None
    for pfad in s["quellen"].get("sachverhalt", []):
        try:
            daten["sachverhalt." + pfad] = wert_aus_pfad(sachverhalt, pfad)
        except PfadFehler:
            daten["sachverhalt." + pfad] = None

    return {
        "section_id": section_id,
        "label": s["label"],
        "typ": s["typ"],
        "render": s["render"],
        "norm_refs": [r.get("zitat") for r in s["norm"]["refs"]],
        "normtext": norm_texte,
        "aufgabe": s["aufgabe"],
        "schutzklausel": s.get("schutzklausel"),
        "daten": daten,
        "escalation_moeglich": s["escalation"]["moeglich"],
        "escalation_grund_vorgabe": s["escalation"]["grund"],
        "output_schema": SECTION_OUTPUT_SCHEMA,
    }


# --------------------------------------------------------------------------- #
# PHASE 3 — Grounding-Validator (deterministisch) — DER TEST                  #
# --------------------------------------------------------------------------- #
_ZAHL = re.compile(r"-?\d{1,3}(?:\.\d{3})+(?:,\d+)?|-?\d+(?:,\d+)?")

# Gesetzeszitate enthalten Zahlen, die KEINE Tatsachenbehauptungen sind
# (§ 286 Abs. 4 Nr. 9a HGB …). Vor dem Geisterzahl-Scan herausfiltern.
_ZITAT = re.compile(r"§\s*\d+\s*[a-z]?|Abs\.\s*\d+\s*[a-z]?|Nr\.\s*\d+\s*[a-z]?|Satz\s*\d+|Buchst\.\s*[a-z]")


def _strip_zitate(text: str) -> str:
    return _ZITAT.sub(" ", text or "")


def _parse_de_zahl(token: str):
    t = token.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _zahlen_im_text(text: str) -> list[float]:
    out = []
    for m in _ZAHL.findall(text or ""):
        v = _parse_de_zahl(m)
        if v is not None:
            out.append(v)
    return out


def _gleich(a, b, toleranz=0.005) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= toleranz
    return str(a).strip() == str(b).strip()


def pruefe_section(section_obj: dict, datenmodell: dict, sachverhalt: dict,
                   sections=None, chunks=None) -> dict:
    """Erdet die generierte Section gegen die Wahrheit. Prüft: jede Claim gegen
    ihren Quell-Pfad (centgenau), Norm-Referenzen vorhanden/existent, keine
    unbelegten Zahlen in Prosa. Gibt strukturiertes Prüfergebnis zurück."""
    fehler: list[str] = []
    warnungen: list[str] = []
    n_claims = 0

    # (0) Strukturvalidierung — schlägt frühzeitig an, bevor Grounding läuft
    try:
        jsonschema.validate(instance=section_obj, schema=SECTION_OUTPUT_SCHEMA)
    except jsonschema.ValidationError as e:
        return {
            "ok": False,
            "fehler": [f"Strukturfehler: {e.message} (Pfad: {'/'.join(str(p) for p in e.absolute_path)})"],
            "warnungen": [],
            "geprueft": {},
        }

    sid = section_obj.get("section_id")
    try:
        s = finde_section(sid, sections)
    except ValueError as e:
        return {"ok": False, "fehler": [str(e)], "warnungen": [], "geprueft": {}}

    if chunks is None:
        chunks = lade_chunks()

    # (1) Norm-Referenzen
    refs = section_obj.get("norm_refs") or []
    if not refs:
        fehler.append("norm_refs leer — jede Anhang-Section braucht mind. eine Norm-Referenz.")
    erlaubte = {r.get("zitat") for r in s["norm"]["refs"]}
    for r in refs:
        if r not in erlaubte:
            warnungen.append(f"norm_ref '{r}' steht nicht in der Section-Definition {sorted(erlaubte)}.")

    wurzeln = {"datenmodell": datenmodell, "sachverhalt": sachverhalt}

    # (2) Claim-Grounding + (3) Geisterzahlen
    for bi, block in enumerate(section_obj.get("blocks", [])):
        claims = block.get("claims", []) or []
        belegte = []
        for ci, claim in enumerate(claims):
            n_claims += 1
            q = claim.get("quelle", {}) or {}
            art, pfad = q.get("art"), q.get("pfad")
            wert = claim.get("wert")
            belegte.append(wert)
            if art not in wurzeln:
                fehler.append(f"block[{bi}].claim[{ci}]: quelle.art '{art}' unbekannt.")
                continue
            try:
                soll = wert_aus_pfad(wurzeln[art], pfad)
            except PfadFehler:
                fehler.append(f"block[{bi}].claim[{ci}]: Quell-Pfad '{pfad}' existiert nicht in {art}.")
                continue
            if not _gleich(wert, soll):
                fehler.append(
                    f"block[{bi}].claim[{ci}]: behauptet {wert!r}, "
                    f"aber {art}.{pfad} = {soll!r}. (eiserner Grundsatz verletzt)"
                )

        # Geisterzahlen: Zahl in Prosa, die keine Claim belegt
        if block.get("typ") == "prosa":
            # Belegt sind numerische Claim-Werte UND Zahlen, die in einem
            # string-wertigen Claim stecken (z. B. "HRB 12345", "31.12.2025",
            # Geschäftsjahr "2025") — sonst Fehlalarm bei Stammdaten-Prosa.
            belegte_zahlen = []
            for b in belegte:
                if isinstance(b, (int, float)):
                    belegte_zahlen.append(b)
                elif isinstance(b, str):
                    belegte_zahlen.extend(_zahlen_im_text(b))
            for z in _zahlen_im_text(_strip_zitate(block.get("text", ""))):
                if not any(_gleich(z, b) for b in belegte_zahlen):
                    warnungen.append(
                        f"block[{bi}]: Zahl {z:g} im Text ist durch keine Claim belegt (mögliche Halluzination)."
                    )

    # (4) Eskalation: Typ C muss geflaggt sein
    if s["typ"] == "C" and not section_obj.get("escalation_flag"):
        fehler.append("Section ist Typ C, aber escalation_flag ist nicht gesetzt (Mensch-Entscheid erforderlich).")

    return {
        "ok": not fehler,
        "fehler": fehler,
        "warnungen": warnungen,
        "geprueft": {"claims": n_claims, "blocks": len(section_obj.get("blocks", []))},
    }


# --------------------------------------------------------------------------- #
# Validierungs-Stempel — Phase-3-Ergebnis auf der Section persistieren        #
#   pruefe_section() prüft nur, hält aber nichts fest — für den PDF-Beleg     #
#   ("✓ geerdet · N Claims geprüft") braucht die Section-JSON das Ergebnis    #
#   selbst. '_validierung' ist kein LLM-Ausgabefeld (schema additionalProp-   #
#   erties=false), daher: vor dem Prüfen abstreifen, danach neu anhängen.     #
# --------------------------------------------------------------------------- #
def stempel_section(section_obj: dict, datenmodell: dict, sachverhalt: dict,
                    geerdet_gegen: str = "Datenmodell + Sachverhaltsblatt",
                    datum: str | None = None, sections=None, chunks=None) -> dict:
    """Führt pruefe_section() auf der schema-reinen Section aus und gibt eine neue
    Section mit angehängtem Prüfergebnis ('_validierung') zurück. ok=False läuft
    NICHT in eine Exception — 'phase3': 'fehler' landet im Stempel, damit ein
    tatsächlich fehlgeschlagener Check sichtbar bleibt statt verschwiegen zu werden."""
    from datetime import date
    sauber = {k: v for k, v in section_obj.items() if k != "_validierung"}
    ergebnis = pruefe_section(sauber, datenmodell, sachverhalt, sections, chunks)
    return {
        **sauber,
        "_validierung": {
            "phase3": "ok" if ergebnis["ok"] else "fehler",
            "claims_geprueft": ergebnis["geprueft"].get("claims", 0),
            "fehler": len(ergebnis["fehler"]),
            "warnungen": len(ergebnis["warnungen"]),
            "geerdet_gegen": geerdet_gegen,
            "datum": datum or date.today().isoformat(),
        },
    }


# --------------------------------------------------------------------------- #
# Typ-A-Helfer: Anlagenspiegel-Tabelle deterministisch bauen                   #
#   Typ A ist so strukturiert, dass kein LLM nötig ist — wahr per Konstruktion. #
# --------------------------------------------------------------------------- #
_SPALTEN = [
    ("ahk_anf", "AHK Anfang"), ("zugang", "Zugänge"), ("abgang_ahk", "Abgänge"),
    ("umbuchung", "Umbuchungen"), ("ahk_ende", "AHK Ende"),
    ("kumafa_anf", "Kum. AfA Anfang"), ("afa_jahr", "AfA des GJ"),
    ("abgang_afa", "Abgänge AfA"), ("kumafa_ende", "Kum. AfA Ende"),
    ("bw_gj", "Buchwert Ende"), ("bw_vj", "Buchwert Vorjahr"),
]


def baue_anlagenspiegel_tabelle(datenmodell: dict) -> dict:
    """Baut das Section-Objekt für den Anlagenspiegel direkt aus dem Datenmodell —
    jede Zelle mit Claim auf ihren Datenmodell-Pfad. Wahr per Konstruktion."""
    asp = datenmodell["anlagenspiegel"]
    positionen = asp["positionen"]
    spalten = ["Posten"] + [titel for _, titel in _SPALTEN]
    zeilen, claims = [], []

    for i, pos in enumerate(positionen):
        zeile = [pos.get("label")]
        for feld, _ in _SPALTEN:
            wert = pos.get(feld)
            zeile.append(wert)
            if isinstance(wert, (int, float)):
                claims.append({
                    "aussage": f"{pos.get('label')} — {feld}",
                    "wert": wert,
                    "quelle": {"art": "datenmodell", "pfad": f"anlagenspiegel.positionen[{i}].{feld}"},
                })
        zeilen.append(zeile)

    summe = ["Summe Anlagevermögen"]
    for feld, _ in _SPALTEN:
        wert = asp["summe"].get(feld)
        summe.append(wert)
        if isinstance(wert, (int, float)):
            claims.append({
                "aussage": f"Summe — {feld}",
                "wert": wert,
                "quelle": {"art": "datenmodell", "pfad": f"anlagenspiegel.summe.{feld}"},
            })
    zeilen.append(summe)

    return {
        "section_id": "anlagenspiegel",
        "norm_refs": ["§ 284 Abs. 3 HGB"],
        "blocks": [{"typ": "tabelle", "spalten": spalten, "zeilen": zeilen, "claims": claims}],
        "confidence": "hoch",
        "escalation_flag": False,
        "escalation_grund": None,
        "offene_punkte": [],
    }


# --------------------------------------------------------------------------- #
# Vollständigkeits-Check — §288 Abs. 1 Gating                                 #
# --------------------------------------------------------------------------- #
def validate_disclosure(output_dir: str | Path, groessenklasse: str = "klein",
                        sections=None) -> dict:
    """Prüft die Vollständigkeit des Pflicht-Anhangs für eine Größenklasse.
    Vergleicht aktive Pflicht-Sections gegen JSON-Dateien in output_dir.

    Eine Datei erfüllt das §288-Gate nur, wenn sie ein nicht-leeres Section-Objekt
    mit passender section_id ist — ein leeres {} oder Fremd-JSON zählt NICHT (sonst
    ließe sich die Vollständigkeit mit Platzhaltern austricksen). Die inhaltliche
    Erdung jeder Claim prüft separat pruefe_section (Existenz-Gate ≠ Inhalts-Gate).

    Gibt erfüllte Sections in 'vorhanden', defekte/leere in 'ungueltig', ganz fehlende
    in 'fehlend' zurück; ok=True nur wenn 'ungueltig' UND 'fehlend' leer sind."""
    pflicht = aktive_sections(groessenklasse, einschluss=("pflicht",), sections=sections)
    pflicht_ids = [s["id"] for s in pflicht]
    out = Path(output_dir)
    vorhanden, ungueltig, fehlend = [], [], []
    for sid in pflicht_ids:
        p = out / f"{sid}.json"
        if not p.exists():
            fehlend.append(sid)
            continue
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            ungueltig.append(sid)
            continue
        if isinstance(obj, dict) and obj and obj.get("section_id") == sid:
            vorhanden.append(sid)
        else:
            ungueltig.append(sid)
    return {
        "ok": not fehlend and not ungueltig,
        "groessenklasse": groessenklasse,
        "pflicht_sections": pflicht_ids,
        "vorhanden": vorhanden,
        "ungueltig": ungueltig,
        "fehlend": fehlend,
    }
