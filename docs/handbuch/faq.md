# Häufige Fragen

Kurze Antworten zu NebenkostenFix. Wie Sie eine Abrechnung Schritt für Schritt erstellen,
steht im [Handbuch](handbuch.md), Installation und Betrieb in der [README](../../README.md).

## Installation und Betrieb

### Windows warnt beim Setup: „Der Computer wurde durch Windows geschützt“. Ist das gefährlich?

Die Setup-Exe ist nicht mit einem Code-Signing-Zertifikat signiert. Ein solches Zertifikat
kostet jedes Jahr Geld, und NebenkostenFix ist kostenlos. Windows SmartScreen warnt deshalb
bei jedem unbekannten Herausgeber.

Laden Sie das Setup nur unter [Releases](https://github.com/Nerbry72/NebenkostenFix/releases/latest)
herunter und vergleichen Sie die Prüfsumme mit `SHA256SUMS.txt` (siehe
[Windows-App](../../README.md#windows-app)). Stimmt sie, klicken Sie auf **Weitere
Informationen** und dann auf **Trotzdem ausführen**. Updates aus der App heraus prüft
NebenkostenFix selbst über eine digitale Signatur, dort erscheint keine Warnung.

### Windows-App oder Docker, was passt zu mir?

Die Windows-App ist für einen einzelnen PC gedacht und braucht keine Vorkenntnisse. Docker
lohnt sich, wenn die App auf einem NAS oder Server läuft und Sie aus dem Browser von jedem
Gerät im Netz darauf zugreifen möchten. Beide rechnen gleich, und Sie können später in beide
Richtungen umziehen.

### Wo liegen meine Daten?

Nur bei Ihnen: in der Windows-App in `Dokumente\NebenkostenFix`, bei Docker im Ordner
`daten/` neben der Compose-Datei. Nichts davon geht an einen Server von NebenkostenFix. Was
genau in dem Ordner liegt, steht in der README unter
[Wo die Daten liegen](../../README.md#wo-die-daten-liegen).

### Ich habe mein Passwort vergessen.

- **Windows-App:** Menü **Hilfe** → **Passwort vergessen …** im Programmfenster.
- **Docker:** Der Betreiber setzt es auf der Kommandozeile zurück, siehe
  [Konten auf der Kommandozeile](../../README.md#konten-auf-der-kommandozeile).

### Wie bekomme ich Updates?

Die App sieht höchstens einmal am Tag nach, ob es eine neue Version gibt, und meldet sie.
In der Windows-App installiert **Update installieren** die neue Version, sichert vorher
Ihre Daten und startet die App neu. Bei Docker aktualisieren Sie das Image. Einzelheiten
unter [Updates](../../README.md#updates).

### Kann ich die Suche nach Updates abschalten?

Ja, unter **Einstellungen** → **Updates** → **Automatisch nach Updates suchen**. Bei der
Suche wird nichts von Ihren Daten übertragen.

## Sichern und Umziehen

### Wie sichere ich meine Daten?

Unter **Einstellungen** → **Datensicherung** → **Sicherung erstellen**. Die Sicherung ist
eine `.nkfix`-Datei mit Datenbank und allen Belegen, auf Wunsch mit einer Passphrase
verschlüsselt. Kopieren Sie sie auf eine externe Platte oder einen anderen Rechner, eine
Sicherung auf derselben Platte hilft bei einem Plattenschaden nicht.

### Wie ziehe ich auf einen neuen PC um?

Auf dem alten Rechner **Alles exportieren**, auf dem neuen Rechner bei der Einrichtung
„Daten aus einer anderen Installation übernehmen“ wählen. Das geht zwischen Windows und
Docker in beide Richtungen. Anleitung unter
[Umzug auf einen anderen Rechner](../../README.md#umzug-auf-einen-anderen-rechner).

### Kann ich meine bisherige Excel-Tabelle übernehmen?

Ja, über **Aus Excel importieren** auf den Seiten Immobilien, Mieter, Zähler & Ablesungen,
Rechnungen & Belege und Zahlungen. Ein Probelauf zeigt vorher, was übernommen würde.

## Abrechnung und Recht

### Welche Kosten darf ich umlegen?

Die Betriebskosten nach Par. 2 BetrKV, soweit der Mietvertrag ihre Umlage vereinbart. Die
App zeigt die Liste unter **Hilfe** → **Grundlagen**. Nicht umlegbar sind zum Beispiel
Verwaltungskosten, Reparaturen und Instandhaltung.

### Bis wann muss die Abrechnung beim Mieter sein?

Spätestens zwölf Monate nach Ende des Abrechnungszeitraums (Par. 556 Abs. 3 BGB).
Entscheidend ist der Zugang beim Mieter, nicht das Absenden. Melden Sie deshalb nach dem
Verschicken in den Details der Abrechnung **Zustellung melden**, dann zeigt die App die
Fristen an.

### Ich habe einen Fehler in einer verschickten Abrechnung gefunden.

Öffnen Sie die Abrechnung und wählen Sie **Korrektur erstellen**. Die Korrektur entsteht
als neue Version mit neuen PDFs, die alte bleibt erhalten.

### Mein Haus hat auch einen Laden oder ein Büro.

Das rechnet NebenkostenFix nicht. Für gewerbliche und gemischt genutzte Gebäude gelten
eigene Regeln. Siehe [Gewerbe im Haus](handbuch.md#gewerbe-im-haus).

### Ersetzt NebenkostenFix eine Rechtsberatung?

Nein. Die App rechnet nach BetrKV, HeizkostenV und CO2KostAufG und wird mit vielen Tests
geprüft, trotzdem kann sie Fehler enthalten und Ihren Einzelfall nicht kennen. Prüfen Sie
jede Abrechnung, bevor Sie sie verschicken. Im Zweifel fragen Sie Ihren Eigentümerverband
oder eine Anwältin für Mietrecht. Siehe auch [Haftung](../../README.md#haftung).

## Projekt

### Was kostet NebenkostenFix?

Nichts. NebenkostenFix ist kostenlos und quelloffen (GPL-3.0-or-later). Wer das Projekt
unterstützen möchte, kann über [Ko-fi](https://ko-fi.com/nerbry72) spenden.

### Wie melde ich einen Fehler?

In der App unter **Hilfe** → **Über NebenkostenFix** → **Fehler melden**. Das öffnet ein
Formular auf GitHub, in dem nur Version, Auslieferungsweg und Betriebssystem vorausgefüllt
sind. Daten aus Ihrer Abrechnung werden nicht übertragen. Schicken Sie keine Namen,
Adressen oder Belege mit.
