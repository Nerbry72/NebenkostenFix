# Servermodus: die Windows-App mit einem Server verbinden (#45)

Die Windows-App kann statt der Daten auf diesem Rechner eine NebenkostenFix-Installation
auf einem Server öffnen, zum Beispiel eine Docker-Instanz im Heimnetz. Sie zeigt den
Server im eigenen Fenster, wie ein Browser, nur ohne Adressleiste.

## Was gebaut ist

- **Ein Eintrag, sonst nichts:** Beim Verbinden schreibt die App nur `[Server] Adresse` in
  `%LOCALAPPDATA%\NebenkostenFix\einstellungen.ini`. Die INI wird atomar geschrieben
  (erst eine `.tmp`-Datei, dann umbenannt). Der Rückweg entfernt genau diesen Eintrag.
- **Weiche beim Start:** Steht eine Adresse in der INI, startet die App im Servermodus.
  Der Schalter `--datenordner` erzwingt immer den lokalen Modus.
- **Im Servermodus läuft kein lokaler Server.** Der Datenordner wird weder geöffnet noch
  angelegt noch verändert, der lokale Port bleibt zu.
- **Kleine Brücke:** Die Server-Seite erreicht nur `speichern` (Speichern-Dialog),
  `oeffnen` (nur PDF und Bilder, siehe unten) und `extern_oeffnen` (nur die Projektseite).
  Jede Methode prüft vorher, ob das Fenster noch die Seite des Servers zeigt. Ordnerwahl,
  Umzug, Umschalten und Neustart gibt es dort nicht.
- **Navigationssperre:** Landet das Fenster auf einer fremden Seite, lädt es die
  Startseite des Servers neu.
- **Menü im Servermodus:** Datei → Drucken, Neu laden, Auf diesem Rechner arbeiten …,
  Beenden; Hilfe → Über. Der Fenstertitel nennt den Server, bei `http://` mit dem Zusatz
  „(unverschlüsselt)“.
- **Updates:** Auch im Servermodus sucht die App beim Start nach einer neuen Version (von
  der Projektseite, nicht vom Server). Sie fragt vor der Installation und startet danach
  wieder im Servermodus. Gemerkt wird der Zeitpunkt der Suche im lokalen App-Ordner, nicht
  im Datenordner.
- **Dateien öffnen (beide Modi):** `oeffnen` gibt nur `.pdf`, `.jpg`, `.jpeg`, `.png`,
  `.webp` und `.heic` an das Standardprogramm. Alles andere geht in den Speichern-Dialog,
  eine `.exe` aus einem Upload startet nie.

## Verbinden

1. In der Windows-App (lokale Daten): Einstellungen → Sicherung → Karte
   **Mit einem Server verbinden**. Auf der leeren Übersicht führt die zweite Aktion
   „Mit einem Server verbinden“ dorthin.
2. Adresse eintragen, zum Beispiel `https://nebenkosten.example.de` oder
   `http://192.168.1.10:8080`. Ohne `http://` oder `https://` nimmt die App `https://`.
   Ein Pfad (`/nk`), Benutzername oder Passwort in der Adresse werden abgelehnt.
3. Den Haken setzen und **Verbinden** wählen. Bei `http://` fragt die App noch
   einmal nach.
4. Die App fragt `/api/health` ab. Antwortet dort ein NebenkostenFix, trägt sie die
   Adresse ein und startet neu. Sonst bleibt alles, wie es war, und die Karte nennt den
   Grund (nicht erreichbar, kein NebenkostenFix, Zertifikat, Weiterleitung, Pfad).

Weiterleitungen folgt die Prüfung nicht, mit einer Ausnahme: `http://host` → `https://host`
auf demselben Host (Standardports) übernimmt sie selbst.

Ihre Daten auf diesem Rechner bleiben unverändert. Wer sie auf den Server bringen will,
nutzt den Umzug (`docs/UMZUG.md`). **Achtung: Die Übernahme ersetzt alles, was schon auf
dem Server ist.**

## Zertifikat

Die App kennt keine Ausnahmen für Zertifikate. WebView2 und die Prüfung beim Verbinden
vertrauen dem Windows-Zertifikatsspeicher. Zwei Wege:

- **Ein öffentliches Zertifikat am Reverse-Proxy**, zum Beispiel von Let's Encrypt
  (siehe „HTTPS und Reverse Proxy“ im README). Das ist der einfache Weg.
- **Ein eigenes (selbstsigniertes) Zertifikat** in Windows importieren: die Datei des
  Zertifikats (nicht den privaten Schlüssel) doppelklicken → „Zertifikat installieren“ →
  „Aktueller Benutzer“ → „Alle Zertifikate in folgendem Speicher speichern“ →
  „Vertrauenswürdige Stammzertifizierungsstellen“. Danach die App neu starten.

## Anmeldeschleife bei http

