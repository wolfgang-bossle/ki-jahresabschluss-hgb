"""
generate_fragebogen_docx.py
Zweck: Mandantenfragebogen (Word) für die Anhang-Sachverhalte, die NICHT aus der
       Saldenliste kommen. Klickbare Word-Kästchen (Content Controls), jede Frage mit
       sichtbarer Rechtsgrundlage, Ja/Nein punkt für punkt mit „Falls ja"-Zeile darunter.
       Bereits aus der Saldenliste ableitbare Angaben (GuV-Verfahren, Geschäftsjahr,
       Bilanzstichtag, Größenklasse) werden bewusst NICHT abgefragt.
Aufruf: python scripts/generate_fragebogen_docx.py
Status: ✅ 2026-07-03
Abhängigkeiten: python-docx
"""
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "output/fragebogen_sachverhalt.docx"
GREY = RGBColor(0x57, 0x60, 0x6A)
INK = RGBColor(0x1F, 0x23, 0x28)

STAMMDATEN = ["Firma", "Rechtsform", "Sitz", "Registergericht / Handelsregisternummer"]
GF = ["Name(n) der Geschäftsführung", "Datum der Feststellung des Jahresabschlusses",
      "Ort der Unterzeichnung"]
# Ja/Nein-Punkte: (Frage, Rechtsgrundlage, Feld-falls-ja | None)
ITEMS = [
    ("Forderungen gegenüber Gesellschaftern zum Bilanzstichtag?", "§ 42 Abs. 3 GmbHG", "Betrag"),
    ("Verbindlichkeiten gegenüber Gesellschaftern zum Bilanzstichtag?", "§ 42 Abs. 3 GmbHG", "Betrag"),
    ("Vorschüsse oder Kredite an die Geschäftsführung?", "§ 285 Nr. 9 Buchst. c HGB", "Betrag, Zinssatz, Bedingungen"),
    ("Besonderheiten bei der Gliederung von Bilanz oder GuV (z. B. Postenzusammenfassung)?", "§ 265 HGB", "Beschreibung unter G."),
    ("Bewertungsmethode gegenüber dem Vorjahr geändert?", "§ 284 Abs. 2 Nr. 2 HGB", "Beschreibung unter G."),
    ("Vorgänge von besonderer Bedeutung nach dem Bilanzstichtag?", "§ 285 Nr. 33 HGB", "Beschreibung unter G."),
    ("Nicht abschreibbarer Grund-und-Boden-Anteil in den Grundstücken?", "§ 284 Abs. 2 Nr. 1 HGB", "Betrag"),
    ("Entgeltlich erworbener Geschäfts-/Firmenwert (Goodwill) aktiviert?", "§ 285 Nr. 13 HGB", "Abschreibungsdauer in Jahren"),
    ("Einbeziehung in den Konzernabschluss eines Mutterunternehmens?", "§ 285 Nr. 14a HGB", "Name und Sitz des Mutterunternehmens"),
    ("Zum beizulegenden Zeitwert bewertete Finanzinstrumente / Derivate?", "§ 285 Nr. 20 HGB", "Art"),
    ("Bewertungseinheiten (Hedge-Accounting) gebildet?", "§ 254, § 285 Nr. 23 HGB", "Art"),
    ("Saldierung von Vermögen und Schulden (z. B. Pensions-Rückdeckung)?", "§ 246 Abs. 2, § 285 Nr. 25 HGB", "Beträge"),
    ("Außergewöhnliche Erträge oder Aufwendungen?", "§ 285 Nr. 31 HGB", "Betrag und Art"),
    ("Haftungsverhältnisse / Eventualverbindlichkeiten (Bürgschaften, Garantien)?", "§ 251, § 268 Abs. 7 HGB", "Art und Betrag"),
    ("Anlagenspiegel freiwillig beifügen?", "§ 284 Abs. 3 HGB", None),
]


def _el(tag, **attrs):
    e = OxmlElement(tag)
    for k, v in attrs.items():
        e.set(qn(k.replace("_", ":", 1)), v)
    return e


