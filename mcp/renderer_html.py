"""
renderer_html.py
Zweck: Renderer — nimmt das geerdete Datenmodell (aus jahresabschluss.generate())
       und erzeugt eine eigenständige, interaktive HTML-Darstellung des
       Jahresabschlusses: Bilanz (§266 HGB), GuV (§275 HGB), Anlagenspiegel
       (§284 Abs. 3 HGB) und – falls vorhanden – die geerdeten Anhang-Sections.
       Kernfeature: klickbares Drill-down je Position entlang der
       Rückverfolgbarkeit Position → Taxonomie-Konzept → Konto → Saldenliste-Saldo.
Status: ✅ 2026-06-23
Abhängigkeiten: keine (reine Standardbibliothek). Eingaben sind das Datenmodell
       und optional die Saldenliste-Konten (Konto → (bez, gj, vj)) für die
       Konto-Ebene im Drill-down.
Datenagnostisch (§2.1): KEINE Kontonummern/Mandant im Code. Alles, was angezeigt
       wird, kommt aus dem übergebenen Datenmodell bzw. den Konten. Der Renderer
       LIEST nur und rechnet NICHTS nach (eiserner Grundsatz §2.7): er übernimmt
       die Werte des Modells unverändert, erfindet keine Zahl.
Letzte Änderung: 2026-06-23
"""
import html
from datetime import date

# Einrückung je Gliederungsebene (px). ebene 0 = Summe, höhere = tiefer im Baum.
_INDENT_PX = 18


def _eur(x):
    """Float -> deutsches Währungsformat '1.700.000,00' (Minus als echtes −)."""
    if x is None:
        return ""
    neg = x < 0
    s = f"{abs(float(x)):,.2f}"          # 1,700,000.00 (US)
    s = s.replace(",", "\0").replace(".", ",").replace("\0", ".")  # -> 1.700.000,00
    return ("−" if neg else "") + s


def _esc(s):
    return html.escape(str(s), quote=True)


def _is_konto_quelle(q):
    """Echte Konten sind reine Ziffernfolgen; '(abgeleitet aus GuV)' o. Ä. nicht."""
    return q and str(q).strip().isdigit()


# --------------------------------------------------------------------------- #
# Drill-down-Detail (Provenienz einer Position)
# --------------------------------------------------------------------------- #
def _provenienz_html(pos, konten, spalten):
    """Detail-Panel: Taxonomie-Konzept + die speisenden Konten mit Saldenliste-Saldo.
    konten: Konto -> (bezeichnung, saldo_gj, saldo_vj) oder None."""
    konzept = pos.get("konzept")
    quelle = pos.get("quelle") or []
    teile = []

    if konzept:
        teile.append(
            f'<div class="prov-konzept">Taxonomie-Anker (de-gaap-ci): '
            f'<code>{_esc(konzept)}</code></div>'
        )

    konto_quellen = [q for q in quelle if _is_konto_quelle(q)]
    abgeleitet = [q for q in quelle if not _is_konto_quelle(q)]

    if konto_quellen:
        zeilen = []
        for k in konto_quellen:
            bez, gj, vj = ("", None, None)
            if konten and k in konten:
                bez, gj, vj = konten[k]
            zeilen.append(
                f'<tr><td class="kn">{_esc(k)}</td>'
                f'<td class="kb">{_esc(bez)}</td>'
                f'<td class="num">{_eur(gj)}</td>'
                f'<td class="num">{_eur(vj)}</td></tr>'
            )
        teile.append(
            '<table class="prov-konten"><thead><tr>'
            '<th>Konto</th><th>Bezeichnung (Saldenliste)</th>'
            '<th class="num">Saldo GJ</th><th class="num">Saldo VJ</th>'
            '</tr></thead><tbody>' + "".join(zeilen) + '</tbody></table>'
        )

    if abgeleitet:
        for a in abgeleitet:
            teile.append(
                f'<div class="prov-note">Speist sich aus: {_esc(a)} '
                f'(keine direkte Saldenlisten-Quelle – aus der Mechanik der '
                f'Taxonomie abgeleitet).</div>'
            )

    if not teile:
        teile.append('<div class="prov-note">Keine Quellangabe.</div>')

    return (f'<tr class="detail"><td colspan="{spalten}">'
            f'<div class="prov">' + "".join(teile) + '</div></td></tr>')


