"""
render_html_demo.py
Zweck: Showcase-/Bau-Skript — erzeugt aus der Muster-Bäckerei-Demo das interaktive
       HTML des Jahresabschlusses und schreibt es nach
       output/baeckerei_2025/jahresabschluss.html.
       Holt das Datenmodell frisch aus generate() (eiserner Grundsatz: Wahrheit aus
       der Saldenliste), reicht die Saldenliste-Konten für das Drill-down durch und
       bindet – falls vorhanden – die geerdeten Anhang-Sections aus output/**/anhang/
       sowie Firma/Stichtag aus dem Sachverhaltsblatt (rein kosmetisch) ein.
Aufruf:  python scripts/render_html_demo.py
Status: ✅ 2026-06-23
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "mcp"))

from jahresabschluss import generate, read_saldenliste  # noqa: E402
from renderer_html import render_html                    # noqa: E402

DATA = BASE / "data/baeckerei_2025"
OUT = BASE / "output/baeckerei_2025"
SALDENLISTE = DATA / "Saldenliste.xlsx"
MAPPING = BASE / "mcp/config/skr03_mapping.json"
TAXONOMIE = BASE / "taxonomy"
ANLAGENBUCHHALTUNG = DATA / "Anlagenbuchhaltung.xlsx"


def _lade_anhang_sections():
    """Geerdete Phase-2-Sections aus output/**/anhang/ (ohne anhang_-Präfix)."""
    d = OUT / "anhang"
    if not d.is_dir():
        return []
    sections = []
    for f in sorted(d.glob("*.json")):
        try:
            sections.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return sections


def _kopfangaben():
    """Firma + Stichtag fürs Kopf-Layout (kosmetisch, aus dem Sachverhaltsblatt)."""
    titel, stichtag = "Jahresabschluss", None
    try:
        from sachverhalt import get_sachverhalt
        sv = get_sachverhalt()
        sd = sv.get("stammdaten", {})
        if sd.get("firma"):
            titel = f"Jahresabschluss {sd['firma']}"
        stichtag = sd.get("stichtag")
    except Exception:
        pass
    return titel, stichtag


def main():
    dm = generate(SALDENLISTE, MAPPING, TAXONOMIE, anlagenbuchhaltung=ANLAGENBUCHHALTUNG)
    konten = read_saldenliste(SALDENLISTE)
    titel, stichtag = _kopfangaben()
    htmltext = render_html(
        dm, konten=konten, anhang_sections=_lade_anhang_sections(),
        titel=titel, stichtag=stichtag,
    )
    ziel = OUT / "jahresabschluss.html"
    ziel.write_text(htmltext, encoding="utf-8")
    print(f"OK: {ziel} ({len(htmltext):,} Zeichen)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