def _rule(par):
    pbdr = _el("w:pBdr")
    pbdr.append(_el("w:bottom", w_val="single", w_sz="6", w_space="2", w_color="1F2328"))
    par._p.get_or_add_pPr().append(pbdr)


def _shade(cell, hex_):
    cell._tc.get_or_add_tcPr().append(_el("w:shd", w_val="clear", w_fill=hex_))


def _checkbox(par, label):
    sdt, pr, cb = _el("w:sdt"), _el("w:sdtPr"), _el("w14:checkbox")
    cb.append(_el("w14:checked", w14_val="0"))
    cb.append(_el("w14:checkedState", w14_val="2612", w14_font="MS Gothic"))
    cb.append(_el("w14:uncheckedState", w14_val="2610", w14_font="MS Gothic"))
    pr.append(cb); sdt.append(pr)
    content, r, rpr = _el("w:sdtContent"), _el("w:r"), _el("w:rPr")
    rpr.append(_el("w:rFonts", w_ascii="MS Gothic", w_hAnsi="MS Gothic", w_eastAsia="MS Gothic"))
    t = _el("w:t"); t.text = "☐"
    r.append(rpr); r.append(t); content.append(r); sdt.append(content)
    par._p.append(sdt)
    par.add_run(" " + label + "  ").font.size = Pt(10)


