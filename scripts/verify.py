"""
verify.py
Zweck: Seiteneffektfreier Verifikations-Lauf der Jahresabschluss-Engine (= der bisher
       fehlende Test). Ruft generate() (schreibt NICHT auf Platte; nur __main__ tut das),
       wodurch die harten Checks der Engine laufen (Bilanzprobe = 0,00, JÜ-Abstimmung,
       Anlagenspiegel-Reconciliation), und vergleicht zusätzlich die centgenau verifizierten
       ANKER. Abweichung oder Exception -> stderr + Exit 1. Sonst "OK" + Exit 0.
Genutzt von: .claude/hooks/{verify_on_change,session_anchors}.py und dem Commit-Gate.
Aufruf:  python scripts/verify.py
Status: ✅ 2026-06-19
"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "mcp"))

# Verifizierte Anker (centgenau, aus dem freigegebenen Datenmodell). Drift hier = Alarm.
ANKER_BILANZ = {
    "summe_aktiva_gj": 1_700_000.0, "summe_aktiva_vj": 1_476_500.0,
    "summe_passiva_gj": 1_700_000.0, "summe_passiva_vj": 1_476_500.0,
}
ANKER_JUE_GJ, ANKER_JUE_VJ = 200_000.0, 150_000.0
ANKER_ASP = {"bw_gj": 943_000.0, "bw_vj": 876_500.0, "afa_jahr": 83_500.0}


def run():
    from jahresabschluss import generate  # Import erst hier -> saubere Fehlermeldung
    dm = generate(
        BASE / "data/baeckerei_2025/Saldenliste.xlsx",
        BASE / "mcp/config/skr03_mapping.json",
        BASE / "taxonomy",
        anlagenbuchhaltung=BASE / "data/baeckerei_2025/Anlagenbuchhaltung.xlsx",
    )

    abw = []
    b = dm["bilanz"]
    for k, soll in ANKER_BILANZ.items():
        if round(b[k], 2) != soll:
            abw.append(f"Bilanz {k}: {b[k]:,.2f} != Anker {soll:,.2f}")

    g = dm["guv"]
    if round(g["jahresueberschuss_gj"], 2) != ANKER_JUE_GJ:
        abw.append(f"JÜ GJ: {g['jahresueberschuss_gj']:,.2f} != {ANKER_JUE_GJ:,.2f}")
    if round(g["jahresueberschuss_vj"], 2) != ANKER_JUE_VJ:
        abw.append(f"JÜ VJ: {g['jahresueberschuss_vj']:,.2f} != {ANKER_JUE_VJ:,.2f}")

    asp = dm.get("anlagenspiegel")
    if asp is None:
        abw.append("Anlagenspiegel-Block fehlt im Datenmodell")
    else:
        rc = asp["reconciliation"]
        for k, soll in ANKER_ASP.items():
            if round(rc[k], 2) != soll:
                abw.append(f"Anlagenspiegel {k}: {rc[k]:,.2f} != Anker {soll:,.2f}")

    if abw:
        raise ValueError("ANKER-ABWEICHUNG:\n  - " + "\n  - ".join(abw))

    return (f"OK: Aktiva=Passiva 1.700.000 (VJ 1.476.500), Bilanzprobe 0,00, "
            f"JÜ 200.000/150.000, Anlagenspiegel BW 943.000/876.500, Σ AfA 83.500 — "
            f"alle Anker centgenau.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        print(run())
    except Exception as e:  # Bilanzprobe-/JÜ-/Reconciliation-ValueError oder Anker-Abweichung
        print(f"VERIFIKATION FEHLGESCHLAGEN:\n{e}", file=sys.stderr)
        sys.exit(1)