# --------------------------------------------------------------------------- #
# Bilanz / GuV (Positionsliste mit ebene, wert_gj, wert_vj, quelle, konzept)
# --------------------------------------------------------------------------- #
def _positionsliste(titel, norm, positionen, konten, summe=None):
    rows = []
    for pos in positionen:
        ebene = int(pos.get("ebene", 0))
        pad = ebene * _INDENT_PX
        cls = f"lvl{min(ebene, 6)}"
        hat_drill = bool(pos.get("quelle") or pos.get("konzept"))
        drill_cls = " drill" if hat_drill else ""
        caret = '<span class="caret">▸</span>' if hat_drill else '<span class="caret-x"></span>'
        rows.append(
            f'<tr class="{cls}{drill_cls}">'
            f'<td class="pos" style="padding-left:{12 + pad}px">{caret}{_esc(pos.get("label",""))}</td>'
            f'<td class="num">{_eur(pos.get("wert_gj"))}</td>'
            f'<td class="num">{_eur(pos.get("wert_vj"))}</td>'
            f'</tr>'
        )
        if hat_drill:
            rows.append(_provenienz_html(pos, konten, 3))

    fuss = ""
    if summe:
        fuss = (
            '<tfoot><tr class="summe">'
            f'<td class="pos">{_esc(summe[0])}</td>'
            f'<td class="num">{_eur(summe[1])}</td>'
            f'<td class="num">{_eur(summe[2])}</td>'
            '</tr></tfoot>'
        )

    return (
        f'<section><h2>{_esc(titel)} <span class="norm">{_esc(norm)}</span></h2>'
        '<table class="rt"><thead><tr>'
        '<th class="pos">Position</th>'
        '<th class="num">Geschäftsjahr</th><th class="num">Vorjahr</th>'
        '</tr></thead><tbody>' + "".join(rows) + '</tbody>' + fuss + '</table></section>'
    )


# --------------------------------------------------------------------------- #
# Anlagenspiegel (Bruttomethode, §284 Abs. 3)
# --------------------------------------------------------------------------- #
_ASP_SPALTEN = [
    ("ahk_anf", "AHK Anfang"), ("zugang", "Zugang"), ("abgang_ahk", "Abgang"),
    ("umbuchung", "Umbuchung"), ("ahk_ende", "AHK Ende"),
    ("kumafa_anf", "Kum. AfA Anf."), ("afa_jahr", "AfA Jahr"),
    ("abgang_afa", "Abgang AfA"), ("kumafa_ende", "Kum. AfA Ende"),
    ("bw_gj", "Buchwert GJ"), ("bw_vj", "Buchwert VJ"),
]


def _anlagenspiegel(asp):
    if not asp:
        return ""
    kopf = "".join(f'<th class="num">{_esc(t)}</th>' for _, t in _ASP_SPALTEN)
    rows = []
    for pos in asp.get("positionen", []):
        ebene = int(pos.get("ebene", 0))
        ist_konto = pos.get("konto") is not None
        cls = "konto" if ist_konto else f"lvl{min(ebene, 6)}"
        pad = ebene * _INDENT_PX
        label = pos.get("label", "")
        if ist_konto:
            zusatz = []
            if pos.get("methode"):
                zusatz.append(pos["methode"])
            if pos.get("nd"):
                zusatz.append(f'ND {pos["nd"]}')
            if zusatz:
                label += f' <span class="meta">({_esc(" · ".join(zusatz))})</span>'
            label = f'{_esc(pos.get("konto"))} · ' + label
        else:
            label = _esc(label)
        zellen = "".join(f'<td class="num">{_eur(pos.get(k))}</td>' for k, _ in _ASP_SPALTEN)
        rows.append(
            f'<tr class="{cls}"><td class="pos" style="padding-left:{12+pad}px">{label}</td>{zellen}</tr>'
        )

    s = asp.get("summe")
    fuss = ""
    if s:
        zellen = "".join(f'<td class="num">{_eur(s.get(k))}</td>' for k, _ in _ASP_SPALTEN)
        fuss = f'<tfoot><tr class="summe"><td class="pos">Summe Anlagevermögen</td>{zellen}</tr></tfoot>'

    hinweise = ""
    for h in asp.get("hinweise", []):
        hinweise += (
            f'<div class="hinweis hinweis-{_esc(h.get("typ","")).lower()}">'
            f'<b>Hinweis ({_esc(h.get("typ",""))}) – {_esc(h.get("gruppe",""))}:</b> '
            f'{_esc(h.get("hinweis",""))}</div>'
        )

    rc = asp.get("reconciliation")
    abst = ""
    if rc:
        ok = rc.get("abgestimmt")
        abst = (
            f'<div class="recon {"ok" if ok else "bad"}">'
            f'{"✓" if ok else "✗"} Reconciliation: Σ AfA Jahr {_eur(rc.get("afa_jahr"))} € '
            f'= AfA-Aufwand Saldenliste {_eur(rc.get("afa_aufwand_saldenliste"))} €; '
            f'Buchwert Ende {_eur(rc.get("bw_gj"))} € = Bilanz Sachanlagen.</div>'
        )

    return (
        '<section><h2>Anlagenspiegel <span class="norm">§ 284 Abs. 3 HGB (Bruttomethode)</span></h2>'
        '<div class="scroll"><table class="rt asp"><thead><tr>'
        f'<th class="pos">Anlagegut</th>{kopf}</tr></thead>'
        '<tbody>' + "".join(rows) + '</tbody>' + fuss + '</table></div>'
        + hinweise + abst + '</section>'
    )


