"""
renderer_pdf.py
Zweck: Print-Renderer — nimmt das geerdete Datenmodell (aus generate()) und erzeugt
       ein professionelles PDF des HGB-Jahresabschlusses: Bilanz (§266), GuV (§275),
       Anlagenspiegel (§284 Abs. 3) und – falls vorhanden – die geerdeten
       Anhang-Sections. Das interaktive Drill-down des HTML-Renderers wird im PDF
       (das flach ist) durch einen Rückverfolgbarkeits-Anhang ersetzt: je Position
       Taxonomie-Konzept + speisende Konten mit Saldenliste-Saldo.
Hinweis Scope: sauberes, druckfähiges PDF. ECHTE PDF/A-3-Archivkonformität
       (eingebettetes XBRL, XMP/ICC) ist hier NICHT zertifiziert — bewusster
       Default-Scope, als Ausblick dokumentiert.
Status: ✅ 2026-06-23
Abhängigkeiten: reportlab (pure-Python). Eingaben wie beim HTML-Renderer.
Datenagnostisch (§2.1): KEINE Kontonummern/Mandant im Code. Eiserner Grundsatz
       (§2.7): übernimmt Modellwerte unverändert, rechnet nichts nach.
Letzte Änderung: 2026-06-23
"""
from datetime import date
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
)

# Farbpalette (an den HTML-Renderer angelehnt).
_GREEN = colors.HexColor("#1a7f37")
_GREY = colors.HexColor("#57606a")
_LINE = colors.HexColor("#d0d7de")
_INK = colors.HexColor("#1f2328")
_ZEBRA = colors.HexColor("#f6f8fa")

_INDENT_MM = 4  # Einrückung je Gliederungsebene


def _eur(x):
    """Float -> '1.700.000,00' (ASCII-Minus '-' wegen PDF-Standardfont-Glyphen)."""
    if x is None:
        return ""
    neg = x < 0
    s = f"{abs(float(x)):,.2f}".replace(",", "\0").replace(".", ",").replace("\0", ".")
    return ("-" if neg else "") + s


def _is_konto_quelle(q):
    return q and str(q).strip().isdigit()


def _styles():
    ss = getSampleStyleSheet()
    out = {
        "h1": ParagraphStyle("h1", parent=ss["Title"], fontName="Helvetica-Bold",
                             fontSize=17, textColor=_INK, spaceAfter=2, alignment=0),
        "sub": ParagraphStyle("sub", parent=ss["Normal"], fontName="Helvetica",
                              fontSize=9, textColor=_GREY, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold",
                             fontSize=12, textColor=_INK, spaceBefore=14, spaceAfter=4),
        "norm": ParagraphStyle("norm", parent=ss["Normal"], fontName="Helvetica",
                               fontSize=8, textColor=_GREY, spaceAfter=4),
        "body": ParagraphStyle("body", parent=ss["Normal"], fontName="Helvetica",
                               fontSize=9.5, leading=14, textColor=_INK, spaceAfter=4),
        "note": ParagraphStyle("note", parent=ss["Normal"], fontName="Helvetica-Oblique",
                               fontSize=8, textColor=_GREY, spaceAfter=2),
        "cell": ParagraphStyle("cell", parent=ss["Normal"], fontName="Helvetica",
                               fontSize=9, leading=11, textColor=_INK),
    }
    return out


def _pos_paragraph(label, ebene, S, bold=False):
    name = "Helvetica-Bold" if (bold or ebene <= 1) else "Helvetica"
    st = ParagraphStyle("p", parent=S["cell"], fontName=name,
                        leftIndent=ebene * _INDENT_MM * mm)
    return Paragraph(label, st)


def _num(x, S, bold=False):
    name = "Helvetica-Bold" if bold else "Helvetica"
    st = ParagraphStyle("n", parent=S["cell"], fontName=name, alignment=TA_RIGHT)
    return Paragraph(_eur(x), st)


