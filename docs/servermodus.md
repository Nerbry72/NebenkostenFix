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
- **Kleine Brücke:** Die Server-Seite erreicht nur vier Methoden: `speichern`
  (Speichern-Dialog), `oeffnen` (nur PDF und Bilder, siehe unten), `extern_oeffnen` (nur
  die Projektseite) und `lokal_arbeiten` (ohne Parameter; öffnet nur die Rückfrage von
  Windows zum Rückweg, siehe unten). Jede Methode prüft vorher, ob das Fenster noch die
  Seite des Servers zeigt. Ordnerwahl, Umzug und Umschalten auf einen anderen Server gibt
  es dort nicht.
- **Navigationssperre:** Landet das Fenster auf einer fremden Seite, lädt es die
  Startseite des Servers neu. Schickt der Server selbst immer wieder weg (etwa ein
  Anmelde-Proxy vor „/“), zeigt das Fenster nach drei Rücksprüngen binnen zehn Sekunden
  die Offline-Seite mit der Weiterleitungsmeldung, statt endlos neu zu laden.
- **Umschalten nur aus der eigenen Oberfläche:** `server_verbinden` der lokalen App prüft,
  ob das Fenster die Seite des lokalen Servers zeigt. Eine fremde Seite kann die App nicht
  umstellen.
- **Menü im Servermodus:** Datei → Drucken, Neu laden, Auf diesem Rechner arbeiten …,
  Beenden; Hilfe → Über. Der Fenstertitel nennt den Server, bei `http://` mit dem Zusatz
  „(unverschlüsselt)“. Nach der Prüfung folgt er der geprüften Adresse, also ohne den
  Zusatz, wenn der Server von `http://` auf `https://` weiterleitet. Dazu zeigen Kopfzeile
  und Einstellungen die Verbindung (siehe „Woran man den Servermodus erkennt“).
- **Updates:** Auch im Servermodus sucht die App beim Start nach einer neuen Version (von
  der Projektseite, nicht vom Server). Sie fragt vor der Installation und startet danach
  wieder im Servermodus. Gemerkt wird der Zeitpunkt der Suche im lokalen App-Ordner, nicht
  im Datenordner.
- **Dateien öffnen (beide Modi):** `oeffnen` gibt nur `.pdf`, `.jpg`, `.jpeg`, `.png`,
  `.webp` und `.heic` an das Standardprogramm. Alles andere geht in den Speichern-Dialog,
  eine `.exe` aus einem Upload startet nie.

## Verbinden

1. In der Windows-App (lokale Daten): Solange noch kein Objekt angelegt ist, fragt die App
   beim Start vor allem anderen „Wo sollen Ihre Daten liegen?“: **Auf diesem Rechner
   arbeiten** (dann Hinweis „Bevor es losgeht“, falls nötig, und die Einführung) oder **Mit
   einem NebenkostenFix-Server verbinden** (öffnet die Verbindungskarte, dort führt **Zurück
   zur Startwahl** zurück). Eine alte Bestätigung des Hinweises im Datenordner spielt dafür
   keine Rolle. Die Wahl kommt bei jedem Start wieder, bis ein Objekt da ist; im Browser und
   auf dem Server nie. Später: Einstellungen → Sicherung → Karte **Mit einem Server
   verbinden**, die zweite Aktion im leeren Reiter **Immobilien** oder im Menü
   **Datei → Mit einem Server verbinden …** (auch wenn schon Objekte da sind).
2. Adresse eintragen, zum Beispiel `https://nebenkosten.example.de` oder
   `http://192.168.1.10:8080`. Ohne `http://` oder `https://` nimmt die App `https://`.
   Scheitert das, weil der Server nur unverschlüsselt läuft, bietet sie `http://` mit
   Rückfrage an.
   Ein Pfad (`/nk`), Benutzername oder Passwort in der Adresse werden abgelehnt.
3. Den Haken setzen und **Verbinden** wählen. Bei `http://` fragt die App noch
   einmal nach.
4. Die App fragt `/api/health` ab. Antwortet dort ein NebenkostenFix, trägt sie die
   Adresse ein und startet neu. Sonst bleibt alles, wie es war, und die Karte nennt rot
   mit Warnsymbol den Grund (nicht erreichbar, kein NebenkostenFix, Zertifikat, Weiterleitung, Pfad).

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

## Woran man den Servermodus erkennt

- **Kopfzeile:** ein Hinweis „Verbunden mit nas.example:8080“ (Host und Port des Servers).
  Bei `http://` steht „(unverschlüsselt)“ dahinter, im Warnton. Ein Klick darauf führt zur
  Karte in den Einstellungen.
- **Einstellungen → Sicherung:** die Karte **Mit einem Server verbunden** mit der Adresse
  und dem Rückweg.
- **Fenstertitel:** nennt den Server, wie oben beschrieben. Ihn setzt die App selbst, nicht
  die Seite des Servers.

