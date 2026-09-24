"""
anhang_stempeln.py
Zweck: Persistiert den Phase-3-Validierungsstempel auf allen kanonischen
       Anhang-Section-JSONs eines Mandanten (output/<mandant>/anhang/*.json),
       damit der PDF-Renderer bei JEDER Section den Beleg "✓ geerdet · N Claims
       geprüft" zeigt — nicht nur bei einer. Holt Datenmodell + Sachverhalt frisch
       (eiserner Grundsatz), stempelt jede Datei einzeln, schreibt sie zurück.
       Exit 1, wenn eine Section fehlschlägt (phase3='fehler').
Aufruf: python scripts/anhang_stempeln.py
Status: ✅ 2026-07-03
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "mcp"))

from anhang import lade_sections, stempel_section  # noqa: E402
from jahresabschluss import generate               # noqa: E402
from sachverhalt import get_sachverhalt             # noqa: E402

DATA = BASE / "data/baeckerei_2025"
OUT = BASE / "output/baeckerei_2025"
SALDENLISTE = DATA / "Saldenliste.xlsx"
MAPPING = BASE / "mcp/config/skr03_mapping.json"
TAXONOMIE = BASE / "taxonomy"
ANLAGENBUCHHALTUNG = DATA / "Anlagenbuchhaltung.xlsx"
GEERDET_GEGEN = "Saldenliste.xlsx + sachverhaltsblatt.json"


def main() -> int:
    datenmodell = generate(SALDENLISTE, MAPPING, TAXONOMIE,
                           anlagenbuchhaltung=ANLAGENBUCHHALTUNG)
    sachverhalt = get_sachverhalt()
    sections = lade_sections()
    anhang_dir = OUT / "anhang"
    fehlgeschlagen = []

    for f in sorted(anhang_dir.glob("*.json")):
        section_obj = json.loads(f.read_text(encoding="utf-8"))
        gestempelt = stempel_section(
            section_obj, datenmodell, sachverhalt,
            geerdet_gegen=GEERDET_GEGEN, sections=sections)
        val = gestempelt["_validierung"]
        status = "✓" if val["phase3"] == "ok" else "✗"
        print(f"  {status} {f.name:40} {val['claims_geprueft']} Claims, "
              f"{val['fehler']} Fehler, {val['warnungen']} Warnungen")
        if val["phase3"] != "ok":
            fehlgeschlagen.append(f.name)
        f.write_text(json.dumps(gestempelt, ensure_ascii=False, indent=2), encoding="utf-8")

    if fehlgeschlagen:
        print(f"\n✗ FEHLGESCHLAGEN: {fehlgeschlagen}")
        return 1
    print(f"\n✓ Alle {len(list(anhang_dir.glob('*.json')))} Sections gestempelt.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