# --------------------------------------------------------------------------- #
# Anhang (geerdete Sections aus output/**/anhang/*.json)
# --------------------------------------------------------------------------- #
def _anhang(sections):
    if not sections:
        return ""
    bloecke = []
    for sec in sections:
        norm = ", ".join(sec.get("norm_refs", []))
        titel = sec.get("section_id", "").replace("_", " ").title()
        prosa = []
        belege = []
        for blk in sec.get("blocks", []):
            if blk.get("typ") == "prosa" and blk.get("text"):
                prosa.append(f'<p>{_esc(blk["text"])}</p>')
            for c in blk.get("claims", []):
                q = c.get("quelle", {})
                belege.append(
                    f'<tr><td>{_esc(c.get("aussage",""))}</td>'
                    f'<td>{_esc(c.get("wert",""))}</td>'
                    f'<td><code>{_esc(q.get("art",""))}: {_esc(q.get("pfad",""))}</code></td></tr>'
                )
        val = sec.get("_validierung", {})
        badge = ""
        if val.get("phase3") == "ok":
            badge = (f'<span class="vbadge ok">✓ geerdet · {val.get("claims_geprueft","?")} '
                     f'Claims · 0 Fehler</span>')
        beleg_tab = ""
        if belege:
            beleg_tab = (
                '<details class="belege"><summary>Belege / Grounding '
                f'({len(belege)} Claims gegen die Wahrheit geprüft)</summary>'
                '<table class="rt"><thead><tr><th>Aussage</th><th>Wert</th>'
                '<th>Quelle (Pfad im Datenmodell / Sachverhalt)</th></tr></thead><tbody>'
                + "".join(belege) + '</tbody></table></details>'
            )
        bloecke.append(
            f'<div class="anhang-sec"><h3>{_esc(titel)} '
            f'<span class="norm">{_esc(norm)}</span> {badge}</h3>'
            + "".join(prosa) + beleg_tab + '</div>'
        )
    return ('<section><h2>Anhang <span class="norm">§§ 284 / 285 HGB</span></h2>'
            + "".join(bloecke) + '</section>')


