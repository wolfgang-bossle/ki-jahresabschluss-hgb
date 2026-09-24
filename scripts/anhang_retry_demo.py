"""
anhang_retry_demo.py
Zweck: CCA 4.4 Lernrtefakt — Validation/Retry-Loop mit pruefe_section() als
       deterministischem Validator. llm_fn = Platzhalter fuer echten LLM-Aufruf
       (API-Kontext). In Claude Code uebernimmt Claude den Loop selbst (liest
       Tool-Fehler, generiert neu) — kein Python-Code noetig.
Status: Lernrtefakt (nicht produktiv)
Abhaengigkeiten: mcp/anhang.py, mcp/jahresabschluss.py
Aufruf: python scripts/anhang_retry_demo.py
Letzte Aenderung: 2026-06-25
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "mcp"))

from anhang import baue_anlagenspiegel_tabelle, baue_kontext, pruefe_section  # noqa: E402
from jahresabschluss import generate  # noqa: E402
from sachverhalt import get_sachverhalt  # noqa: E402

DEFAULT_SALDENLISTE      = BASE / "data/baeckerei_2025/Saldenliste.xlsx"
DEFAULT_MAPPING          = BASE / "mcp/config/skr03_mapping.json"
DEFAULT_TAXONOMIE        = BASE / "taxonomy"
DEFAULT_ANLAGENBUCHHALTUNG = BASE / "data/baeckerei_2025/Anlagenbuchhaltung.xlsx"


# ---------------------------------------------------------------------------
# Kern-Muster: retry_loop (CCA 4.4 Referenzimplementierung)
# ---------------------------------------------------------------------------
def retry_loop(llm_fn, section_id, datenmodell, sachverhalt, max_retries=3):
    """Validation/Retry-Loop.

    llm_fn(kontext, fehler_vorherig) -> section_dict
      API-Kontext:   echter client.messages.create()-Aufruf mit tool_use.
      Claude Code:   Claude liest Fehler aus anhang_section_pruefen() und
                     generiert automatisch neu — dieser Python-Loop entfaellt.
    """
    fehler_vorherig = None

    for attempt in range(1, max_retries + 1):
        kontext = baue_kontext(section_id, datenmodell, sachverhalt)
        section = llm_fn(kontext, fehler_vorherig)

        ergebnis = pruefe_section(section, datenmodell, sachverhalt)

        status = "OK" if ergebnis["ok"] else f"{len(ergebnis['fehler'])} Fehler"
        print(f"  Versuch {attempt}: {status}")

        if ergebnis["ok"]:
            return section

        fehler_vorherig = ergebnis["fehler"]
        print(f"    Fehler: {fehler_vorherig[0]}")

    raise RuntimeError(
        f"Validierung nach {max_retries} Versuchen fehlgeschlagen: {fehler_vorherig}"
    )


# ---------------------------------------------------------------------------
# Demo-Stub: simuliert 1. Versuch fehlerhaft, 2. Versuch korrekt
# ---------------------------------------------------------------------------
def _falsche_section(datenmodell):
    """Injiziert falschen Buchwert — simuliert LLM-Halluzination."""
    s = copy.deepcopy(baue_anlagenspiegel_tabelle(datenmodell))
    for claim in s["blocks"][0]["claims"]:
        if claim["quelle"]["pfad"] == "anlagenspiegel.summe.bw_gj":
            claim["wert"] = claim["wert"] + 7000   # falsch: +7.000 EUR
    return s


def make_demo_llm_fn(datenmodell):
    """Closure: gibt beim 1. Aufruf eine fehlerhafte, beim 2. die korrekte Section."""
    versuch = [0]

    def llm_fn(kontext, fehler_vorherig):
        versuch[0] += 1
        if versuch[0] == 1:
            print("    [LLM] generiert Section (Buchwert halluziniert)...")
            return _falsche_section(datenmodell)
        print(f"    [LLM] korrigiert (Fehler-Kontext: {str(fehler_vorherig[0])[:70]}...)")
        return baue_anlagenspiegel_tabelle(datenmodell)

    return llm_fn


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
def main():
    print("=== CCA 4.4 — Validation/Retry-Loop Demo ===\n")

    dm = generate(DEFAULT_SALDENLISTE, DEFAULT_MAPPING, DEFAULT_TAXONOMIE,
                  anlagenbuchhaltung=DEFAULT_ANLAGENBUCHHALTUNG)
    sv = get_sachverhalt()

    print("Retry-Loop startet fuer Section 'anlagenspiegel':")
    try:
        result = retry_loop(make_demo_llm_fn(dm), "anlagenspiegel", dm, sv, max_retries=3)
        print(f"\nErgebnis: OK — {result['section_id']}, "
              f"confidence={result['confidence']}, "
              f"blocks={len(result['blocks'])}")
    except RuntimeError as e:
        print(f"\nFehlgeschlagen: {e}")
        sys.exit(1)

    print("\n--- Muster (CCA 4.4) ---")
    print("1. llm_fn generiert Output (tool_use + Schema)")
    print("2. pruefe_section() validiert deterministisch")
    print("3. Fehler strukturiert zurueck an llm_fn")
    print("4. Nach MAX_RETRIES: RuntimeError + Human-Review (CCA 5.5)")


if __name__ == "__main__":
    main()
