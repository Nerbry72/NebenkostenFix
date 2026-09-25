# Glossar — verbindlicher Begriffs- und Beschriftungskatalog

**Ablageort:** `docs/glossar.md`
**Zielbezug:** „Ein Wort je Sache" — keine zwei Beschriftungen mit gleicher Bedeutung
**Stand:** 22. September 2026
**Wächter:** `tests/test_ui_konsistenz.py` (NK-074) liest die Sperrliste und die Verb-Regel aus
diesem Katalog; § 5 (Navigation) und § 6 (Knopfvokabular) sind die maschinell geprüften Teile.

**Was dieses Dokument ist.** Der Kanon der Wörter, die die Oberfläche benutzt. Jede sichtbare
Beschriftung — Navigation, Überschriften, Knöpfe, Feldbeschriftungen, Meldungen, Tooltips —
bemißt sich an ihm. Ein Begriff, der hier verworfen ist, darf in der Oberfläche nicht auftauchen;
der Test bricht `make check` ab, wenn er zurückkehrt.

---

## 1. Die Dinge der Anwendung

| Begriff | Bedeutung | Verworfen (darf nicht verwendet werden) |
|---|---|---|
| **Immobilie** | Das Gebäude oder Grundstück, dessen Kosten umgelegt werden. Umlagemasse und Gesamtfläche gehören zur Immobilie. | „Objekt“, „Haus“, „Liegenschaft“ |
| **Wohnung** | Eine vermietbare Einheit einer Immobilie. Auch Garagen oder Gewerbeeinheiten sind Wohnungen im Sinne der Oberfläche (Nutzungsart unterscheidet sie). | „Einheit“, „Objekt“, „Unit“ |
| **Mieter** | Das Mietverhältnis: eine Person oder ein Haushalt in einer Wohnung mit Ein- und Auszug. | „Profil“, „Kunde“, „Mietpartei“ |
| **Kostenprofil** | Die Umlagearten einer Wohnung: für jede Kostenart, wie ihr Anteil verteilt wird (nach Fläche, nach Personen, direkt zugewiesen, nur Allgemeinanteil, ignoriert). | „Abrechnungsprofil“, „Profile“ |
| **Anbieter** | Wer eine Rechnung ausstellt (Stadtwerke, Müllabfuhr, Schornsteinfeger). | „Lieferant“, „Vendor“, „Gläubiger“ |
| **Rechnung** | Ein Kostenposten, der umgelegt wird: Betrag, Zeitraum, Kostenart, optional Anbieter und Beleg. | „Kostenpunkt“, „Kostenposition“, „Posten“ |
| **Beleg** | Das Dokument zu einer Rechnung: PDF, Foto oder Scan. | „Dokument“, „Datei“, „Anhang“ |
| **Sammelrechnung** | Ein Beleg, der mehrere Rechnungen enthält (z. B. die Jahresabrechnung der Stadtwerke). Tooltext: „Ein Dokument des Anbieters, aus dem mehrere einzelne Rechnungen erfasst werden.“ | „Dokumenten-Manager“, „Sammelbeleg“ |
| **Kostenart** | Die Betriebskostenart nach BetrKV-Nummer (Nr. 1–17) oder eine eigene Art. | „Kategorie“, „Typ“, „Kostengruppe“ |
| **Zähler** | Ein Erfassungsgerät (Strom, Wasser, Wärme, Gas) mit Zählernummer, Einheit und ggf. HT/NT-Register (Doppeltarif). | „Meter“, „Messgerät“, „Uhr“ |
| **Ablesung** | Ein erfasster Zählerstand zu einem Datum — der Vorgang und der Datensatz. | „Zählerstand“ als Name des Vorgangs oder Knopfs |
| **Abrechnung** | Das Ergebnis für einen Mieter über einen Zeitraum: die Berechnung samt erzeugtem PDF. | „Report“, „Bericht“, „Abrechnungslauf“ |
| **Zahlung** | Ein erfasster Betrag, den ein Mieter gezahlt hat (Miete, Vorauszahlung, Nachzahlung). | „Einnahme“ als Name des Vorgangs oder Knopfs |
| **Einnahmen** | Kennzahl (Summe): die Zahlungen eines Zeitraums. Nur als Überschrift von Kennzahlen, nie als Knopf. | „Umsatz“, „YTD“, „Income“ |
| **Vorauszahlung** | Die Abschläge des Mieters auf Betriebskosten während des Abrechnungsjahres. | „Abschlag“ in Knöpfen und Feldbeschriftungen |
| **Kurzbrief** | Der Abrechnungslauf über weniger als ein Jahr (Einzug, Auszug, Eigentumswechsel). | — |

## 2. Die Umlagearten (Auswahlliste Kostenprofil)