# --------------------------------------------------------------------------- #
# Bilanz / GuV als Tabelle
# --------------------------------------------------------------------------- #
def _positionstabelle(positionen, S, avail, summe=None):
    col = [avail - 70 * mm, 35 * mm, 35 * mm]
    data = [[Paragraph("<b>Position</b>", S["cell"]),
             Paragraph('<para align="right"><b>Geschäftsjahr</b></para>', S["cell"]),
             Paragraph('<para align="right"><b>Vorjahr</b></para>', S["cell"])]]
    style = [
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, _LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for pos in positionen:
        ebene = int(pos.get("ebene", 0))
        r = len(data)
        data.append([
            _pos_paragraph(pos.get("label", ""), ebene, S),
            _num(pos.get("wert_gj"), S),
            _num(pos.get("wert_vj"), S),
        ])
        if r % 2 == 0:
            style.append(("BACKGROUND", (0, r), (-1, r), _ZEBRA))
    if summe:
        r = len(data)
        data.append([
            Paragraph(f"<b>{summe[0]}</b>", S["cell"]),
            _num(summe[1], S, bold=True), _num(summe[2], S, bold=True),
        ])
        style.append(("LINEABOVE", (0, r), (-1, r), 1.0, _INK))
        style.append(("LINEBELOW", (0, r), (-1, r), 0.4, _LINE))
    t = Table(data, colWidths=col, hAlign="LEFT")
    t.setStyle(TableStyle(style))
    return t


# --------------------------------------------------------------------------- #
# Anlagenspiegel (11 Spalten -> kompakt, passt auf A4 hoch mit kleiner Schrift)
# --------------------------------------------------------------------------- #
_ASP_SPALTEN = [
    ("ahk_anf", "AHK\nAnf."), ("zugang", "Zugang"), ("abgang_ahk", "Abgang"),
    ("umbuchung", "Umb."), ("ahk_ende", "AHK\nEnde"),
    ("kumafa_anf", "Σ AfA\nAnf."), ("afa_jahr", "AfA\nJahr"),
    ("abgang_afa", "Abg.\nAfA"), ("kumafa_ende", "Σ AfA\nEnde"),
    ("bw_gj", "BW GJ"), ("bw_vj", "BW VJ"),
]


def _anlagenspiegel_flow(asp, S, avail):
    if not asp:
        return []
    sc = ParagraphStyle("sc", parent=S["cell"], fontSize=7.2, leading=9)
    scr = ParagraphStyle("scr", parent=sc, alignment=TA_RIGHT)
    sch = ParagraphStyle("sch", parent=scr, fontName="Helvetica-Bold")
    numw = 18.0 * mm
    col = [avail - 11 * numw] + [numw] * 11

    head = [Paragraph("<b>Anlagegut</b>", sc)] + [
        Paragraph(t.replace("\n", "<br/>"), sch) for _, t in _ASP_SPALTEN]
    data = [head]
    style = [
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, _LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("LEFTPADDING", (1, 0), (-1, -1), 2.5),
        ("RIGHTPADDING", (1, 0), (-1, -1), 2.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for pos in asp.get("positionen", []):
        ebene = int(pos.get("ebene", 0))
        ist_konto = pos.get("konto") is not None
        label = pos.get("label", "")
        if ist_konto:
            zus = []
            if pos.get("methode"):
                zus.append(pos["methode"])
            if pos.get("nd"):
                zus.append(f'ND {pos["nd"]}')
            label = f'{pos.get("konto")} · {label}' + (f' ({" · ".join(zus)})' if zus else "")
            ps = ParagraphStyle("k", parent=sc, leftIndent=ebene * 3 * mm, textColor=_GREY)
        else:
            ps = ParagraphStyle("g", parent=sc, leftIndent=ebene * 3 * mm,
                                fontName="Helvetica-Bold")
        row = [Paragraph(label, ps)] + [
            Paragraph(_eur(pos.get(k)), scr) for k, _ in _ASP_SPALTEN]
        data.append(row)

    s = asp.get("summe")
    if s:
        r = len(data)
        row = [Paragraph("<b>Summe Anlagevermögen</b>", sc)] + [
            Paragraph(f"<b>{_eur(s.get(k))}</b>", scr) for k, _ in _ASP_SPALTEN]
        data.append(row)
        style.append(("LINEABOVE", (0, r), (-1, r), 0.8, _INK))

    t = Table(data, colWidths=col, hAlign="LEFT", repeatRows=1)
    t.setStyle(TableStyle(style))

    flow = [Paragraph("Anlagenspiegel", S["h2"]),
            Paragraph("§ 284 Abs. 3 HGB · Bruttomethode (Beträge in EUR)", S["norm"]),
            t]
    for h in asp.get("hinweise", []):
        flow.append(Spacer(1, 4))
        flow.append(Paragraph(
            f'<b>Hinweis ({h.get("typ","")}) – {h.get("gruppe","")}:</b> {h.get("hinweis","")}',
            S["note"]))
    rc = asp.get("reconciliation")
    if rc:
        ok = rc.get("abgestimmt")
        flow.append(Spacer(1, 4))
        flow.append(Paragraph(
            f'{"✓" if ok else "✗"} Reconciliation: Σ AfA Jahr {_eur(rc.get("afa_jahr"))} EUR '
            f'= AfA-Aufwand Saldenliste {_eur(rc.get("afa_aufwand_saldenliste"))} EUR; '
            f'Buchwert Ende {_eur(rc.get("bw_gj"))} EUR = Bilanz Sachanlagen.', S["note"]))
    return flow


# --------------------------------------------------------------------------- #
# Anhang + Rückverfolgbarkeits-Appendix
# --------------------------------------------------------------------------- #
_SHOWCASE_BANNER = (
    "Hinweis: Dieser Anhang bildet bewusst den vollständigen, nach § 288 Abs. 1 HGB "
    "für eine kleine Kapitalgesellschaft NICHT befreiten Pflichtangaben-Katalog ab — "
    "über das für eine kleine GmbH übliche Mindestmaß hinaus, einschließlich rechtlich "
    "einschlägiger, aber im konkreten Sachverhalt nicht erfüllter Tatbestände "
    "(\"nicht einschlägig\"). Dies dient dem Nachweis, dass die KI keine Sachverhalte "
    "erfindet, sondern ehrlich Fehlanzeige meldet."
)


def _anhang_flow(sections, S, sections_config=None):
    if not sections:
        return []
    sections_config = sections_config or {}
    zeigt_showcase = any(
        sections_config.get(sec.get("section_id"), {}).get("showcase") for sec in sections)
    flow = [PageBreak(), Paragraph("Anhang", S["h2"]),
            Paragraph("§§ 284 / 285 HGB", S["norm"])]
    if zeigt_showcase:
        flow.append(Paragraph(_SHOWCASE_BANNER, S["note"]))
    for sec in sections:
        titel = sec.get("section_id", "").replace("_", " ").title()
        norm = ", ".join(sec.get("norm_refs", []))
        tag = (' <font size=7 color="#57606a">[Showcase — über Mindestangabe hinaus]</font>'
               if sections_config.get(sec.get("section_id"), {}).get("showcase") else "")
        flow.append(Paragraph(f"{titel} <font size=8 color='#57606a'>{norm}</font>{tag}", S["h2"]))
        for blk in sec.get("blocks", []):
            if blk.get("typ") == "prosa" and blk.get("text"):
                flow.append(Paragraph(blk["text"], S["body"]))
        val = sec.get("_validierung", {})
        if val.get("phase3") == "ok":
            flow.append(Paragraph(
                f'✓ geerdet · {val.get("claims_geprueft","?")} Claims gegen die Wahrheit '
                f'geprüft · 0 Fehler', S["note"]))
    return flow


# --------------------------------------------------------------------------- #
# Unterschrift + Feststellungsvermerk — jeder reale Unternehmensregister-        #
# Auszug hat das (32/32 Geschäftsführer-Nennung, 31/32 Feststellungsvermerk,   #
# 31/32 Unterschriftsblock — s. docs/local/ANHANG_REALWELT_ABGLEICH.md).       #
# --------------------------------------------------------------------------- #
def _unterschrift_flow(geschaeftsfuehrer, feststellung, S):
    if not geschaeftsfuehrer:
        return []
    feststellung = feststellung or {}
    flow = [Spacer(1, 14), Paragraph("Unterschrift der Geschäftsführung", S["h2"])]
    kopf = ", ".join(x for x in (feststellung.get("ort"), feststellung.get("datum")) if x)
    if kopf:
        flow.append(Paragraph(kopf, S["body"]))
    for eintrag in geschaeftsfuehrer:
        name = eintrag.get("name") if isinstance(eintrag, dict) else eintrag
        titel = eintrag.get("titel", "Geschäftsführer") if isinstance(eintrag, dict) else "Geschäftsführer"
        flow.append(Spacer(1, 10))
        flow.append(Paragraph("_" * 40, S["body"]))
        flow.append(Paragraph(f"{name}, {titel}", S["note"]))
    flow.append(Spacer(1, 14))
    flow.append(Paragraph("sonstige Berichtsbestandteile", S["h2"]))
    if feststellung.get("datum"):
        flow.append(Paragraph("Angaben zur Feststellung:", S["norm"]))
        flow.append(Paragraph(
            f"Der Jahresabschluss wurde am {feststellung['datum']} festgestellt.", S["body"]))
    return flow


def _rueckverfolgbarkeit_flow(positionen_gruppen, konten, S, avail):
    """Print-Analog zum HTML-Drill-down: je Position Konzept + speisende Konten."""
    flow = [PageBreak(), Paragraph("Rückverfolgbarkeit", S["h2"]),
            Paragraph("Nachweis je Position: Taxonomie-Konzept (de-gaap-ci) und die "
                      "speisenden Konten der Saldenliste. Die Werte oben sind hierauf "
                      "vollständig zurückführbar.", S["norm"])]
    sc = ParagraphStyle("rc", parent=S["cell"], fontSize=8, leading=10)
    scm = ParagraphStyle("rcm", parent=sc, fontName="Courier", fontSize=7.5)
    for gruppe, positionen in positionen_gruppen:
        flow.append(Spacer(1, 6))
        flow.append(Paragraph(f"<b>{gruppe}</b>", sc))
        data = [[Paragraph("<b>Position</b>", sc), Paragraph("<b>Konzept</b>", sc),
                 Paragraph("<b>Konten</b>", sc)]]
        for pos in positionen:
            quelle = pos.get("quelle") or []
            konto_q = [q for q in quelle if _is_konto_quelle(q)]
            abgl = [q for q in quelle if not _is_konto_quelle(q)]
            kt = []
            for k in konto_q:
                bez = konten[k][0] if (konten and k in konten) else ""
                kt.append(f"{k} {bez}".strip())
            kt += abgl
            data.append([
                Paragraph(pos.get("label", ""), sc),
                Paragraph(pos.get("konzept", "") or "", scm),
                Paragraph("<br/>".join(kt) if kt else "—", sc),
            ])
        t = Table(data, colWidths=[avail * 0.34, avail * 0.34, avail * 0.32], hAlign="LEFT")
        t.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, _LINE),
            ("LINEBELOW", (0, 1), (-1, -1), 0.3, _LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        flow.append(t)
    return flow


# --------------------------------------------------------------------------- #
# Gesamt-Dokument
# --------------------------------------------------------------------------- #
def render_pdf(datenmodell, konten=None, anhang_sections=None,
               titel=None, stichtag=None, anhang_sections_config=None,
               geschaeftsfuehrer=None, feststellung=None):
    """Erzeugt das PDF als bytes (kein Plattenschreiben — der Aufrufer speichert).

    Argumente analog renderer_html.render_html. titel/stichtag sind kosmetisch
    (kommen nicht aus den Zahlen). anhang_sections_config ist optional ein
    {section_id: config_row}-Lookup aus anhang_sections.json — steuert nur die
    Showcase-Kennzeichnung (§13 ANHANG.md), keine LLM-Prompt-Änderung.
    geschaeftsfuehrer: Liste von Namen (str) oder {"name":..., "titel":...}-Dicts.
    feststellung: {"datum":..., "ort":...} — beide kosmetisch, kommen aus dem
    Sachverhaltsblatt, nicht aus dem Datenmodell.
    """
    bilanz = datenmodell.get("bilanz", {})
    guv = datenmodell.get("guv", {})
    meta = datenmodell.get("metadata", {})
    asp = datenmodell.get("anlagenspiegel")
    S = _styles()

    buf = BytesIO()
    margin = 16 * mm
    ls = landscape(A4)
    avail = A4[0] - 2 * margin              # Hochformat-Breite (Bilanz/GuV/Anhang)
    avail_ls = ls[0] - 2 * margin           # Querformat-Breite (Anlagenspiegel)

    titel = titel or "Jahresabschluss"
    kopf = "HGB-Jahresabschluss" + (f" zum {stichtag}" if stichtag else "")
    probe_ok = (round(meta.get("bilanzprobe_gj", 1), 2) == 0.0
                and round(meta.get("bilanzprobe_vj", 1), 2) == 0.0)
    status = (f"Bilanzprobe {_eur(meta.get('bilanzprobe_gj'))} / "
              f"{_eur(meta.get('bilanzprobe_vj'))} EUR"
              f"  ·  JÜ aus GuV = Bilanz A.V {'✓' if meta.get('jue_abgestimmt') else '✗'}"
              f"  ·  Taxonomie {meta.get('taxonomie','')}  ·  Quelle {meta.get('quelle','')}")

    flow = [
        Paragraph(titel, S["h1"]),
        Paragraph(kopf, S["sub"]),
        Paragraph(("<font color='%s'>%s</font>" %
                   ("#1a7f37" if probe_ok else "#cf222e", status)), S["norm"]),
        Spacer(1, 6),
        Paragraph("Bilanz – Aktiva", S["h2"]),
        Paragraph("§ 266 Abs. 2 HGB (Beträge in EUR)", S["norm"]),
        _positionstabelle(bilanz.get("aktiva", []), S, avail,
                          summe=("Summe Aktiva", bilanz.get("summe_aktiva_gj"),
                                 bilanz.get("summe_aktiva_vj"))),
        Paragraph("Bilanz – Passiva", S["h2"]),
        Paragraph("§ 266 Abs. 3 HGB (Beträge in EUR)", S["norm"]),
        _positionstabelle(bilanz.get("passiva", []), S, avail,
                          summe=("Summe Passiva", bilanz.get("summe_passiva_gj"),
                                 bilanz.get("summe_passiva_vj"))),
        PageBreak(),
        Paragraph("Gewinn- und Verlustrechnung", S["h2"]),
        Paragraph("§ 275 Abs. 2 HGB · Gesamtkostenverfahren (Beträge in EUR)", S["norm"]),
        _positionstabelle(guv.get("positionen", []), S, avail,
                          summe=("Jahresüberschuss", guv.get("jahresueberschuss_gj"),
                                 guv.get("jahresueberschuss_vj"))),
        Spacer(1, 10),
    ]
    if asp:
        flow += [NextPageTemplate("landscape"), PageBreak()]
        flow += _anlagenspiegel_flow(asp, S, avail_ls)
        flow += [NextPageTemplate("portrait")]
    flow += _anhang_flow(anhang_sections, S, sections_config=anhang_sections_config)
    flow += _unterschrift_flow(geschaeftsfuehrer, feststellung, S)
    flow += _rueckverfolgbarkeit_flow(
        [("Bilanz – Aktiva", bilanz.get("aktiva", [])),
         ("Bilanz – Passiva", bilanz.get("passiva", [])),
         ("Gewinn- und Verlustrechnung", guv.get("positionen", []))],
        konten, S, avail)

    def _footer(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(_GREY)
        breite = canvas._pagesize[0]
        canvas.drawString(margin, 8 * mm,
                          f"Generiert aus dem geerdeten Datenmodell ({meta.get('quelle','')}) "
                          f"am {date.today().strftime('%d.%m.%Y')} · eiserner Grundsatz: "
                          f"Werte aus der Saldenliste, nicht nachgerechnet.")
        canvas.drawRightString(breite - margin, 8 * mm, f"Seite {d.page}")
        canvas.restoreState()

    doc = BaseDocTemplate(
        buf, pagesize=A4, leftMargin=margin, rightMargin=margin,
        topMargin=14 * mm, bottomMargin=14 * mm,
        title=titel, author="8_AI_Accounting")
    doc.addPageTemplates([
        PageTemplate(id="portrait", pagesize=A4, onPage=_footer, frames=[
            Frame(margin, 14 * mm, A4[0] - 2 * margin, A4[1] - 28 * mm, id="p")]),
        PageTemplate(id="landscape", pagesize=ls, onPage=_footer, frames=[
            Frame(margin, 14 * mm, ls[0] - 2 * margin, ls[1] - 28 * mm, id="l")]),
    ])
    doc.build(flow)
    return buf.getvalue()