Kopfzeile und Karte gibt es nur, wenn App **und** Server diesen Stand haben. Die
Oberfläche kommt im Servermodus vom Server, die Brücke von der App; fehlt einer Seite der
neue Stand, bleiben nur Fenstertitel und Menü.

## Zurück zu den lokalen Daten

Zwei Wege, beide mit derselben Rückfrage von Windows:

- Einstellungen → Sicherung → **Zurück zu den Daten auf diesem Rechner** (auch über den
  Hinweis in der Kopfzeile erreichbar).
- Datei → **Auf diesem Rechner arbeiten …**

Nach dem Bestätigen entfernt die App nur die Serveradresse aus der INI und startet mit den
lokalen Daten neu, so wie sie vor dem Verbinden waren. Es öffnet sich nie mehr als eine
Rückfrage zugleich, auch wenn Menü und Knopf gleichzeitig gewählt werden. Nach einem
„Abbrechen“ tut der Knopf 10 Sekunden lang nichts; das Menü fragt sofort. Bei älteren
Servern und auf der Seite „Keine Verbindung zum Server“ gibt es nur den Menüweg; er geht
auch, wenn der Server nicht erreichbar ist.

## Wo die App die Verbindung speichert

- **Die Verbindung:** `[Server] Adresse` in `%LOCALAPPDATA%\NebenkostenFix\einstellungen.ini`,
  neben dem Pfad zum Datenordner (`[Daten] Ordner`) und den übrigen Geräteeinstellungen.
- **Die Anmeldung am Server:** Cookies im WebView2-Profil
  `%LOCALAPPDATA%\NebenkostenFix\WebView2`.
- **Die Daten:** getrennt davon im Datenordner (Standard `Dokumente\NebenkostenFix`).
  Dort steht auch, ob der Hinweis „Bevor es losgeht“ bestätigt ist.

Daraus folgt:

- Wer den Datenordner löscht, bleibt verbunden. Erst beim nächsten **lokalen** Start
  erscheint der Hinweis wieder (dann mit dem Knopf „Mit einem Server verbinden“).
- Das Deinstallieren (setup.exe) fragt, ob auch die Einstellungen dieses Rechners weg
  sollen (Vorgabe Nein, still nur mit `/EINSTELLUNGEN=1`). Bei Ja entfernt es den
  Abschnitt `[Server]` der INI, den Ordner `WebView2` (Anmeldung am Server; das Profil
  teilt sich die lokale App, also gehen auch Thema, Schrift, Fortschritt von Assistenten
  und der Merker der Einführung), `konsole.log` und
  `app-einstellungen.json` (Merker der Update-Suche; nicht, wenn daneben eine
  `nebenkosten.db` liegt, der lokale Ordner also zugleich der Datenordner ist). `[Daten]`, den Datenordner und den Ausweich `Daten` lässt es immer
  stehen. Bei Nein startet eine Neuinstallation wieder verbunden.
- Store-Paket (MSIX): Windows lenkt Schreibzugriffe nach `%LOCALAPPDATA%` vermutlich in den
  Paketordner um und entfernt ihn beim Deinstallieren; eine Rückfrage gibt es dort nicht.
  Ausnahme: Eine INI am echten Ort aus einer früheren Exe-Installation bleibt. Unter Windows
  nicht geprüft.

Das ist gewollt: Die Wahl „lokal oder Server“ gehört zum Gerät, nicht zu den Daten. Wer
Daten löscht, verschiebt oder eine Sicherung einspielt, soll nicht nebenbei den Modus
wechseln, und Updates oder eine Neuinstallation behalten die Wahl. Der Nachteil: Den
Datenordner zu löschen ist kein frischer Anfang. Deshalb gibt es den sichtbaren Rückweg in
den Einstellungen. Von Hand geht es auch: in der INI den Abschnitt `[Server]` löschen (für
die Anmeldung zusätzlich den Ordner `WebView2`).

## Ältere Versionen

- **Ältere App, INI mit `[Server]`:** Eine ältere App kennt den Eintrag nicht und startet
  lokal. Der Eintrag bleibt stehen.
- **Neue App, älterer Server (ab 0.9):** `/api/health` antwortet gleich. Die alte
  Oberfläche ruft nur `speichern`, `oeffnen` und `extern_oeffnen`. Den Ordnerknopf der
  Sicherung zeigt sie trotzdem; ein Klick darauf tut nichts. Server vor 0.9 sind nicht
  geprüft.
- **Neue App, Server vor diesem Stand:** kein Hinweis in der Kopfzeile, keine Karte
  „Mit einem Server verbunden“; der Rückweg geht über das Menü.
- **App 0.18.0, neuer Server:** ebenso. Die Oberfläche zeigt nichts, was die Brücke nicht
  kann.
- Datenbank, Sicherungsformat und Umzugspaket sind unverändert. Alte Sicherungen lassen
  sich weiter einspielen.