def _heading(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(12), Pt(4)
    r = p.add_run(text)
    r.bold, r.font.size, r.font.color.rgb = True, Pt(11.5), INK
    _rule(p)


def _note(doc, text, size=8.5):
    r = doc.add_paragraph().add_run(text)
    r.font.size, r.font.color.rgb = Pt(size), GREY


def _headrow(table, texts):
    for c, txt in enumerate(texts):
        cell = table.rows[0].cells[c]
        run = cell.paragraphs[0].add_run(txt)
        run.bold, run.font.size, run.font.color.rgb = True, Pt(9), RGBColor(0xFF, 0xFF, 0xFF)
        _shade(cell, "1F2328")


def _fillin(doc, felder, w=(6.5, 10.5)):
    t = doc.add_table(rows=len(felder), cols=2)
    t.style = "Table Grid"
    for i, feld in enumerate(felder):
        t.rows[i].cells[0].paragraphs[0].add_run(feld).font.size = Pt(9.5)
        t.rows[i].cells[0].width, t.rows[i].cells[1].width = Cm(w[0]), Cm(w[1])


def _uline(doc, label, indent=0.0):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent, p.paragraph_format.space_after = Cm(indent), Pt(2)
    p.paragraph_format.tab_stops.add_tab_stop(Cm(15.5), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.LINES)
    r = p.add_run(label + "\t")
    r.font.size, r.italic, r.font.color.rgb = Pt(9), True, GREY


def _item(doc, nr, frage, norm, feld):
    p = doc.add_paragraph()
    p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(8), Pt(1)
    p.add_run(f"{nr}.  {frage}  ").font.size = Pt(10)
    rr = p.add_run(f"({norm})")
    rr.italic, rr.font.size, rr.font.color.rgb = True, Pt(8.5), GREY
    pc = doc.add_paragraph()
    pc.paragraph_format.left_indent, pc.paragraph_format.space_after = Cm(0.6), Pt(1)
    _checkbox(pc, "Nein"); _checkbox(pc, "Ja")
    if feld and not feld.startswith("Beschreibung"):
        _uline(doc, f"Falls ja — {feld}:", indent=0.6)
    elif feld:
        _note(doc, "    Falls ja: bitte unter G. erläutern.")


def build():
    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(10)
    for s in doc.sections:
        s.top_margin = s.bottom_margin = Cm(2); s.left_margin = s.right_margin = Cm(2.2)

    tp = doc.add_paragraph()
    tr = tp.add_run("Fragebogen zum Jahresabschluss — Ergänzende Angaben für den Anhang")
    tr.bold, tr.font.size = True, Pt(15)
    _rule(tp)
    _note(doc, "Die Zahlen entnehmen wir Ihrer Saldenliste (daraus ergeben sich auch "
               "Geschäftsjahr, Bilanzstichtag, GuV-Verfahren und Größenklasse). Für den Anhang "
               "(§§ 284–288 HGB) benötigen wir nur noch die folgenden, nicht aus Zahlen "
               "ableitbaren Angaben. Bitte Kästchen anklicken; bei „Ja“ die Zeile darunter "
               "ausfüllen, bei „Nein“ leer lassen. Die rechtssichere Formulierung übernehmen wir.",
          size=9.5)

    _heading(doc, "A. Angaben zur Gesellschaft")
    _fillin(doc, STAMMDATEN)
    _heading(doc, "B. Geschäftsführung und Feststellung")
    _fillin(doc, GF)

    _heading(doc, "C. Arbeitnehmer  (§ 285 Nr. 7 i. V. m. § 267 Abs. 5 HGB)")
    _note(doc, "Maßgeblich ist der Durchschnitt der an den vier Quartalsenden beschäftigten "
               "Arbeitnehmer (Summe ÷ 4) — den berechnen wir. Auszubildende bleiben außer Ansatz; "
               "die Vorjahreszahl übernehmen wir aus dem Vorjahresabschluss. Bitte nur die Stände "
               "eintragen.")
    at = doc.add_table(rows=2, cols=5)
    at.style = "Table Grid"
    _headrow(at, ["", "31.03.", "30.06.", "30.09.", "31.12."])
    at.rows[1].cells[0].paragraphs[0].add_run("Beschäftigte Arbeitnehmer\n(ohne Auszubildende)").font.size = Pt(9)
    _uline(doc, "Nachrichtlich — Zahl der Auszubildenden (nicht im Durchschnitt):")

    _heading(doc, "D. Verbindlichkeiten — Restlaufzeiten und Sicherheiten  (§ 285 Nr. 1 HGB)")
    _note(doc, "Die Gesamtbeträge entnehmen wir der Saldenliste — bitte nur die Aufteilung und "
               "etwaige Sicherheiten ergänzen (z. B. Grundschuld, Bürgschaft, Sicherungsübereignung).")
    vt = doc.add_table(rows=6, cols=5)
    vt.style = "Table Grid"
    _headrow(vt, ["Kategorie", "bis 1 Jahr", "1–5 Jahre", "über 5 Jahre", "gesichert durch"])
    for i, kat in enumerate(("Verbindlichkeiten gegenüber Kreditinstituten",
                             "Verbindlichkeiten aus Lieferungen und Leistungen",
                             "sonstige Verbindlichkeiten", "", ""), start=1):
        vt.rows[i].cells[0].paragraphs[0].add_run(kat).font.size = Pt(9)

    _heading(doc, "E. Sonstige finanzielle Verpflichtungen  (§ 285 Nr. 3a HGB)")
    _note(doc, "Nicht bilanzierte Verpflichtungen, z. B. aus Miet-, Pacht- oder Leasingverträgen.")
    st = doc.add_table(rows=4, cols=3)
    st.style = "Table Grid"
    _headrow(st, ["Art der Verpflichtung", "Betrag p. a.", "Fälligkeit"])

    _heading(doc, "F. Weitere anhangrelevante Sachverhalte")
    for i, (frage, norm, feld) in enumerate(ITEMS, start=1):
        _item(doc, i, frage, norm, feld)

    _heading(doc, "G. Ergänzende Erläuterungen")
    _note(doc, "Zu den oben mit „Ja“ markierten Punkten sowie sonstige Hinweise (in eigenen Worten):", size=9.5)
    box = doc.add_table(rows=1, cols=1)
    box.style = "Table Grid"
    box.rows[0].height = Cm(5); box.rows[0].cells[0].width = Cm(17)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    return OUT


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"OK: {build()}")
