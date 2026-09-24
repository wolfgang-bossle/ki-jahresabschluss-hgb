"""
sachverhalt.py
Zweck: get_sachverhalt() — lädt den Case-Facts-Block (Sachverhaltsblatt) und
       validiert ihn gegen ein Minimal-Schema. Deterministisch, datenagnostisch.
       Enthält NUR Sachverhalte, die nicht in der Saldenliste stehen (Stammdaten,
       Mitarbeiter, Organbezüge, Nachtragsereignisse) — numerische Wahrheiten
       bleiben beim eisernen Grundsatz §2.7 (Saldenliste → Datenmodell).
Status: ✅ Produktiv 2026-06-27
Quelle (Default): data/baeckerei_2025/sachverhaltsblatt.json
Siehe: docs/ANHANG.md (Case-Facts-Block, Bau-Schritt 1)
"""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DEFAULT_SACHVERHALT = BASE / "data/baeckerei_2025/sachverhaltsblatt.json"

# Pflicht-Schlüssel des Case-Facts-Blocks (Minimal-Schema). Werte dürfen leer/None
# sein — fehlende FAKTEN werden im Anhang als 'unclear' behandelt, nicht erfunden.
PFLICHT_TOP = ("stammdaten", "mitarbeiter", "organbezuege", "nachtragsereignisse")
PFLICHT_STAMMDATEN = (
    "firma", "rechtsform", "sitz", "geschaeftsjahr", "stichtag",
    "groessenklasse", "guv_verfahren",
)


def get_sachverhalt(path: str | Path = DEFAULT_SACHVERHALT) -> dict:
    """Lädt und validiert den Sachverhaltsblatt-JSON (Case-Facts-Block).

    Returns:
        dict mit den Schlüsseln stammdaten / mitarbeiter / organbezuege /
        nachtragsereignisse (+ optionale Felder). Validiert nur die STRUKTUR,
        nicht die fachliche Richtigkeit (die prüft der Mensch).

    Raises:
        FileNotFoundError: Sachverhaltsblatt fehlt.
        ValueError: Pflicht-Struktur verletzt.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Sachverhaltsblatt nicht gefunden: {p}")

    with open(p, encoding="utf-8") as f:
        daten = json.load(f)

    fehlen = [k for k in PFLICHT_TOP if k not in daten]
    if fehlen:
        raise ValueError(f"Sachverhaltsblatt unvollständig — fehlende Blöcke: {fehlen}")

    stammdaten = daten.get("stammdaten") or {}
    fehlen_sd = [k for k in PFLICHT_STAMMDATEN if not stammdaten.get(k)]
    if fehlen_sd:
        raise ValueError(f"Sachverhaltsblatt: stammdaten unvollständig — {fehlen_sd}")

    if not isinstance(daten.get("nachtragsereignisse"), list):
        raise ValueError("Sachverhaltsblatt: 'nachtragsereignisse' muss eine Liste sein.")

    return daten


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    sv = get_sachverhalt()
    print("OK Sachverhaltsblatt geladen:")
    print(f"  Firma: {sv['stammdaten']['firma']}")
    print(f"  Mitarbeiter Ø GJ/VJ: {sv['mitarbeiter'].get('durchschnitt_gj')}/{sv['mitarbeiter'].get('durchschnitt_vj')}")
    print(f"  Schutzklausel §286(4): {sv['organbezuege'].get('schutzklausel_286_4')}")
    print(f"  Nachtragsereignisse: {len(sv['nachtragsereignisse'])}")
