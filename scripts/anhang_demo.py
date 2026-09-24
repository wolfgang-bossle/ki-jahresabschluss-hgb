"""
anhang_demo.py
Zweck: End-to-End-Nachweis des Anhang-Schritts ohne Live-LLM. Fährt Phase 1
       (Kontext-Assembly) für alle Sections und Phase 3 (Grounding-Validator)
       gegen das echte Datenmodell. Beweist: grün bei Wahrheit, ROT bei
       manipulierter Zahl (eiserner Grundsatz §2.5/§2.7).
       Zugleich der TEST des Anhang-Moduls (Exit 1 bei unerwartetem Ergebnis).
Aufruf: python scripts/anhang_demo.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "mcp"))

from anhang import (  # noqa: E402
    baue_anlagenspiegel_tabelle,
    baue_kontext,
    lade_sections,
    pruefe_section,
    validate_disclosure,
)
from sachverhalt import get_sachverhalt  # noqa: E402

DATENMODELL = BASE / "output/baeckerei_2025/jahresabschluss_datenmodell.json"
ART_DIR = BASE / "output/baeckerei_2025"


def hr(t):
    print("\n" + "=" * 70 + f"\n{t}\n" + "=" * 70)


def main() -> int:
    datenmodell = json.loads(DATENMODELL.read_text(encoding="utf-8"))
    sachverhalt = get_sachverhalt()
    sections = lade_sections()
    fehlgeschlagen = []

    # ---- Phase 1: Kontext für alle 7 Sections ---------------------------- #
    hr("PHASE 1 — Kontext-Assembly (alle Sections)")
    for s in sections:
        k = baue_kontext(s["id"], datenmodell, sachverhalt, sections)
        nt_ok = all(n["text"] for n in k["normtext"])
        daten_ok = any(v is not None for v in k["daten"].values()) if k["daten"] else True
        print(f"  [{k['typ']}] {s['id']:32} norm={k['norm_refs']} "
              f"normtext={'✓' if nt_ok else '✗'} daten={'✓' if daten_ok else '∅'}")
        if not nt_ok:
            fehlgeschlagen.append(f"{s['id']}: Normtext nicht gefunden")
        if not daten_ok:
            fehlgeschlagen.append(f"{s['id']}: keine Daten assembliert")

    # ---- Phase 3a: Anlagenspiegel deterministisch → muss GRÜN sein ------- #
    hr("PHASE 3a — Anlagenspiegel (Typ A, deterministisch) → erwartet GRÜN")
    asp_section = baue_anlagenspiegel_tabelle(datenmodell)
    res = pruefe_section(asp_section, datenmodell, sachverhalt, sections)
    print(f"  ok={res['ok']}  geprüfte Claims={res['geprueft']['claims']}  "
          f"Fehler={len(res['fehler'])}  Warnungen={len(res['warnungen'])}")
    if not res["ok"]:
        fehlgeschlagen.append("Anlagenspiegel-Validierung unerwartet ROT")
        for f in res["fehler"]:
            print("   FEHLER:", f)
    (ART_DIR / "anhang_anlagenspiegel.json").write_text(
        json.dumps(asp_section, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- Phase 3b: Manipulierte Zahl → muss ROT sein -------------------- #
    hr("PHASE 3b — manipulierte Zahl → erwartet ROT (Validator muss greifen)")
    boese = json.loads(json.dumps(asp_section))
    boese["blocks"][0]["claims"][0]["wert"] = 999999.0  # gefälschter Buchwert
    res_boese = pruefe_section(boese, datenmodell, sachverhalt, sections)
    if res_boese["ok"]:
        fehlgeschlagen.append("Validator hat manipulierte Zahl NICHT erkannt!")
        print("  ✗✗ Validator ließ Fälschung durch — schwerer Defekt.")
    else:
        print(f"  ok={res_boese['ok']} → korrekt erkannt. Erster Fehler:")
        print("   ", res_boese["fehler"][0])

    # ---- Phase 3c: Prosa-Fixture organbezüge (Schutzklausel §286(4)) ----- #
    hr("PHASE 3c — Organbezüge (Schutzklausel §286 Abs. 4) → erwartet GRÜN")
    organ = {
        "section_id": "organbezuege",
        "norm_refs": ["§ 285 Nr. 9a HGB", "§ 286 Abs. 4 HGB"],
        "blocks": [{
            "typ": "prosa",
            "text": ("Auf die Angabe der Gesamtbezüge der Geschäftsführung wird gemäß "
                     "§ 286 Abs. 4 HGB verzichtet, da die Gesellschaft einen einzigen "
                     "Geschäftsführer hat und die Angabe Rückschlüsse auf dessen Bezüge zuließe."),
            "claims": [{
                "aussage": "Anzahl Geschäftsführer",
                "wert": 1,
                "quelle": {"art": "sachverhalt", "pfad": "organbezuege.geschaeftsfuehrer_anzahl"},
            }],
        }],
        "confidence": "hoch",
        "escalation_flag": False,
        "escalation_grund": None,
        "offene_punkte": [],
    }
    res_o = pruefe_section(organ, datenmodell, sachverhalt, sections)
    print(f"  ok={res_o['ok']}  Fehler={len(res_o['fehler'])}  Warnungen={len(res_o['warnungen'])}")
    for w in res_o["warnungen"]:
        print("   WARN:", w)
    if not res_o["ok"]:
        fehlgeschlagen.append("Organbezüge-Fixture unerwartet ROT")
        for f in res_o["fehler"]:
            print("   FEHLER:", f)
    (ART_DIR / "anhang_organbezuege.json").write_text(
        json.dumps(organ, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- Phase 3d: Geisterzahl in Prosa → erwartet WARNUNG -------------- #
    hr("PHASE 3d — unbelegte Zahl in Prosa → erwartet WARNUNG")
    geist = {
        "section_id": "mitarbeiter",
        "norm_refs": ["§ 285 Nr. 7 HGB"],
        "blocks": [{
            "typ": "prosa",
            "text": "Im Geschäftsjahr waren durchschnittlich 38 Arbeitnehmer und 12 Aushilfen beschäftigt.",
            "claims": [{
                "aussage": "durchschnittliche Arbeitnehmer GJ",
                "wert": 38,
                "quelle": {"art": "sachverhalt", "pfad": "mitarbeiter.durchschnitt_gj"},
            }],
        }],
        "confidence": "hoch", "escalation_flag": False, "escalation_grund": None, "offene_punkte": [],
    }
    res_g = pruefe_section(geist, datenmodell, sachverhalt, sections)
    geist_warn = any("12" in w for w in res_g["warnungen"])
    print(f"  ok={res_g['ok']}  Warnungen={len(res_g['warnungen'])}")
    for w in res_g["warnungen"]:
        print("   WARN:", w)
    if not geist_warn:
        fehlgeschlagen.append("Geisterzahl 12 wurde nicht als Warnung erkannt")

    # ---- Phase 4: Vollständigkeits-Check §288 Abs. 1 ---------------------- #
    hr("PHASE 4 — validate_disclosure() — Vollständigkeit Pflicht-Anhang (klein)")
    vd = validate_disclosure(ART_DIR / "anhang", "klein")
    print(f"  ok={vd['ok']}  Pflicht-Sections: {vd['pflicht_sections']}")
    print(f"  Vorhanden: {vd['vorhanden']}")
    print(f"  Fehlend:   {vd['fehlend']}")

    # ---- Fazit ---------------------------------------------------------- #
    hr("FAZIT")
    if fehlgeschlagen:
        print("✗ FEHLGESCHLAGEN:")
        for f in fehlgeschlagen:
            print("   -", f)
        return 1
    print("✓ Alle Erwartungen erfüllt: Phase 1 assembliert, Validator erdet centgenau,")
    print("  Fälschung erkannt, Schutzklausel grün, Geisterzahl gewarnt.")
    print(f"  Phase-2-Status: {len(vd['vorhanden'])}/{len(vd['pflicht_sections'])} "
          f"Pflicht-Sections vorhanden, fehlend: {vd['fehlend']}")
    print(f"  Artefakte: {ART_DIR/'anhang_anlagenspiegel.json'}")
    print(f"             {ART_DIR/'anhang_organbezuege.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