# --------------------------------------------------------------------------- #
# Gesamt-Dokument
# --------------------------------------------------------------------------- #
_CSS = """
:root{--green:#1a7f37;--greenbg:#e6f4ea;--red:#cf222e;--redbg:#ffebe9;--grey:#57606a;
       --line:#d0d7de;--ink:#1f2328;--accent:#0969da;--accentbg:#ddf4ff;}
*{box-sizing:border-box;}
body{font-family:-apple-system,"Segoe UI",system-ui,sans-serif;margin:0;
     padding:24px 32px 80px;color:var(--ink);max-width:1100px;}
h1{font-size:24px;margin:0 0 2px;}
.sub{color:var(--grey);margin:0 0 4px;font-size:14px;}
.bar{position:sticky;top:0;background:#fff;padding:12px 0;border-bottom:1px solid var(--line);
     display:flex;align-items:center;gap:10px;flex-wrap:wrap;z-index:5;margin-bottom:8px;}
.pill{font-size:12.5px;padding:3px 10px;border-radius:20px;border:1px solid var(--line);
      background:#f6f8fa;color:var(--grey);}
.pill.ok{background:var(--greenbg);color:var(--green);border-color:#a6e0b8;}
button{font:inherit;padding:5px 12px;border:1px solid var(--line);background:#f6f8fa;
       border-radius:6px;cursor:pointer;}
button:hover{background:#eef1f4;}
section{margin:26px 0;}
h2{font-size:16px;margin:0 0 8px;border-bottom:1px solid var(--line);padding-bottom:5px;}
h3{font-size:14.5px;margin:18px 0 6px;}
.norm{font-weight:400;color:var(--grey);font-size:12.5px;}
table.rt{border-collapse:collapse;width:100%;font-size:13.5px;}
table.rt th,table.rt td{padding:5px 10px;border-bottom:1px solid #eaeef2;text-align:left;}
table.rt th{color:var(--grey);font-weight:600;font-size:12px;border-bottom:1px solid var(--line);
            white-space:nowrap;}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;}
td.pos{position:relative;}
tr.lvl0>td{font-weight:700;}
tr.lvl1>td{font-weight:600;}
tr.summe td{font-weight:700;border-top:2px solid var(--ink);border-bottom:none;background:#f6f8fa;}
tr.drill{cursor:pointer;}
tr.drill:hover>td{background:var(--accentbg);}
.caret{display:inline-block;width:14px;color:var(--accent);transition:transform .12s;font-size:11px;}
.caret-x{display:inline-block;width:14px;}
tr.exp .caret{transform:rotate(90deg);}
tr.detail{display:none;}
tr.detail.open{display:table-row;}
tr.detail>td{background:#fbfcfd;padding:0;border-bottom:1px solid #eaeef2;}
.prov{padding:10px 16px 12px 40px;}
.prov-konzept{font-size:12.5px;color:var(--grey);margin-bottom:8px;}
.prov-konzept code,.belege code,.anhang-sec code{font-family:"Cascadia Code",Consolas,monospace;
     font-size:12px;background:#eef1f4;padding:1px 5px;border-radius:4px;color:#24292f;}
table.prov-konten{border-collapse:collapse;font-size:12.5px;background:#fff;}
table.prov-konten th,table.prov-konten td{padding:3px 10px;border:1px solid var(--line);}
table.prov-konten td.kn{font-family:Consolas,monospace;}
.prov-note{font-size:12.5px;color:var(--grey);font-style:italic;margin-top:4px;}
.meta{color:var(--grey);font-weight:400;font-size:12px;}
.scroll{overflow-x:auto;}
table.asp{font-size:12px;}table.asp td.pos{white-space:nowrap;}
tr.konto>td{color:var(--grey);}
.hinweis{margin:10px 0;padding:8px 12px;border-radius:6px;font-size:13px;
         background:#fff8e6;border:1px solid #f0d58a;}
.recon{margin:10px 0;padding:7px 12px;border-radius:6px;font-size:13px;}
.recon.ok{background:var(--greenbg);color:var(--green);border:1px solid #a6e0b8;}
.recon.bad{background:var(--redbg);color:var(--red);border:1px solid #f0b1b1;}
.anhang-sec p{font-size:13.5px;line-height:1.55;margin:6px 0;}
.vbadge.ok{font-size:11.5px;color:var(--green);background:var(--greenbg);border:1px solid #a6e0b8;
           border-radius:20px;padding:2px 9px;font-weight:600;}
details.belege{margin:6px 0 10px;}
details.belege summary{cursor:pointer;font-size:12.5px;color:var(--accent);}
footer{margin-top:40px;padding-top:14px;border-top:1px solid var(--line);
       color:var(--grey);font-size:12px;}
"""

