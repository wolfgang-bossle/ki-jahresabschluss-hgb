"""
generate_saldenliste.py
Zweck: Synthese-Generator — erzeugt centgenaue, bilanzierte SKR03-Saldenlisten
       als Excel (4-Spalten-Format) für Engine-Stress-Tests.
Status: ✅ Produktiv seit 2026-06-27
Abhängigkeiten: mcp/config/skr03_mapping.json, openpyxl
Letzte Änderung: 2026-06-27
"""
import argparse
import json
import random
from pathlib import Path

import openpyxl
from openpyxl.styles import Font

BASE = Path(__file__).resolve().parent.parent
MAPPING_PATH = BASE / "mcp/config/skr03_mapping.json"
DEFAULT_TAXONOMY = BASE / "taxonomy"

AKTIVA    = ["0210","0440","0441","0450","0520","0521","0650","1000","1140","1200","1400"]
PASSIVA   = ["0670","0671","0800","0860","0950","1600","1740"]
IS_ERTRAG = ["8400","8401"]
IS_AUFWAND= ["2100","3300","3310","4100","4130","4210","4240","4360","4830","4900","7610"]

MIN_AKTIVA  = ["1200"]
MIN_PASSIVA = ["0800"]
MIN_ERTRAG  = ["8400"]
MIN_AUFWAND = ["4100","7610"]

BANK = "1200"   # Puffer-Konto für VJ-Rundungsausgleich


def load_names():
    m = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))["mapping"]
    return {k: v["name"] for k, v in m.items()}


def split_cents(rng, total, n):
    """Verteile total Cent ganzzahlig auf n Teile (alle ≥ 1, falls total ≥ n)."""
    if n == 1:
        return [total]
    if total <= 0:
        return [0] * n
    if total < n:
        return [1 if i < total else 0 for i in range(n)]
    if total == n:
        return [1] * n
    cuts = sorted(rng.sample(range(1, total), n - 1))
    cuts = [0] + cuts + [total]
    return [cuts[i + 1] - cuts[i] for i in range(n)]


def generate(seed, bs_eur, jue_ratio, vj_faktor, mode):
    rng   = random.Random(seed)
    names = load_names()

    ak = MIN_AKTIVA  if mode == "min" else AKTIVA
    pa = MIN_PASSIVA if mode == "min" else PASSIVA
    er = MIN_ERTRAG  if mode == "min" else IS_ERTRAG
    aw = MIN_AUFWAND if mode == "min" else IS_AUFWAND

    # --- GJ in Cent (integer → centgenau) ---
    bs = round(bs_eur * 100)
    assert bs >= max(len(ak), len(pa)), \
        f"Bilanzsumme {bs_eur} EUR zu klein für {max(len(ak), len(pa))} Konten"

    umsatz = rng.randint(int(bs * 1.5), int(bs * 4.0))
    jue    = round(umsatz * jue_ratio)          # negativ = Jahresfehlbetrag
    aw_tot = max(umsatz - jue, len(aw))         # Σ Aufwandkonten (mind. 1 Cent/Konto)
    pa_tot = max(bs - jue, len(pa))             # Passiva non-JÜ

    er_gj = split_cents(rng, umsatz, len(er))
    aw_gj = split_cents(rng, aw_tot, len(aw))
    pa_gj = split_cents(rng, pa_tot, len(pa))
    ak_gj = split_cents(rng, bs,     len(ak))   # Aktiva = Bilanzsumme GJ

    # Interne GJ-Probe (muss 0 sein; sonst Bug im Generator)
    _probe_gj = sum(ak_gj) - sum(pa_gj) - (sum(er_gj) - sum(aw_gj))
    assert _probe_gj == 0, f"Interner Fehler GJ Bilanzprobe: {_probe_gj}"

    # --- VJ: integer-skaliert, Puffer-Konto gleicht Cent-Differenz aus ---
    sc = lambda v: max(0, round(v * vj_faktor))

    er_vj  = [sc(v) for v in er_gj]
    aw_vj  = [sc(v) for v in aw_gj]
    jue_vj = sum(er_vj) - sum(aw_vj)
    pa_vj  = [sc(v) for v in pa_gj]
    ak_vj  = [sc(v) for v in ak_gj]

    buf = ak.index(BANK) if BANK in ak else len(ak) - 1
    ak_vj[buf] += (sum(pa_vj) + jue_vj) - sum(ak_vj)  # Rundungsausgleich

    _probe_vj = sum(ak_vj) - sum(pa_vj) - (sum(er_vj) - sum(aw_vj))
    assert _probe_vj == 0, f"Interner Fehler VJ Bilanzprobe: {_probe_vj}"

    # --- Zusammenbauen (EUR = Cent / 100) ---
    rows = (
        [(k, names[k], gj/100, vj/100) for k, gj, vj in zip(ak, ak_gj, ak_vj)] +
        [(k, names[k], gj/100, vj/100) for k, gj, vj in zip(pa, pa_gj, pa_vj)] +
        [(k, names[k], gj/100, vj/100) for k, gj, vj in zip(er, er_gj, er_vj)] +
        [(k, names[k], gj/100, vj/100) for k, gj, vj in zip(aw, aw_gj, aw_vj)]
    )
    rows.sort(key=lambda r: r[0])

    meta = {
        "seed": seed, "konten": len(rows), "modus": mode,
        "bilanzsumme_gj": bs / 100, "bilanzsumme_vj": sum(ak_vj) / 100,
        "jue_gj": jue / 100, "jue_vj": jue_vj / 100,
    }
    return rows, meta


