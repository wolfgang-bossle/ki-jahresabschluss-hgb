"""
jahresabschluss.py
Zweck: Engine — Saldenliste + Tabelle B (Konto->Konzept) + XBRL-Taxonomie
       => Bilanz (§266) + GuV (§275) als Datenmodell, Bilanzprobe = 0,00 € hart.
Status: ✅ Produktiv 2026-06-18
Abhängigkeiten: mcp/config/skr03_mapping.json, taxonomy/*-presentation-*.xml,
                taxonomy/*-label-de.xml, openpyxl
Datenagnostisch (§2.1): KEINE Kontonummern/Mandant im Code. Werte aus Saldenliste,
                Zuordnung aus Tabelle B, Gliederung aus der Taxonomie (§2.8).
Letzte Änderung: 2026-06-18
"""
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import openpyxl

# --- Taxonomie-Strukturkonstanten (NICHT mandantenspezifisch, aus de-gaap-ci) ---
# Ort, an dem der abgeleitete Jahresüberschuss in der Bilanz steht (§266 A.V):
NETINCOME_CONCEPT = "de-gaap-ci_bs.eqLiab.equity.netIncome"
BS_AKTIVA_ROOT = "de-gaap-ci_bs.ass"
BS_PASSIVA_ROOT = "de-gaap-ci_bs.eqLiab"
STD_LABEL_ROLE = "http://www.xbrl.org/2003/role/label"
XLINK = "{http://www.w3.org/1999/xlink}"


def _lname(tag):
    return tag.split("}")[-1]


def is_revenue(concept, balance):
    """GuV-Ertrag (+) vs. Aufwand (−) — aus dem XBRL-balance-Attribut der amtlichen
    Taxonomie (credit = Ertrag, debit = Aufwand), NICHT geraten (§2.8). Fehlt das
    balance für ein GuV-Konzept, ist das Vorzeichen nicht ableitbar → harter Fehler
    statt stiller Annahme (§2.7)."""
    b = balance.get(concept)
    if b is None:
        raise ValueError(
            f"GuV-Konzept ohne balance-Attribut im Taxonomie-Katalog: {concept} "
            f"— Ertrag/Aufwand nicht ableitbar. Katalog ggf. aus dem Schema neu extrahieren.")
    return b == "credit"


# --------------------------------------------------------------------------- #
# Taxonomie laden
# --------------------------------------------------------------------------- #
def load_labels(label_path):
    """concept_id -> deutsches Standard-Label aus der Label-Linkbase."""
    root = ET.parse(label_path).getroot()
    loc, arc, lab = {}, defaultdict(list), defaultdict(list)
    for e in root.iter():
        n = _lname(e.tag)
        if n == "loc":
            loc[e.get(XLINK + "label")] = e.get(XLINK + "href", "").split("#")[-1]
        elif n == "labelArc":
            arc[e.get(XLINK + "from")].append(e.get(XLINK + "to"))
        elif n == "label":
            lab[e.get(XLINK + "label")].append((e.get(XLINK + "role", ""), (e.text or "").strip()))
    out = {}
    for loclab, cid in loc.items():
        for tolab in arc.get(loclab, []):
            for role, txt in lab.get(tolab, []):
                if role == STD_LABEL_ROLE and txt:
                    out[cid] = txt
    return out


def build_tree(pres_path, want_concepts):
    """Presentation-Linkbase -> (child->parent, parent->[(order,child)]).
    Wählt das Netzwerk mit den meisten gesuchten Konzepten."""
    root = ET.parse(pres_path).getroot()
    links = []
    for pl in root.iter():
        if _lname(pl.tag) != "presentationLink":
            continue
        loc_l, arcs = {}, []
        for c in pl:
            if _lname(c.tag) == "loc":
                loc_l[c.get(XLINK + "label")] = c.get(XLINK + "href", "").split("#")[-1]
            elif _lname(c.tag) == "presentationArc":
                arcs.append((c.get(XLINK + "from"), c.get(XLINK + "to"), float(c.get("order", 0))))
        links.append((loc_l, arcs))
    loc_l, arcs = max(links, key=lambda L: len(set(L[0].values()) & want_concepts))
    c2p, p2c = {}, defaultdict(list)
    for f, t, o in arcs:
        pc, cc = loc_l.get(f), loc_l.get(t)
        if pc and cc:
            c2p[cc] = pc
            p2c[pc].append((o, cc))
    for k in p2c:
        p2c[k].sort()
    return c2p, p2c


# --------------------------------------------------------------------------- #
# Mandantendaten laden
# --------------------------------------------------------------------------- #
def read_saldenliste(xlsx_path):
    """Konto -> (bezeichnung, saldo_gj, saldo_vj). 4-Spalten-Format."""
    ws = openpyxl.load_workbook(xlsx_path, data_only=True).active
    konten = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row[0] or not str(row[0])[0].isdigit():
            continue
        konten[str(row[0]).strip()] = (str(row[1]), float(row[2] or 0), float(row[3] or 0))
    return konten