## Noch offen

- Unter Windows nicht von Hand geprüft (siehe Prüfliste unten).
- Der Schalter „Updates automatisch“ aus den lokalen Einstellungen gilt im Servermodus
  nicht, weil der Datenordner zu bleibt. Die App sucht dort höchstens einmal in
  24 Stunden und fragt vor jeder Installation.
- Eine Server-Seite kann die Rückfrage zum Rückweg nach einer Ablehnung erneut öffnen, frühestens
  nach 10 Sekunden und nie zwei zugleich. Dazwischen sind Menü und Datei → Beenden erreichbar.
- Nicht im MVP: mehrere Server, Installer-Schalter
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
   auf einer bestimmten Seite öffnen, Datei → Drucken. Kein Feld zeigt „Choose File“ oder
   „No file chosen“; ein Datumsfeld öffnet mit deutschen Monatsnamen, und „12,5“ in einem
   Zahlenfeld bleibt nach dem Speichern 12,5.
6. **Neustart:** Verbinden startet die App neu, ebenso „Auf diesem Rechner arbeiten …“.
   Ein Update im Servermodus installieren (die Frage mit OK bestätigen): Danach startet die
   App von selbst wieder im Servermodus.
7. **Erster Start, Anzeige und Rückweg:**
   1. Frische Installation ohne Objekte (vorher deinstallieren und die Frage nach den
      Einstellungen mit Ja beantworten, sonst startet die App wieder verbunden), einmal mit
      leerem und einmal mit altem Datenordner, in dem der Hinweis schon bestätigt ist: Zuerst
      kommt nur „Wo sollen Ihre Daten liegen?“, der Fokus liegt auf „Auf diesem Rechner
      arbeiten“, Escape schließt nicht. Weder Hinweis noch Einführung springen dazwischen.
   2. „Mit einem NebenkostenFix-Server verbinden“: Einstellungen → Sicherung, Fokus im
      Adressfeld. **Zurück zur Startwahl** öffnet die Wahl wieder.
   3. „Auf diesem Rechner arbeiten“: Hinweis „Bevor es losgeht“ (beim alten Datenordner
      nicht), danach die Einführung wie bisher.
   4. Mit mindestens einem Objekt neu starten: keine Startwahl.
   5. Nach dem Verbinden: Die Kopfzeile zeigt „Verbunden mit …“, bei `http://` mit
      „(unverschlüsselt)“. Ein Klick darauf führt zur Karte „Mit einem Server verbunden“.
   6. In der Karte **Zurück zu den Daten auf diesem Rechner** → Abbrechen: Die App bleibt
      verbunden, ein zweiter Klick gleich danach tut nichts. Nach mehr als 10 Sekunden noch
      einmal → Bestätigen: Neustart lokal, die lokalen Daten sind unverändert (Prüfsumme
      wie unten).
   7. Der Menüweg geht weiter. Menü und Knopf kurz nacheinander: Es öffnet sich nur eine
      Rückfrage.
   8. Neue App gegen einen 0.18.0-Server: kein Hinweis in der Kopfzeile, der Menüweg geht.
   9. Datenordner bei bestehender Verbindung löschen: Die App bleibt verbunden (gewollt,
      siehe „Wo die App die Verbindung speichert“).
   10. Lokal mit Objekten: **Datei → Mit einem Server verbinden …** führt zur Karte, Fokus
      im Adressfeld. Eine Adresse ohne Schema zu einem Server ohne https (etwa
      `192.168.1.10:8080`): Die Meldung steht rot mit Warnsymbol, die App fragt „Mit
      http://… unverschlüsselt verbinden?“. Ja verbindet, Nein lässt alles, wie es war.
8. **Deinstallation:** Bei bestehender Verbindung deinstallieren, die Frage nach den
   Einstellungen mit Nein beantworten: INI mit `[Server]`, `WebView2` und `konsole.log`
   bleiben. Neu installieren, verbinden, wieder deinstallieren, diesmal mit Ja: `[Server]`,
   `WebView2` und `konsole.log` sind weg; `[Daten]`, der Datenordner und, falls vorhanden,
   der Ordner `Daten` unter `%LOCALAPPDATA%\NebenkostenFix` bleiben.

**Abwärtskompatibilität (von Hand):**

- Eine 0.11-Installation mit erfundenen Daten auf den neuen Stand aktualisieren: Die App
  startet lokal, alle Daten sind da.
- Auf einen Server umschalten und zurück: Der lokale Datenordner ist bytegleich (vorher
  und nachher eine Prüfsumme über den Ordner bilden, etwa mit `Get-FileHash`).
- Den neuen Stand deinstallieren (Frage nach den Einstellungen mit Nein) und 0.11 neu
  installieren: Die App startet lokal, `[Server]` steht weiter in der INI.
- Eine alte Sicherung einspielen.
