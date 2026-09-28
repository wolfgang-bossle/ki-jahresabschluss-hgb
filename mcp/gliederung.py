"""
gliederung.py
Zweck: Ordnet die Positionen des Datenmodells in die gesetzliche Gliederung
       (§ 266 Abs. 2/3, § 275 Abs. 2 HGB) aus mcp/config/gliederung_hgb.json.
       Liest nur und rechnet nichts: jeder Posten übernimmt Wert und Quelle genau
       eines Konzepts aus dem Datenmodell. Taxonomie-Hilfssummen ohne Posten
       entfallen. Ein Konto-Konzept ohne Posten ist ein harter Fehler, damit kein
       Wert stillschweigend aus der Darstellung fällt.
Status: am erfundenen Musterfall gebaut, nicht im Mandantenbetrieb erprobt (README, Einordnung)
Abhängigkeiten: mcp/config/gliederung_hgb.json (reine Standardbibliothek)
"""
import json
from pathlib import Path

GLIEDERUNG = Path(__file__).resolve().parent / "config" / "gliederung_hgb.json"


def lade_gliederung(path: str | Path = GLIEDERUNG) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _ist_blatt(konzept: str, alle: set[str]) -> bool:
    return not any(k.startswith(konzept + ".") for k in alle)


def gliedere(positionen: list[dict], teil: str, gliederung: dict | None = None) -> list[dict]:
    """Positionen (aktiva | passiva | guv) in Gesetzesfolge, im Format des Datenmodells
    (ebene, label, wert_gj, wert_vj, quelle, konzept). Posten ohne Konzept im
    Datenmodell entfallen samt Unterposten."""
    gliederung = gliederung or lade_gliederung()
    nach_konzept = {p["konzept"]: p for p in positionen if p.get("konzept")}
    out, erfasst, endposten = [], set(), []

    def lauf(posten, ebene):
        for g in posten:
            pos = nach_konzept.get(g["konzept"])
            if pos is None:
                continue
            erfasst.add(g["konzept"])
            if not g.get("posten"):
                endposten.append(g["konzept"])
            out.append({**pos, "ebene": ebene,
                        "label": f'{g["gliederung"]} {g["bezeichnung"]}'})
            lauf(g.get("posten", []), ebene + 1)

    lauf(gliederung[teil], 1)

    # Ein Konto-Konzept ist gedeckt, wenn es selbst Posten ist oder unter einem
    # Posten ohne Unterposten liegt (z. B. Kasse und Bank unter B.IV.).
    alle = set(nach_konzept)
    offen = [k for k in alle if _ist_blatt(k, alle) and k not in erfasst
             and not any(k.startswith(e + ".") for e in endposten)]
    if offen:
        raise ValueError(f"Gliederung {teil}: Konzept(e) ohne Posten nach HGB-Schema, "
                         f"Wert würde fehlen: {sorted(offen)} (gliederung_hgb.json ergänzen).")
    return out