def load_mapping(map_path):
    """Tabelle B: Konto -> taxonomy_concept."""
    mp = json.loads(Path(map_path).read_text(encoding="utf-8"))["mapping"]
    return {k: m["taxonomy_concept"] for k, m in mp.items()}


def load_balance(balance_path):
    """concept_id -> 'credit'|'debit' aus dem schlanken, einmalig aus dem de-gaap-ci-
    Schema (xbrli:balance) extrahierten Katalog. Liefert das GuV-Vorzeichen (§2.8)."""
    return json.loads(Path(balance_path).read_text(encoding="utf-8"))["balance"]


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
def _rollup(leaf_vals, c2p):
    """Knoten-Werte (gj,vj) + beitragende Konten je Knoten.
    Die Vorzeichen (GuV-Ertrag/Aufwand) stehen schon in den Leaf-Werten (siehe
    is_revenue beim Leaf-Aufbau); der Rollup summiert nur noch entlang der Hierarchie."""
    node = defaultdict(lambda: [0.0, 0.0])
    quelle = defaultdict(set)
    for concept, (gj, vj, konten) in leaf_vals.items():
        cur, seen = concept, set()
        while cur and cur not in seen:
            seen.add(cur)
            node[cur][0] += gj
            node[cur][1] += vj
            quelle[cur].update(konten)
            cur = c2p.get(cur)
    return node, quelle


def _render(root_concept, node, p2c, labels, quelle):
    """Geordnete, flache Positionsliste ab einem Wurzelkonzept."""
    rows = []

    def walk(c, depth):
        if c not in node:
            return
        rows.append({
            "ebene": depth,
            "konzept": c,
            "label": labels.get(c, c),
            "wert_gj": round(node[c][0], 2),
            "wert_vj": round(node[c][1], 2),
            "quelle": sorted(quelle.get(c, [])),
        })
        for _, ch in p2c.get(c, []):
            if ch in node:
                walk(ch, depth + 1)

    walk(root_concept, 0)
    return rows


def generate(saldenliste, mapping_file, taxonomy_dir, anlagenbuchhaltung=None):
    tax = Path(taxonomy_dir)
    labels = load_labels(tax / "de-gaap-ci-2025-04-01-label-de.xml")
    balance = load_balance(tax / "de-gaap-ci-2025-04-01-balance-is.json")
    konten = read_saldenliste(saldenliste)
    konto2concept = load_mapping(mapping_file)

    # Konten ohne Mapping = harter Fehler (kein stilles Ignorieren)
    fehlend = [k for k in konten if k not in konto2concept]
    if fehlend:
        raise ValueError(f"Konten ohne Tabelle-B-Zuordnung: {fehlend}")

    # Leaf-Aggregation getrennt nach Bilanz / GuV
    bs_leaf = defaultdict(lambda: [0.0, 0.0, []])
    is_leaf = defaultdict(lambda: [0.0, 0.0, []])
    for konto, (_, gj, vj) in konten.items():
        c = konto2concept[konto]
        if c.startswith("de-gaap-ci_bs."):
            bs_leaf[c][0] += gj; bs_leaf[c][1] += vj; bs_leaf[c][2].append(konto)
        elif c.startswith("de-gaap-ci_is."):
            s = 1 if is_revenue(c, balance) else -1   # GuV signiert (credit/debit, §2.8)
            is_leaf[c][0] += s * gj; is_leaf[c][1] += s * vj; is_leaf[c][2].append(konto)

    # Jahresüberschuss aus der GuV ableiten -> in die Bilanz (§266 A.V)
    jue_gj = round(sum(v[0] for v in is_leaf.values()), 2)
    jue_vj = round(sum(v[1] for v in is_leaf.values()), 2)
    bs_leaf[NETINCOME_CONCEPT][0] += jue_gj
    bs_leaf[NETINCOME_CONCEPT][1] += jue_vj
    bs_leaf[NETINCOME_CONCEPT][2].append("(abgeleitet aus GuV)")

    # Bilanz aufbauen
    bs_concepts = set(bs_leaf)
    bs_c2p, bs_p2c = build_tree(tax / "de-gaap-ci-2025-04-01-presentation-balanceSheet.xml", bs_concepts)
    bs_node, bs_q = _rollup(bs_leaf, bs_c2p)
    aktiva = _render(BS_AKTIVA_ROOT, bs_node, bs_p2c, labels, bs_q)
    passiva = _render(BS_PASSIVA_ROOT, bs_node, bs_p2c, labels, bs_q)
    summe_aktiva = (round(bs_node[BS_AKTIVA_ROOT][0], 2), round(bs_node[BS_AKTIVA_ROOT][1], 2))
    summe_passiva = (round(bs_node[BS_PASSIVA_ROOT][0], 2), round(bs_node[BS_PASSIVA_ROOT][1], 2))

    # GuV aufbauen
    is_concepts = set(is_leaf)
    is_c2p, is_p2c = build_tree(tax / "de-gaap-ci-2025-04-01-presentation-incomeStatement.xml", is_concepts)
    is_node, is_q = _rollup(is_leaf, is_c2p)
    if not is_node:
        raise ValueError("Keine GuV-Konten in der Saldenliste — GuV und "
                         "Jahresüberschuss nicht ableitbar (§2.7).")
    is_root = next(c for c in is_node if is_c2p.get(c) not in is_node)
    guv = _render(is_root, is_node, is_p2c, labels, is_q)

    # Bilanzprobe — hart
    probe_gj = round(summe_aktiva[0] - summe_passiva[0], 2)
    probe_vj = round(summe_aktiva[1] - summe_passiva[1], 2)
    if probe_gj != 0.0 or probe_vj != 0.0:
        raise ValueError(f"BILANZ NICHT AUSGEGLICHEN: GJ {probe_gj}, VJ {probe_vj} "
                         f"-> Konto in der Saldenliste falsch angesetzt (§2.7)")
    if round(is_node[is_root][0], 2) != jue_gj:
        raise ValueError("JÜ aus GuV-Rollup != abgeleitetem JÜ — Abstimmung verletzt")

    modell = {
        "bilanz": {
            "aktiva": aktiva, "passiva": passiva,
            "summe_aktiva_gj": summe_aktiva[0], "summe_aktiva_vj": summe_aktiva[1],
            "summe_passiva_gj": summe_passiva[0], "summe_passiva_vj": summe_passiva[1],
        },
        "guv": {"positionen": guv, "jahresueberschuss_gj": jue_gj, "jahresueberschuss_vj": jue_vj},
        "metadata": {
            "quelle": Path(saldenliste).name,
            "bilanzprobe_gj": probe_gj, "bilanzprobe_vj": probe_vj,
            "jue_abgestimmt": True,
            "taxonomie": "de-gaap-ci-2025-04-01",
        },
    }

    # Anlagenspiegel — additiver Block, ändert Bilanz/GuV NICHT (§2.7). Lazy-Import
    # vermeidet Zirkularität (anlagenspiegel.py importiert aus diesem Modul).
    if anlagenbuchhaltung is not None:
        from anlagenspiegel import generate_anlagenspiegel
        modell["anlagenspiegel"] = generate_anlagenspiegel(
            anlagenbuchhaltung, saldenliste, mapping_file, taxonomy_dir)

    return modell