Die fünf Arten tragen genau die Beschriftungen aus `abrechnungsart.ARTEN`; Oberfläche und
Rechenkern dürfen nicht auseinanderlaufen:

| Wert | Beschriftung (wortgleich `abrechnungsart.ARTEN`) |
|---|---|
| `qm` | Umlage nach Wohnfläche |
| `personen` | Umlage nach Personen |
| `direkt` | Nach Verbrauch (eigener Zähler) |
| `nur_allgemein` | Nur Anteil am Allgemeinverbrauch |
| `ignoriert` | Wird diesem Mieter nicht berechnet |

Auf dem Abrechnungsblatt heißt die Zeile einer direkt zugewiesenen Rechnung
„Direkt zugewiesen (100 % der Rechnung für diese Wohnung)“ — sie behauptet keine
Umlage nach Verbrauch (F-20).

Verworfen: „Nach Quadratmeter“, „Ignoriert (Zahlt nichts)“, „Eigenverbrauch“ als Name
der Art, „Kostenpunkt“.

## 3. Ton und Ansprache

1. **Siezen durchgängig.** „Möchten Sie …?“, „Ihre Rechnungen“. Kein „du“, „dich“,
   „dir“, „dein“ in Beschriftungen, Meldungen und Rückfragen.
2. **Knöpfe nennen Verb und Objekt**: „Immobilie anlegen“, „Ablesung erfassen“, „PDF
   erstellen“. Keine „Los“, „OK“, „Go“-Knöpfe. Zerstörende Handlungen heißen ausdrücklich
   so („Mieter löschen“) und fragen vorher nach.
3. **Fehlermeldungen sind Sätze am Entstehungsort.** Was ist passiert, was kann getan
   werden — vollständig auf Deutsch, keine Stacktraces, keine Fehlercodes als einziger Text.
4. **Keine Emojis in Beschriftungen.** Bildzeichen kommen aus dem Phosphor-Iconset
   (`ph ph-…`); jedes Icon ist Dekoration, die Bedeutung steht im Text.
5. **Zahlen mit Einheit**: Fläche in m² (nicht „qm“), Beträge mit Eurozeichen, Temperatur
   und Mengen mit der Einheit des Zählers.
6. **Ein Wort je Sache**: steht hier ein Begriff, wird er überall gleich benutzt — in der
   Navigation, auf Knöpfen, in Meldungen und in Tooltips.

## 4. Tooltips

Komplexe oder fachlich belastete Felder tragen ein Fragezeichen-Icon
(`<i class="ph ph-question feld-hilfe" title="…">`) neben der Beschriftung, Knöpfe mit
uneindeutiger Wirkung ein `title`-Attribut. Pflichtthemen mit festen Erklärungen:

- **Sammelrechnung**: „Ein Dokument des Anbieters, aus dem mehrere einzelne Rechnungen
  erfasst werden.“
- **Direkt zuweisen**: „Die ganze Rechnung gehört dieser Wohnung — nichts wird auf andere
  Wohnungen verteilt.“
- **Nebenkostenvorauszahlung**: „Was der Mieter während des Jahres monatlich auf
  Betriebskosten gezahlt hat.“
- **Kaution**: „Die Sicherheit für Mietschulden; sie wird nicht automatisch verrechnet.“
- **Doppeltarifzähler (HT/NT)**: „Ein Zähler mit zwei Registern für hohe und niedrige
  Tarifzeit; beide Stände werden am selben Datum abgelesen.“
- **Offizieller Zähler**: „Hauptzähler des Versorgers. Private Zwischenzähler messen nur
  einzelne Wohnungen und werden nicht als Hauptzähler erfasst.“
- **Zuletzt abgerechnet bis einschließlich**: „Das Datum der letzten Ablesung, die in einer
  Abrechnung enthalten ist — der Anfangspunkt der nächsten Abrechnung.“
- **Autarke Einzelwohnung**: „Ein Objekt mit nur einer Wohnung, das Heizung und Warmwasser
  selbst erzeugt; keine getrennte Abrechnung nach Heizkostenverordnung.“

## 5. Navigation (maschinell geprüfter Kanon)

Die Navigation trägt genau diese Beschriftungen (Ziel in Klammern):

| Beschriftung | Ziel | Icon | Bisher |
|---|---|---|---|
| Übersicht | `dashboard` | `ph-squares-four` | „Dashboard“ |
| Immobilien | `properties` | `ph-house` | — |
| Mieter | `tenants` | `ph-users` | „Mieter & Profile“ |
| Zähler & Ablesungen | `meters` | `ph-gauge` | „Zählerstände“ |
| Rechnungen & Belege | `invoices` | `ph-receipt` | „Rechnungen“ |
| Abrechnungen | `billing` | `ph-file-text` | Icon doppelt (`ph-receipt`) |
| Zahlungen | `payments` | `ph-coins` | „Einnahmen“ |
| Statistiken | `reports` | `ph-chart-line-up` | — |
| Einstellungen | `settings` | `ph-gear` | — |