_JS = """
(function(){
  function setAll(open){
    document.querySelectorAll('tr.detail').forEach(function(d){d.classList.toggle('open',open);});
    document.querySelectorAll('tr.drill').forEach(function(r){r.classList.toggle('exp',open);});
  }
  document.querySelectorAll('tr.drill').forEach(function(r){
    r.addEventListener('click',function(){
      var d=r.nextElementSibling;
      if(!d||!d.classList.contains('detail'))return;
      var open=d.classList.toggle('open');
      r.classList.toggle('exp',open);
    });
  });
  var ea=document.getElementById('expandAll'), ca=document.getElementById('collapseAll');
  if(ea)ea.addEventListener('click',function(){setAll(true);});
  if(ca)ca.addEventListener('click',function(){setAll(false);});
})();
"""


def render_html(datenmodell, konten=None, anhang_sections=None,
                titel=None, stichtag=None):
    """Erzeugt das eigenständige HTML-Dokument als String (kein Plattenschreiben).

    datenmodell: Rückgabe von jahresabschluss.generate().
    konten:      Konto -> (bezeichnung, saldo_gj, saldo_vj) für die Konto-Ebene
                 im Drill-down (optional; aus read_saldenliste()).
    anhang_sections: Liste geerdeter Anhang-Section-Dicts (optional).
    titel/stichtag: rein kosmetische Kopfangaben (kommen NICHT aus den Zahlen,
                 daher als Parameter – der Renderer rechnet nichts nach).
    """
    bilanz = datenmodell.get("bilanz", {})
    guv = datenmodell.get("guv", {})
    meta = datenmodell.get("metadata", {})
    asp = datenmodell.get("anlagenspiegel")

    titel = titel or "Jahresabschluss"
    untertitel = "HGB-Jahresabschluss"
    if stichtag:
        untertitel += f" zum {stichtag}"

    # Statuspillen aus der metadata (die harten Checks der Engine).
    probe_ok = (round(meta.get("bilanzprobe_gj", 1), 2) == 0.0
                and round(meta.get("bilanzprobe_vj", 1), 2) == 0.0)
    jue_ok = bool(meta.get("jue_abgestimmt"))
    pills = [
        (f'Bilanzprobe {_eur(meta.get("bilanzprobe_gj"))} € / '
         f'{_eur(meta.get("bilanzprobe_vj"))} €', probe_ok),
        ('JÜ aus GuV = Bilanz A.V', jue_ok),
        (f'Taxonomie {meta.get("taxonomie","")}', True),
        (f'Quelle: {meta.get("quelle","")}', True),
    ]
    pill_html = "".join(
        f'<span class="pill{" ok" if ok else ""}">{_esc(t)}</span>' for t, ok in pills
    )

    teile = [
        _positionsliste(
            "Bilanz – Aktiva", "§ 266 Abs. 2 HGB", bilanz.get("aktiva", []), konten,
            summe=("Summe Aktiva", bilanz.get("summe_aktiva_gj"), bilanz.get("summe_aktiva_vj")),
        ),
        _positionsliste(
            "Bilanz – Passiva", "§ 266 Abs. 3 HGB", bilanz.get("passiva", []), konten,
            summe=("Summe Passiva", bilanz.get("summe_passiva_gj"), bilanz.get("summe_passiva_vj")),
        ),
        _positionsliste(
            "Gewinn- und Verlustrechnung", "§ 275 Abs. 2 HGB (Gesamtkostenverfahren)",
            guv.get("positionen", []), konten,
            summe=("Jahresüberschuss", guv.get("jahresueberschuss_gj"),
                   guv.get("jahresueberschuss_vj")),
        ),
        _anlagenspiegel(asp),
        _anhang(anhang_sections),
    ]

    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(titel)}</title>
<style>{_CSS}</style></head>
<body>
<h1>{_esc(titel)}</h1>
<p class="sub">{_esc(untertitel)} · jede Position ist <b>klickbar</b> → Rückverfolgung
   Position → Taxonomie-Konzept → Konto → Saldenliste-Saldo.</p>
<div class="bar">
  {pill_html}
  <span style="flex:1"></span>
  <button id="expandAll">Alles aufklappen</button>
  <button id="collapseAll">Zuklappen</button>
</div>
{"".join(teile)}
<footer>
  Generiert aus dem geerdeten Datenmodell ({_esc(meta.get("quelle",""))}) am
  {date.today().strftime("%d.%m.%Y")}. Eiserner Grundsatz: alle Werte leiten sich
  aus der Saldenliste ab; dieser Renderer liest nur und rechnet nichts nach.
</footer>
<script>{_JS}</script>
</body></html>"""
