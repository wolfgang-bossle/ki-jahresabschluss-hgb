# KI-Jahresabschluss nach HGB

**Saldenliste · Bilanz · Anhang**

Wolfgang Bossle, CPA · Claude Certified Architect

**→ [Demo-Abschluss herunterladen](../../releases/latest).** Am Release hängt das PDF des Musterfalls.

## Ausgangspunkt

Das Repositorium zeigt an einem erfundenen Musterfall, wie der Jahresabschluss einer kleinen GmbH nach HGB mit KI-Unterstützung entstehen kann, ohne dass eine Zahl ungeprüft in das Dokument gelangt. Eingang ist die Saldenliste, Ausgang sind Bilanz, Gewinn- und Verlustrechnung und Anhang als PDF. Jede Zahl lässt sich bis auf das Konto zurückverfolgen.

## Was im Repositorium steckt

**Die Saldenliste ist die einzige Wahrheit.** Bilanz und Gewinn- und Verlustrechnung werden ausschließlich aus der Saldenliste abgeleitet, nie umgekehrt. Geht die Bilanz nicht auf den Cent auf oder ist ein Konto keinem Posten zugeordnet, bricht der Lauf ab.

**Die Gliederung kommt aus der Taxonomie.** Die Konten werden über die HGB-Taxonomie den Posten nach § 266 und § 275 HGB zugeordnet, nicht aus dem Trainingswissen eines Sprachmodells.

**Die Werkzeuge rechnen, die KI formuliert.** Die Texte des Anhangs formuliert Claude von Anthropic. Jede Zahl und jede Tatsachenbehauptung darin muss auf eine Stelle im Datenmodell verweisen und wird dort centgenau geprüft, bevor sie in das Dokument gelangt. Eine Zahl im Text ohne diesen Verweis wird gemeldet.

Anthropic hat an dem Repositorium nicht mitgewirkt.

## Anwendbarkeit

Das Repositorium ist auf die kleine GmbH im Sinne von § 267 Abs. 1 HGB zugeschnitten; die Größenklasse wird aus den Daten geprüft. Die Gewinn- und Verlustrechnung folgt dem Gesamtkostenverfahren. Die Kontonummern der Musterdaten sind an den SKR 03 angelehnt, aber nicht gegen den offiziellen Kontenrahmen abgeglichen. Alle Gesellschaften, Konten und Zahlen sind frei erfunden.

Die Anhangtexte des Musterfalls liegen formuliert und geprüft im Repositorium. Für eine andere Gesellschaft formuliert Claude sie neu; der MCP-Server `jahresabschluss-hgb` stellt dazu den Kontext bereit und prüft das Ergebnis.

## Ausprobieren

Voraussetzung ist Python 3.12 oder neuer.

```
pip install fastmcp jsonschema openpyxl reportlab pdfplumber
python scripts/verify.py
python scripts/render_pdf_demo.py
```

`verify.py` prüft die Bilanzprobe und die festen Werte des Musterfalls, `render_pdf_demo.py` erzeugt das PDF unter `output/baeckerei_2025/`.

## Einordnung

Das Repositorium ist an einem erfundenen Musterfall gebaut und aus den genannten Normen hergeleitet, nicht im Mandantenbetrieb erprobt. Es zeigt einen Weg, es ist kein Werkzeug für die Aufstellung echter Jahresabschlüsse.

Rückmeldungen gerne per Direktnachricht auf LinkedIn: <https://www.linkedin.com/in/wolfgang-bossle/>

## Keine Haftung

**Das Repositorium wird unentgeltlich abgegeben. Der Verfasser übernimmt keinerlei Haftung für Schäden, die aus seiner Verwendung entstehen, gleich aus welchem Rechtsgrund.**

Es wird keine Erstellung, Prüfung, prüferische Durchsicht, Rechts- oder Steuerberatung erbracht. Das Ergebnis ist kein Jahresabschluss zur Aufstellung, Feststellung oder Offenlegung. Durch die Verwendung entsteht kein Vertrag, kein Mandat und kein Auskunftsverhältnis.

Für Vollständigkeit, Richtigkeit und Aktualität wird keine Gewähr übernommen. Normtexte und Taxonomie geben den Stand zum Zeitpunkt des Abrufs wieder; maßgeblich ist immer die Quelle selbst. Für die Inhalte verlinkter Seiten sind deren Betreiber verantwortlich.

Wer den Code einsetzt, entscheidet selbst und auf eigene Verantwortung, ob ein Ergebnis zutrifft.

Ergänzend gelten der Gewährleistungs- und Haftungsausschluss der MIT-Lizenz für Code und Musterdaten und Abschnitt 5 des Lizenztextes von CC BY-ND 4.0 für Texte und Demo-Ergebnis.

## Lizenz

© Wolfgang Bossle.

**Code und Musterdaten** (`mcp/`, `scripts/`, `tests/`, `data/`): MIT-Lizenz, siehe `LICENSE`.

**Texte und Demo-Ergebnis** (diese Datei, `output/`, das PDF am Release): Creative Commons Namensnennung-Keine Bearbeitungen 4.0 International (CC BY-ND 4.0), siehe `LICENSE-CC-BY-ND-4.0` und <https://www.creativecommons.org/licenses/by-nd/4.0/>. Weitergabe ist erlaubt, auch kommerziell, sofern das Dokument unverändert bleibt. Bei Weitergabe bleiben erhalten: der Name des Urhebers, dieser Vermerk, der Hinweis auf die Lizenz und der Abschnitt „Keine Haftung“.

**Taxonomie** (`taxonomy/`): © XBRL Deutschland e.V., verwendet nach dessen Nutzungsbedingungen, siehe `taxonomy/NOTICE`.

**Gesetzestext** (`rag/chunks.json`): HGB nach gesetze-im-internet.de, keine amtliche Fassung.