## 6. Knopfvokabular (maschinell geprüfte Verbliste)

Jede Schaltfläche beginnt mit einem dieser Verben — das Objekt folgt:

| Verb | Wann | Beispiele |
|---|---|---|
| **anlegen** | Neuer Stammdaten-Datensatz | Immobilie anlegen, Wohnung anlegen, Mieter anlegen, Zähler anlegen, Anbieter anlegen |
| **erfassen** | Neuer beweglicher Datensatz mit Datum oder Betrag | Rechnung erfassen, Ablesung erfassen, Zahlung erfassen |
| **hochladen** | Datei aus dem Dateisystem | Beleg hochladen |
| **erstellen** | Etwas aus Daten Erzeugtes | Abrechnung erstellen, PDF erstellen |
| **bearbeiten** | Vorhandenen Datensatz ändern | Wohnung bearbeiten, Rechnung bearbeiten |
| **löschen** | Zerstörend; fragt vorher nach | Wohnung löschen, Ablesung löschen |
| **speichern** | Eingabeformular abschließen | Speichern |
| **abbrechen / schließen** | Dialog verlassen | Abbrechen, Schließen |
| **exportieren / herunterladen** | Daten oder Datei herausgeben | Daten exportieren, Beleg herunterladen |
| **drucken** | Druckdialog aufrufen | Drucken |
| **aktualisieren** | Ansicht neu laden | Aktualisieren |
| **zurücksetzen** | Zustand zurückstellen (zerstörend; fragt nach) | Datenbank zurücksetzen |
| **öffnen** | Zu einem anderen Bereich springen (nicht erzeugen) | Immobilien öffnen, Rechnungen öffnen |
| **ansehen** | Vorhandenes anzeigt bekommen (kein Neues entsteht) | Abrechnung ansehen, PDF ansehen (einfach), Beleg ansehen |
| **abrechnen** | Abrechnungsvorgang starten | Offene Kosten abrechnen |
| **abmelden** | Sitzung beenden | Abmelden |
| **weiter** | Mehrstufigen Ablauf fortführen | Weiter zur Vorschau |
| **auswählen** | Einen Ort oder eine Datei im System wählen lassen (Dialog des Betriebssystems, nur Windows-App) | Ordner auswählen |
| **übernehmen** | Den ganzen Bestand aus einem Umzugspaket einsetzen (ersetzt alles; fragt nach) | Daten übernehmen |
| **importieren** | Viele Datensätze aus einer Excel- oder CSV-Tabelle anlegen | Aus Excel importieren, Daten importieren |
| **prüfen** | Probelauf ohne Änderung: zeigt Fehler je Zeile | Tabelle prüfen |
| **bleiben** | Die Sitzung vor der Leerlauf-Abmeldung verlängern | Angemeldet bleiben |
| **wiederherstellen** | Eine vor der Abmeldung gesicherte Eingabe zurückholen | Eingabe wiederherstellen |
| **zurück** | Im mehrstufigen Ablauf einen Schritt zurück (Gegenstück zu „weiter“) | Zurück |
| **melden** | Der Anwendung einen Vorgang mitteilen, der außerhalb geschah | Zustellung melden |
| **suchen** | Nachfragen, ob es etwas Neues gibt (nur auf Knopfdruck, NK-081) | Nach Updates suchen |
| **installieren** | Eine neue Version der Anwendung einrichten (nur Windows-App, NK-081) | Update installieren |

Verworfen als alleiniger Knopftext: „OK“, „Los“, „Go“, „Hinzufügen“ (wo ein Verb steht kann
es folgen: „Zahlung hinzufügen“ ist Teil von „erfassen“-Abläufen und bleibt zulässig als
Text **innerhalb** eines Dialogs, nicht als alleiniger Aufrufknopf), „Export“, „Plus“.

Zulässige Formen: hinter dem Verb darf in Klammern näher stehen, **welches** von mehreren
gleichen Zielen gemeint ist — „PDF erstellen (detailliert)“, „PDF ansehen (einfach)“.

Keine Aktionsknöpfe und daher nicht an der Verbliste gemessen: Filter und Auswahlpillen
(Kategorienamen wie „Strom“, „Gas“, „Alle Kosten“) sowie reine Anzeigen („Erste Schritte“,
Kennzahlen).

## 7. Sperrliste (maschinell geprüft)

Diese Zeichenketten dürfen in sichtbaren Beschriftungen nicht vorkommen:

- Englische Reste: `Dashboard`, `Settings`, `Export` (allein), `Danger Zone`, `YTD`,
  `Loading`, `Delete`, `Save`, `Cancel`, `Error`, `Warning` (als Text), `Invoice`,
  `Tenant`, `Property`, `Meter`, `Reading`, `Payment`.
