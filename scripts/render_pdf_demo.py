"""
render_pdf_demo.py
Zweck: Showcase-/Bau-Skript — erzeugt aus der Muster-Bäckerei-Demo das PDF des
       Jahresabschlusses und schreibt es nach
       output/baeckerei_2025/jahresabschluss.pdf.
       Holt das Datenmodell frisch aus generate() (eiserner Grundsatz), reicht die
       Saldenliste-Konten für den Rückverfolgbarkeits-Anhang durch und bindet –
       falls vorhanden – die geerdeten Anhang-Sections sowie Firma/Stichtag/
       Geschäftsführer/Feststellungsdatum aus dem Sachverhaltsblatt (kosmetisch) ein.
Aufruf:  python scripts/render_pdf_demo.py
Status: ✅ 2026-06-23, Unterschrift/Feststellung 2026-07-03
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "mcp"))

from anhang import lade_sections                         # noqa: E402
from jahresabschluss import generate, read_saldenliste   # noqa: E402
from renderer_pdf import render_pdf                       # noqa: E402

DATA = BASE / "data/baeckerei_2025"
OUT = BASE / "output/baeckerei_2025"
SALDENLISTE = DATA / "Saldenliste.xlsx"
MAPPING = BASE / "mcp/config/skr03_mapping.json"
TAXONOMIE = BASE / "taxonomy"
ANLAGENBUCHHALTUNG = DATA / "Anlagenbuchhaltung.xlsx"


def _lade_anhang_sections():
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
    titel, stichtag, geschaeftsfuehrer, feststellung = "Jahresabschluss", None, None, None
    try:
        from sachverhalt import get_sachverhalt
        sv = get_sachverhalt()
        sd = sv.get("stammdaten", {})
        if sd.get("firma"):
            titel = f"Jahresabschluss {sd['firma']}"
        stichtag = sd.get("stichtag")
        gf_name = sv.get("organbezuege", {}).get("geschaeftsfuehrer_name")
        if gf_name:
            geschaeftsfuehrer = [gf_name]
        fst = sv.get("feststellung")
        if fst:
            feststellung = {"datum": fst.get("datum"), "ort": fst.get("ort")}
    except Exception:
        pass
    return titel, stichtag, geschaeftsfuehrer, feststellung


def main():
    dm = generate(SALDENLISTE, MAPPING, TAXONOMIE, anlagenbuchhaltung=ANLAGENBUCHHALTUNG)
    konten = read_saldenliste(SALDENLISTE)
    titel, stichtag, geschaeftsfuehrer, feststellung = _kopfangaben()
    sections_config = {s["id"]: s for s in lade_sections()}
    pdf = render_pdf(dm, konten=konten, anhang_sections=_lade_anhang_sections(),
                     titel=titel, stichtag=stichtag, anhang_sections_config=sections_config,
                     geschaeftsfuehrer=geschaeftsfuehrer, feststellung=feststellung)
    ziel = OUT / "jahresabschluss.pdf"
    ziel.write_bytes(pdf)
    print(f"OK: {ziel} ({len(pdf):,} Bytes)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