def write_excel(rows, path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Saldenliste"
    ws.append(["Konto", "Bezeichnung", "Saldo GJ", "Saldo VJ"])
    for c in ws[1]:
        c.font = Font(bold=True)
    for row in rows:
        ws.append(list(row))
    for col, w in zip("ABCD", [10, 45, 16, 16]):
        ws.column_dimensions[col].width = w
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


# --------------------------------------------------------------------------- #
# Profile mode — deterministic, industry-specific, taxonomy-grounded (§2.8)
# --------------------------------------------------------------------------- #
def _tax_bal(td=None):
    p = Path(td or DEFAULT_TAXONOMY) / "de-gaap-ci-2025-04-01-balance-is.json"
    return json.loads(p.read_text(encoding="utf-8"))["balance"]


def _psum(kk, k2c, side, ex=None):
    pfx = f"de-gaap-ci_bs.{side}."
    return round(sum(v for k, v in kk.items()
                     if k != ex and k2c.get(k, "").startswith(pfx)), 2)


def _pjue(kk, k2c, bal):
    return round(sum((v if bal.get(k2c.get(k, "")) == "credit" else -v)
                     for k, v in kk.items()
                     if k2c.get(k, "").startswith("de-gaap-ci_is.")), 2)


def generate_from_profile(profil_path, td=None, ausgabe=None):
    """Profil-JSON -> centgenaue, bilanzierte Saldenliste.xlsx.
    Gewinnvortrag (balance_konto) wird automatisch abgeleitet; Bilanzprobe = 0,00."""
    pf  = json.loads(Path(profil_path).read_text(encoding="utf-8"))
    mp  = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))["mapping"]
    k2c = {k: m["taxonomy_concept"] for k, m in mp.items()}
    k2n = {k: m.get("name", k) for k, m in mp.items()}
    bal = _tax_bal(td)
    bk  = pf["balance_konto"]
    bad = [k for k in pf["konten"] if k not in k2c]
    if bad:
        raise ValueError(f"Konten nicht in Tabelle B: {bad}")
    gj  = {k: float(v["gj"]) for k, v in pf["konten"].items()}
    vj  = {k: float(v["vj"]) for k, v in pf["konten"].items()}
    bez = {k: v.get("bezeichnung", k2n.get(k, k)) for k, v in pf["konten"].items()}
    for kk in (gj, vj):
        kk[bk] = round(_psum(kk, k2c, "ass") - _psum(kk, k2c, "eqLiab", bk)
                       - _pjue(kk, k2c, bal), 2)
    bez[bk] = pf.get("balance_konto_bezeichnung", k2n.get(bk, bk))
    for lbl, kk in (("GJ", gj), ("VJ", vj)):
        probe = round(_psum(kk, k2c, "ass") - _psum(kk, k2c, "eqLiab") - _pjue(kk, k2c, bal), 2)
        if probe:
            raise ValueError(f"Bilanzprobe {lbl} = {probe} — interner Fehler")
    slug = Path(profil_path).stem.replace("profile_", "")
    out  = Path(ausgabe) if ausgabe else BASE / f"data/{slug}_2025/Saldenliste.xlsx"
    rows = sorted([(k, bez.get(k, ""), gj[k], vj[k]) for k in gj if gj[k] or vj[k]])
    write_excel(rows, out)
    return {"ausgabe": str(out), "branche": pf.get("branche", ""),
            "bilanzsumme_gj": _psum(gj, k2c, "ass"),
            "jue_gj": _pjue(gj, k2c, bal), "jue_vj": _pjue(vj, k2c, bal),
            "gv_gj": gj[bk], "gv_vj": vj[bk]}


def main():
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="SKR03-Saldenlisten-Generator")
    ap.add_argument("--profil",      help="Branchen-Profil JSON (Profile-Modus)")
    ap.add_argument("--taxonomie",   default=str(DEFAULT_TAXONOMY))
    ap.add_argument("--out",         default="", help="Ausgabepfad .xlsx")
    ap.add_argument("--seed",        type=int,   default=42)
    ap.add_argument("--bilanzsumme", type=float, default=1_000_000)
    ap.add_argument("--jue-ratio",   type=float, default=0.05)
    ap.add_argument("--vj-faktor",   type=float, default=0.85)
    ap.add_argument("--konten", choices=["min", "voll"], default="voll")
    args = ap.parse_args()
    try:
        if args.profil:
            r = generate_from_profile(args.profil, args.taxonomie, args.out or None)
            print(f"OK: {r['branche']} -> {r['ausgabe']}")
            print(f"   Bilanzprobe GJ/VJ : 0,00 / 0,00")
            print(f"   JUE GJ/VJ         : {r['jue_gj']:>12,.2f} / {r['jue_vj']:>12,.2f}")
            print(f"   Bilanzsumme GJ    : {r['bilanzsumme_gj']:>12,.2f}")
            print(f"   Gewinnvortrag GJ  : {r['gv_gj']:>12,.2f} / VJ {r['gv_vj']:>12,.2f}")
        else:
            rows, meta = generate(args.seed, args.bilanzsumme, args.jue_ratio,
                                  args.vj_faktor, args.konten)
            out = args.out or str(BASE / f"data/synth_{args.seed}/Saldenliste.xlsx")
            write_excel(rows, out)
            print(f"OK: Stress-Test -> {out}")
            print(f"   Konten:     {meta['konten']} ({meta['modus']})")
            print(f"   Bilanzsumme GJ {meta['bilanzsumme_gj']:>12,.2f} | VJ {meta['bilanzsumme_vj']:>12,.2f}")
            print(f"   JUE/JF      GJ {meta['jue_gj']:>12,.2f} | VJ {meta['jue_vj']:>12,.2f}")
    except Exception as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
