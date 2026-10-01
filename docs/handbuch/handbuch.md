# Handbuch

Dieses Handbuch führt Sie durch Ihre erste Nebenkostenabrechnung mit NebenkostenFix und
erklärt die häufigen Sonderfälle. Installation, Updates, Datensicherung und Umzug stehen in
der [README](../../README.md). Kurze Antworten auf häufige Fragen finden Sie in der
[FAQ](faq.md).

Die Begriffe in diesem Handbuch sind dieselben wie in der App. Was ein Wort genau bedeutet,
steht in der App unter **Hilfe → Begriffe von A bis Z**. Eine Kurzanleitung als PDF
öffnen Sie in der **Hilfe** mit **Kurzanleitung öffnen (PDF)**.

> NebenkostenFix rechnet nach Betriebskostenverordnung, Heizkostenverordnung und
> CO2KostAufG. Es ersetzt keine Rechtsberatung. Prüfen Sie jede Abrechnung, bevor Sie sie
> verschicken.

## Inhalt

1. [Bevor Sie anfangen](#bevor-sie-anfangen)
2. [Erst ausprobieren](#erst-ausprobieren)
3. [Die erste Abrechnung Schritt für Schritt](#die-erste-abrechnung-schritt-für-schritt)
4. [Nach der Abrechnung: Zustellung und Fristen](#nach-der-abrechnung-zustellung-und-fristen)
5. [Sonderfälle](#sonderfälle)
6. [Daten aus Excel übernehmen](#daten-aus-excel-übernehmen)
7. [Zahlungen](#zahlungen)
8. [Einstellungen im Überblick](#einstellungen-im-überblick)

## Bevor Sie anfangen

Legen Sie sich zurecht, was die Abrechnung braucht. Die App zeigt dieselbe Liste unter
**Hilfe → Was Sie vorher sammeln**:

- die Rechnungen und Belege des Jahres (Grundsteuer, Wasser, Müll, Versicherung, Strom für
  Allgemeinflächen, Heizung und so weiter),
- die Zählerstände zum Stichtag und bei jedem Mieterwechsel,
- die Mietverträge mit Ein- und Auszugsdatum und den vereinbarten Vorauszahlungen,
- die Wohnfläche jeder Wohnung in m²,
- die Personenzahl je Haushalt, wenn Sie Kosten nach Personen verteilen.

Welche Kosten Sie überhaupt umlegen dürfen, steht unter **Hilfe → Grundlagen** (Par. 2
BetrKV). Was im Mietvertrag nicht vereinbart ist, dürfen Sie in der Regel nicht umlegen.

## Erst ausprobieren

Auf der **Übersicht** stehen die **Erste Schritte**. Der erste Schritt legt eine
**Beispielimmobilie** an: ein kleines Haus mit zwei Wohnungen, Mietern, Zählern und
Rechnungen. Damit können Sie jede Seite gefahrlos ausprobieren und eine Abrechnung
erzeugen, bevor Sie Ihre eigenen Daten eingeben. Die Beispielimmobilie löschen Sie danach
unter **Immobilien** wie jede andere.

## Die erste Abrechnung Schritt für Schritt

Die Reihenfolge entspricht den **Erste Schritte** auf der Übersicht.

### 1. Immobilie anlegen

Unter **Immobilien** legen Sie das Haus an: Name, Adresse, Gesamtfläche. Hat das Haus eine
zentrale Heizung, erfassen Sie sie über **Anlage erfassen** als Heizungsanlage. Vermieten
Sie nur eine einzelne Wohnung ohne Haus drumherum, setzen Sie **Ist eine autarke
Einzelwohnung**.

### 2. Wohnungen anlegen

Auf der Karte der Immobilie legen Sie jede Wohnung an, mit Wohnfläche in m² und
Nutzungsart (Wohnraum oder Gewerbe). Zwei Häkchen sind für Sonderfälle da:

- **Vom Vermieter selbst bewohnt**, siehe [Eigennutzung](#eigennutzung).
- **Beheizt sich selbst** (eigene Therme, eigener Ofen). Diese Wohnung nimmt an den
  Heizkosten und am CO₂ des Hauses nicht teil.

### 3. Mieter anlegen

Unter **Mieter** legen Sie jeden Mieter mit Wohnung, Einzug und gegebenenfalls Auszug an.
Den Mietvertrag können Sie gleich mit hochladen. In der Mieterliste stehen je Mieter zwei
weitere Knöpfe:

- **Kostenprofil**: je Kostenart der Umlageschlüssel, also wie dieser Mieter an ihr
  beteiligt ist.
- **Haushaltsgröße**: wie viele Personen ab wann im Haushalt leben. Das braucht es nur für
  Kosten, die nach Personen verteilt werden.

Haben Sie für diesen Mieter früher schon anders abgerechnet, tragen Sie unter **Zuletzt
abgerechnet bis einschließlich** das Ende des letzten Zeitraums ein. Die App schließt dann
nahtlos an.

### 4. Rechnungen erfassen

Unter **Rechnungen & Belege** erfassen Sie jede Rechnung mit Kostenart, Betrag, Zeitraum
und Zuweisung. Den Beleg laden Sie als PDF oder
Foto hoch. Enthält ein Sammelbeleg mehrere Rechnungen, geben Sie die betroffenen Seiten
an. Heizrechnungen ordnen Sie der Heizungsanlage zu und tragen CO₂-Kosten und
CO₂-Emissionen des Belegs ein, sonst kann die App die CO₂-Kosten nicht aufteilen.

### 5. Zähler & Ablesungen (nur bei Verbrauch)

Brauchen Sie keine verbrauchsabhängigen Kosten, überspringen Sie diesen Schritt. Sonst
legen Sie unter **Zähler & Ablesungen** jeden Zähler an. Ein Zähler mit Tag- und
Nachttarif ist ein Doppeltarif-Zähler (HT/NT). **Offizieller Zähler vom Versorger** unterscheidet den
Zähler des Versorgers von einem privaten Unterzähler.

Ablesungen tragen Sie zum Stichtag ein, am besten mit einem Beweisfoto. Bei einem
Mieterwechsel wählen Sie als Art der Ablesung **Zwischenablesung**, siehe
[Mieterwechsel](#mieterwechsel-im-laufenden-jahr).

### 6. Jahr abrechnen

Unter **Abrechnungen** startet **Jahr abrechnen** einen Assistenten in fünf Schritten:

1. **Jahr und Immobilie** wählen.
2. **Rechnungen**: Die App zeigt alle Rechnungen des Jahres neben dem Vorjahr. Fehlt eine
   Kostenart, die es im Vorjahr gab, fällt das hier auf. Mit **Liste prüfen** gehen Sie
   sie durch, mit **Als Tabelle erfassen** tragen Sie fehlende Rechnungen schnell nach.
3. **Ablesungen**: Welche Zählerstände fehlen noch, und für welche Zähler.
4. **Vorschau**: die Abrechnung jedes Mieters mit Nachzahlung oder Guthaben. Einzelne
   Mieter können Sie abwählen. Hier ist noch nichts festgesetzt.
5. **Abschließen**: Mit **Anschreiben bearbeiten** passen Sie den Begleittext an,
   **Abrechnungen erstellen** setzt die Abrechnungen fest und erzeugt die PDFs, jeweils
   einfach und detailliert.

Für einen einzelnen Mieter oder einen abweichenden Zeitraum gibt es **Abrechnung frei
erstellen**: Mieter und Zeitraum wählen, **Weiter zur Vorschau**, dann **PDF erstellen &
abschließen**.

## Nach der Abrechnung: Zustellung und Fristen

Schicken Sie jedem Mieter seine Abrechnung und öffnen Sie danach in den Details der
Abrechnung **Zustellung melden**. Maßgeblich ist der Tag, an dem die Abrechnung beim
Mieter ankommt, nicht der Tag, an dem Sie sie abschicken.

Ab dann zeigt die App zwei Fristen (Par. 556 Abs. 3 BGB):

- **Nachforderungsfrist**: Die Abrechnung muss dem Mieter spätestens zwölf Monate nach
  Ende des Abrechnungszeitraums zugehen. Kommt sie später, können Sie eine Nachzahlung in
  der Regel nicht mehr verlangen.
- **Einwendungsfrist**: Der Mieter kann bis zwölf Monate nach Zugang Einwände erheben.

### Eine Abrechnung korrigieren

Stellt sich ein Fehler heraus, öffnen Sie die Abrechnung und wählen **Korrektur
erstellen**. Die Korrektur rechnet mit den heutigen Daten, entsteht als neue Version und
bekommt neue PDFs. Die alte Version bleibt zum Nachweis erhalten.

## Sonderfälle

### Mieterwechsel im laufenden Jahr

1. Beim alten Mieter das Auszugsdatum eintragen, beim neuen das Einzugsdatum. Das
   Auszugsdatum ist der letzte Miettag, er wird dem alten Mieter noch berechnet. Zieht er
   am 30.09. aus, zieht der neue Mieter am 01.10. ein.
2. Beim Wechsel jeden Zähler der Wohnung ablesen und als **Zwischenablesung** eintragen,
   mit dem letzten Miettag oder dem Einzugstag als Datum. Beides zählt als Übergabe.
3. **Jahr abrechnen** verteilt die Kosten dann auf beide Mieter: verbrauchsabhängige Kosten
   nach den Zählerständen, alle anderen nach Tagen.

Welche Zählerstände noch fehlen, sehen Sie im Assistenten im Schritt **Ablesungen**.

### Leerstand

Zeiten, in denen eine Wohnung nicht vermietet war, rechnet die App automatisch als
Leerstand. Den Anteil dieser Zeit an den Kosten tragen Sie als Vermieter, nicht die übrigen
Mieter. Sie müssen dafür nichts eintragen.

### Eigennutzung

Wohnen Sie selbst im Haus, setzen Sie bei Ihrer Wohnung **Vom Vermieter selbst bewohnt**.
Die Wohnung ist dann nicht leer, zählt aber auch auf keinen Mieter. Ihren Anteil an den
Kosten tragen Sie selbst, er erscheint in keiner Abrechnung eines Mieters.

### Heizung und CO₂

Für eine zentrale Heizung braucht die Immobilie eine Heizungsanlage (**Anlage erfassen**).
Die Anlage trägt den Verbrauchsanteil nach Par. 7 Abs. 1 HeizkostenV und die
Heizrechnungen. Die CO₂-Kosten teilt die App nach dem Stufenmodell des CO2KostAufG
zwischen Ihnen und den Mietern auf. Dafür braucht jede Heizrechnung die CO₂-Kosten und
CO₂-Emissionen des Belegs.

Wohnungen mit eigener Heizung markieren Sie mit **Beheizt sich selbst**.

### Gewerbe im Haus

NebenkostenFix rechnet nach dem Recht für Wohngebäude. Für gewerbliche und gemischt
genutzte Gebäude gelten eigene Regeln (Par. 8 CO2KostAufG), die die App nicht rechnet.
Hat eine Immobilie eine Wohnung mit der Nutzungsart **Gewerbe**, lehnt die App die
Abrechnung dieser Immobilie deshalb ab und sagt, warum. Rechnen Sie den Wohnteil in einer
eigenen Immobilie ab oder wenden Sie sich an einen Verwalter.

## Daten aus Excel übernehmen

Immobilien, Mieter, Zähler, Rechnungen und Zahlungen können Sie jeweils über **Aus Excel
importieren** übernehmen: Vorlage herunterladen, ausfüllen, Spalten zuordnen, dann ein
Probelauf, der zeigt, was übernommen würde. Erst danach wird wirklich importiert. Mehr dazu
in der README unter [Daten aus Excel übernehmen](../../README.md#daten-aus-excel-übernehmen).

## Zahlungen

Unter **Zahlungen** erfassen Sie die Vorauszahlungen der Mieter. Mit der Serienbuchung
tragen Sie gleiche monatliche Zahlungen für ein ganzes Jahr auf einmal ein. Die
Abrechnung rechnet die gezahlten Vorauszahlungen gegen die Kosten.

## Einstellungen im Überblick

Die **Einstellungen** sind in Gruppen geteilt:

- **Vermieter & Anbieter**: Name und IBAN für das Deckblatt und den GiroCode (QR-Code zum
  Bezahlen), auf Wunsch Ihr Logo, dazu die Anbieter und Versorger für die Rechnungen.
- **Datensicherung**: **Sicherung erstellen** (auf Wunsch mit Passphrase verschlüsselt),
  **Belege exportieren** als ZIP mit sprechenden Dateinamen und der Umzug mit **Alles
  exportieren** und **Daten übernehmen (ersetzt alles)**. Anleitung in der README unter
  [Sichern und Zurückholen](../../README.md#sichern-und-zurückholen) und
  [Umzug auf einen anderen Rechner](../../README.md#umzug-auf-einen-anderen-rechner).
- **Konto**: Darstellung (Schrift und Knöpfe in 100, 115 oder 130 %, gilt für diesen
  Browser), **Passwort ändern** und **Zweites Konto anlegen**, etwa für den Partner.
- **Updates**: **Automatisch nach Updates suchen**, siehe
  [Updates](../../README.md#updates).
- **Datenschutz**: **Gesperrte Mietverhältnisse** sind gelöschte Mieter, deren
  festgesetzte Abrechnungen und Zahlungen noch aufbewahrt werden müssen (Par. 147 AO,
  Par. 257 HGB). Sie sind überall ausgeblendet und werden nach dem genannten Tag
  automatisch gelöscht. Dazu der **Datenauszug für andere Programme** mit allen Daten.