Läuft der Server mit `BEHIND_HTTPS` (Cookies nur über https) und die App verbindet sich
mit `http://`, schickt der Server nach jeder Anmeldung wieder zur Anmeldung. Die Prüfung
erkennt das nicht. Abhilfe: die Adresse mit `https://` eintragen. Die Seite „Keine
Verbindung zum Server“ nennt diesen Hinweis bei `http://` ebenfalls.

Die Anmeldung gilt für eine Sitzung. Nach jedem Start der App meldet man sich neu an.
Die App speichert keine Passwörter; Cookies liegen im WebView2-Profil unter
`%LOCALAPPDATA%\NebenkostenFix\WebView2`.

## Zurück zu den lokalen Daten

Datei → **Auf diesem Rechner arbeiten …** → bestätigen. Die App entfernt die Adresse aus
der INI und startet mit den lokalen Daten neu, so wie sie vor dem Verbinden waren. Ist der
Server nicht erreichbar, zeigt das Fenster „Keine Verbindung zum Server“; der Rückweg über
das Menü geht trotzdem.

## Ältere Versionen

- **Ältere App, INI mit `[Server]`:** Eine ältere App kennt den Eintrag nicht und startet
  lokal. Der Eintrag bleibt stehen.
- **Neue App, älterer Server (ab 0.9):** `/api/health` antwortet gleich. Die alte
  Oberfläche ruft nur `speichern`, `oeffnen` und `extern_oeffnen`. Den Ordnerknopf der
  Sicherung zeigt sie trotzdem; ein Klick darauf tut nichts. Server vor 0.9 sind nicht
  geprüft.
- Datenbank, Sicherungsformat und Umzugspaket sind unverändert. Alte Sicherungen lassen
  sich weiter einspielen.

## Noch offen

- Unter Windows nicht von Hand geprüft (siehe Prüfliste unten).
- Der Schalter „Updates automatisch“ aus den lokalen Einstellungen gilt im Servermodus
  nicht, weil der Datenordner zu bleibt. Die App sucht dort höchstens einmal in
  24 Stunden und fragt vor jeder Installation.
- Nicht im MVP: Wahlseite beim ersten Start, mehrere Server, Installer-Schalter
  `/SERVER=`, Ausnahmen für selbstsignierte Zertifikate, Anmeldung über einen
  Identitätsanbieter, Offline-Zwischenspeicher, eigener Umzugsassistent, Unterpfad hinter
  dem Reverse-Proxy, Versionsangabe in `/api/health`.
- Mehrere Rechner gleichzeitig auf einem Server verhalten sich wie mehrere Browser heute;
  das ist ein eigenes Thema.

## Prüfliste Windows (von Hand)

Ein Rechner mit Windows 10 oder 11 reicht, dazu ein NebenkostenFix-Server im Netz
(Docker), einmal mit `https://` und einmal mit `http://`.

1. **Navigation:** Nach dem Verbinden lädt das Fenster den Server, auch nach der
   Anmeldung und nach Datei → Neu laden. Der Link „Projektseite auf GitHub“ in den
   Einstellungen öffnet sich im Browser, nicht im Fenster. Ob die Sperre bei fremden Seiten greift
   (`events.loaded` bei Navigation durch die Seite selbst), lässt sich nur mit einer
   präparierten Server-Seite prüfen, die per `location.href` wegspringt.
2. **Brücke:** Im Servermodus eine Abrechnung als PDF speichern und eine Rechnung öffnen.
   Beides klappt; im Protokoll (`%LOCALAPPDATA%\NebenkostenFix\konsole.log`, falls
   vorhanden) steht keine Warnung „fremder Ursprung“.
3. **Anmeldung und Cookies:** Am Server anmelden, App schließen, neu starten: Die App
   fragt wieder nach der Anmeldung. Zurück zu lokal: Die lokale App läuft ohne Anmeldung
   wie vorher.
4. **Zertifikat:** Einen Server mit selbstsigniertem Zertifikat eintragen. Die Karte meldet
   „Das Zertifikat des Servers ist nicht vertrauenswürdig“. Nach dem Import des Zertifikats
   (siehe oben) klappt die Verbindung, und das Fenster zeigt die Seite ohne Warnung.
5. **Dateien und Druck:** Beleg hochladen (Dateiauswahl), Abrechnung herunterladen, PDF
   auf einer bestimmten Seite öffnen, Datei → Drucken.
6. **Neustart:** Verbinden startet die App neu, ebenso „Auf diesem Rechner arbeiten …“.
   Ein Update im Servermodus installieren (die Frage mit OK bestätigen): Danach startet die
   App von selbst wieder im Servermodus.

**Abwärtskompatibilität (von Hand):**

- Eine 0.11-Installation mit erfundenen Daten auf den neuen Stand aktualisieren: Die App
  startet lokal, alle Daten sind da.
- Auf einen Server umschalten und zurück: Der lokale Datenordner ist bytegleich (vorher
  und nachher eine Prüfsumme über den Ordner bilden, etwa mit `Get-FileHash`).
- Den neuen Stand deinstallieren und 0.11 neu installieren: Die App startet lokal,
  `[Server]` steht weiter in der INI.
- Eine alte Sicherung einspielen.