if __name__ == "__main__":
    import sys
    base = Path(__file__).resolve().parent.parent
    dm = generate(
        base / "data/baeckerei_2025/Saldenliste.xlsx",
        base / "mcp/config/skr03_mapping.json",
        base / "taxonomy",
        anlagenbuchhaltung=base / "data/baeckerei_2025/Anlagenbuchhaltung.xlsx",
    )
    out = base / "output/baeckerei_2025"
    out.mkdir(parents=True, exist_ok=True)
    (out / "jahresabschluss_datenmodell.json").write_text(
        json.dumps(dm, ensure_ascii=False, indent=2), encoding="utf-8")

    def show(title, rows):
        print(f"\n{title}")
        for r in rows:
            print(f"{'  ' * r['ebene']}{r['label'][:46 - 2 * r['ebene']]:<{48 - 2 * r['ebene']}}"
                  f"{r['wert_gj']:>13,.0f}{r['wert_vj']:>13,.0f}")

    sys.stdout.reconfigure(encoding="utf-8")
    b = dm["bilanz"]
    print("=" * 74, "\nBILANZ", f"{'GJ':>50}{'VJ':>13}")
    show("AKTIVA", b["aktiva"]); show("PASSIVA", b["passiva"])
    print("-" * 74)
    print(f"{'SUMME AKTIVA':<48}{b['summe_aktiva_gj']:>13,.0f}{b['summe_aktiva_vj']:>13,.0f}")
    print(f"{'SUMME PASSIVA':<48}{b['summe_passiva_gj']:>13,.0f}{b['summe_passiva_vj']:>13,.0f}")
    show("\nGEWINN- UND VERLUSTRECHNUNG (§275 GKV)", dm["guv"]["positionen"])
    m = dm["metadata"]
    print("-" * 74)
    print(f"Bilanzprobe GJ {m['bilanzprobe_gj']}  VJ {m['bilanzprobe_vj']}  | "
          f"JÜ {dm['guv']['jahresueberschuss_gj']:,.0f} / {dm['guv']['jahresueberschuss_vj']:,.0f}  | "
          f"abgestimmt={m['jue_abgestimmt']}")
    if "anlagenspiegel" in dm:
        rc = dm["anlagenspiegel"]["reconciliation"]
        print(f"Anlagenspiegel: BW GJ {rc['bw_gj']:,.0f} / VJ {rc['bw_vj']:,.0f} | "
              f"AfA {rc['afa_jahr']:,.0f} = Saldenliste-AfA {rc['afa_aufwand_saldenliste']:,.0f} | "
              f"abgestimmt={rc['abgestimmt']}")
    print(f"\nGeschrieben: {out / 'jahresabschluss_datenmodell.json'}")