- Verworfene Synonyme aus § 1 und § 2: „Kostenpunkt“, „Dokumenten-Manager“, „qm“,
  „Eigenverbrauch“ als Artname, „Nach Quadratmeter“, „Objekt“ (als Beschriftung),
  „Einheit“ (als Beschriftung), „Profil“ (für Mieter).
- Du-Form: „du“, „dich“, „dir“, „dein“, „deine“, „deinen“, „deiner“, „deines“.
  *Lücke (2026-09-24, F-66):* Imperative wie „Lege fest …“, „Gib …“, „Trage …“ und „Lasse …“
  fängt diese Liste nicht, und Meldungen aus dem Backend (`app.py`, `rechenkern.py`,
  `heizung.py`, `co2.py`, `auth.py`) prüft der Wächter gar nicht. Karte NK-139 (Phase 7).

Ausnahmen (Fachwörter, die deutsch sind und bleiben): „PDF“, „CSV“, „HTML“, „NAS“,
„ID“, „HT/NT“, „API“ — in Meldungen für Betreiber, nicht in Vermieterbeschriftungen.

## 8. Hilfe in der App (Alltagssprache, NK-158)

Die Erklärungen hinter dem „?“ an Fachbegriffen und im Hilfebereich unter „Begriffe von A bis Z“.
Ein Satz, Alltagssprache, gesiezt. **Eine Quelle:** `scripts/hilfe_begriffe.py` erzeugt daraus
`static/hilfe-begriffe.json`; `tests/test_hilfe.py` bricht ab, wenn beide auseinanderlaufen
oder ein Pflichtbegriff in der Oberfläche kein „?“ hat.

| Schlüssel | Begriff | Erklärung |
|---|---|---|
| abrechnungsfrist | Abrechnungsfrist | Die Abrechnung muss dem Mieter spätestens zwölf Monate nach Ende des Abrechnungszeitraums zugehen; danach können Sie keine Nachzahlung mehr verlangen, ein Guthaben müssen Sie trotzdem auszahlen (§ 556 Abs. 3 BGB). |
| abrechnungszeitraum | Abrechnungszeitraum | Die Zeit, über die abgerechnet wird: höchstens zwölf Monate, meist ein Kalenderjahr; bei Ein- oder Auszug zählen nur die Monate, in denen der Mieter dort gewohnt hat. |
| guthaben | Guthaben | Hat der Mieter mehr vorausgezahlt, als an Kosten angefallen ist, bekommt er den Unterschied zurück. |
| hauptzaehler | Hauptzähler | Der Zähler des Versorgers für das ganze Haus; nach ihm stellt der Versorger seine Rechnung. |
| kostenprofil | Kostenprofil | Für jeden Mieter und jede Kostenart die Angabe, wie seine Wohnung beteiligt ist: nach Wohnfläche, nach Personen, nach eigenem Zähler oder gar nicht. |
| leerstand | Leerstand | Zeiten, in denen eine Wohnung nicht vermietet war; ihren Anteil an den Kosten tragen Sie als Vermieter, nicht die übrigen Mieter. |
| nachzahlung | Nachzahlung | Waren die Kosten höher als die Vorauszahlungen, zahlt der Mieter den Unterschied nach. |
| sammelrechnung | Sammelrechnung | Ein Dokument des Anbieters, aus dem Sie mehrere einzelne Rechnungen erfassen, etwa die Jahresabrechnung der Stadtwerke für Wasser und Abwasser. |
| umlagefaehig | umlagefähig | Kosten, die Sie nach § 2 Betriebskostenverordnung auf den Mieter umlegen dürfen, wenn der Mietvertrag es vorsieht; Reparaturen, Verwaltung und Rücklagen gehören nicht dazu. |
| umlageschluessel | Umlageschlüssel | Die Regel, nach der eine Rechnung auf die Wohnungen verteilt wird: nach Wohnfläche, nach Personen oder nach dem Verbrauch laut Zähler. |
| unterzaehler | Unterzähler | Ein eigener Zähler in einer Wohnung, der misst, was diese Wohnung vom Verbrauch des ganzen Hauses selbst verbraucht hat. |
| vorauszahlung | Vorauszahlung | Der Betrag, den der Mieter jeden Monat zusätzlich zur Miete auf die Nebenkosten zahlt; die Abrechnung stellt ihn den tatsächlichen Kosten gegenüber. |
| wohnflaeche | Wohnfläche | Die Fläche der Wohnung in m² laut Mietvertrag; nach ihr werden die meisten Kosten verteilt. |
| zwischenablesung | Zwischenablesung | Ein Zählerstand am Tag eines Mieterwechsels, damit jeder Mieter nur seinen eigenen Verbrauch bezahlt. |
