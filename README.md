# NebenkostenFix

Nebenkostenabrechnung für private Vermieter mit ein bis fünfzehn Wohnungen.
Immobilien, Wohnungen, Mieter, Zählerstände und Rechnungen liegen an einer Stelle,
am Ende steht eine fertige Abrechnung als PDF. Die Regeln folgen BetrKV, HeizkostenV
und CO2KostAufG.

- **Immobilien und Wohnungen** mit beliebig vielen Einheiten und Umlageschlüsseln
- **Mieter** mit Ein- und Auszug, anteilige Abrechnung und Leerstand inbegriffen
- **Rechnungen** einzeln, als Sammelrechnung oder als Tabelle, Belege als PDF oder Foto
- **Zähler** mit Beweisfoto, Zwischenablesung und Doppeltarif (HT/NT)
- **Heizkosten** nach HeizkostenV, CO₂-Kostenaufteilung nach Stufenmodell
- **Abrechnung** als PDF mit Deckblatt, Anschreiben und Zahlungs-QR-Code (GiroCode)
- **Assistent „Jahr abrechnen“**, Beispielimmobilie, Hilfe mit Begriffen A–Z
- **Import** aus Excel oder CSV, **Umzug** zwischen Rechnern als eine `.nkfix`-Datei
- **Anmeldung** mit Benutzername und Passwort, bis zu zwei Konten

Es gibt NebenkostenFix in zwei Formen:

| | Docker | Windows-App |
| --- | --- | --- |
| für | NAS (z. B. Synology), Raspberry Pi, Heimserver | einen einzelnen Windows-PC |
| Zugriff | Browser, von jedem Gerät im Netz | eigenes Fenster auf dem PC |
| Installation | `docker compose up -d` | `NebenkostenFix-<Version>-Setup.exe` |

Beide nutzen denselben Datenbestand. Ein Umzug in beide Richtungen ist mit einer
Datei erledigt (siehe [Umzug](#umzug-auf-einen-anderen-rechner)).

---

## Installation mit Docker

Nötig ist ein Rechner mit Docker und dem Compose-Plugin. Eine Datenbank, einen
Webserver, Python oder eine `.env` braucht es nicht. Das Abbild gibt es für amd64 und
arm64.

**1. Ordner anlegen und `docker-compose.yml` hineinlegen**

```bash
mkdir nebenkostenfix && cd nebenkostenfix
# docker-compose.yml aus diesem Repository hierher kopieren
```

**2. Anmelden bei der Registry (solange das Repository privat ist)**

Das Abbild liegt unter `ghcr.io/nerbry72/nebenkostenfix`. Solange Repository und Paket
privat sind, braucht `docker` einmalig eine Anmeldung. Dafür dient ein GitHub-Token mit
dem Recht `read:packages`:

```bash
docker login ghcr.io -u <github-name>
```

**3. Starten**

```bash
docker compose up -d
```

Neben der Compose-Datei entsteht der Datenordner `daten/`. Wer aus dem Quellcode
bauen will, startet mit `docker compose up -d --build`.

**4. Einrichten im Browser**

`http://<rechner>:6060` öffnen. Solange es noch kein Konto gibt, zeigt die Anwendung die
Einrichtung. Dort vergeben Sie Benutzername und Passwort (mindestens zehn Zeichen)
und geben den **Einmal-Code** ein. Der Code steht nur auf dem Server, damit sich niemand
im Netz ein Konto anlegen kann:

```bash
cat daten/ERSTEINRICHTUNG-CODE.txt
docker compose logs web | grep Einmal-Code
```

Nach fünf falschen Versuchen gilt ein neuer Code. Nach der Einrichtung verschwindet die
Datei. Den Sitzungsschlüssel erzeugt die Anwendung selbst, er liegt in `daten/secret_key`.

**5. Prüfen**

```bash
docker compose ps                         # STATUS: Up (healthy)
curl http://localhost:6060/api/health     # {"status":"ok", ...}
```

### Synology (ohne Kommandozeile)

1. **Ordner anlegen:** In der File Station einen Ordner anlegen, z. B. `docker/nebenkostenfix`.
2. **Projekt anlegen:** Container Manager → Projekt → Erstellen. Als Name `nebenkostenfix`
   eintragen, als Pfad den Ordner aus Schritt 1. Bei Quelle „docker-compose.yml hochladen“
   wählen.
3. **Nutzer eintragen:** In der Compose-Datei (oder einer `.env` daneben) `PUID` und `PGID`
   auf den DSM-Nutzer setzen, dem der Ordner gehört (per SSH: `id <name>`). Sonst kann der
   Container nicht in `daten/` schreiben.
4. **Registry:** Solange das Paket privat ist, unter Container Manager → Registry →
   Einstellungen `ghcr.io` mit GitHub-Name und Token hinzufügen.
5. **Starten:** Mit „Weiter“ bis „Fertig“. Der Container Manager lädt das Abbild und startet
   es.
6. **Einmal-Code:** In der File Station `docker/nebenkostenfix/daten/ERSTEINRICHTUNG-CODE.txt`
   öffnen.
7. **Einrichten:** `http://<synology>:6060` im Browser öffnen, Konto anlegen und den Code
   eintragen.

### Einstellungen

Die Anwendung läuft ohne jede Einstellung. Wer etwas ändern will, legt eine `.env` neben
die Compose-Datei. `.env.example` erklärt jeden Wert. Die wichtigsten:

| Variable | Wirkung | Standard |
| --- | --- | --- |
| `APP_PORT` | Port auf dem Wirt | `6060` |
| `PUID` / `PGID` | Nutzer, dem der Datenordner gehört | `1000` |
| `NK_VERSION` | Welche Version Compose startet | `latest` |
| `BEHIND_HTTPS` | `1` hinter einem HTTPS-Proxy | aus |
| `ERLAUBTE_URSPRUENGE` | öffentliche Adresse, wenn der Proxy den Host umschreibt | leer |
| `SITZUNG_LEERLAUF_MIN` | Abmeldung nach so vielen Minuten ohne Aktivität | `60` |
| `MAX_UPLOAD_MB` | größter Beleg | `32` |
| `BACKUP_ZIELE` | zusätzliche Ordner für Sicherungen, mit `:` getrennt | leer |
| `VERMIETER_NAME` / `VERMIETER_IBAN` | Zahlungs-QR-Code auf der Abrechnung | leer |
| `LOG_LEVEL` | `DEBUG` … `CRITICAL` | `INFO` |

### HTTPS und Reverse Proxy

Im eigenen LAN reicht `http://`. Passwort und Mieterdaten gehen dann aber im Klartext
durchs Netz, und die Anwendung warnt beim Start. Für den Zugriff von außen gehört ein
Reverse Proxy mit Zertifikat davor:

- **Synology:** Systemsteuerung → Anmeldeportal → Erweitert → Reverse Proxy. Als Quelle
  `https://nk.<ihre-domain>:443` eintragen, als Ziel `http://localhost:6060`.
- **Caddy:**

  ```
  nk.example.org {
      reverse_proxy 127.0.0.1:6060
  }
  ```

- **nginx:** `proxy_pass http://127.0.0.1:6060;` mit `proxy_set_header Host $host;`,
  `proxy_set_header X-Forwarded-Proto https;` und `client_max_body_size 32m;`.

Danach in der `.env` `BEHIND_HTTPS=1` setzen und den Port nur noch lokal binden:
`APP_PORT=127.0.0.1:6060`.

### Betrieb

```bash
docker compose logs -f web                     # Protokoll mitlesen
docker compose restart web                     # neu starten
docker compose down                            # anhalten, Daten bleiben
docker compose pull && docker compose up -d    # Update auf die neueste Version
```

Nach einem Update passt die Anwendung das Datenbankschema beim Start selbst an und sichert
vorher automatisch. Eine bestimmte Version starten Sie mit `NK_VERSION=0.9.1` in der `.env`.

Tritt ein unerwarteter Fehler auf, zeigt die Anwendung eine **Vorgangsnummer**. Unter dieser
Nummer steht im Protokoll, was passiert ist:

```bash
grep A1B2C3D4 daten/nebenkosten.log
```

### Konten auf der Kommandozeile

Ein zweites Konto legen Sie in der Oberfläche unter Einstellungen an. Für den Notfall gibt
es die Kommandozeile:

```bash
docker compose exec web flask users list
docker compose exec web flask users passwd <name>    # Passwort vergessen, hebt auch eine Sperre auf
docker compose exec web flask users add <name>
docker compose exec web flask users disable <name>
```

---

## Windows-App

Für einen einzelnen PC (Windows 10 ab 1809 oder Windows 11) gibt es einen Installer. Er
braucht weder Python noch Docker noch eine Kommandozeile.

1. Unter **Releases** die neueste `NebenkostenFix-<Version>-Setup.exe` herunterladen.
2. Ausführen und den Schritten folgen. Die App startet in ihrem eigenen Fenster (Edge WebView2).
3. Beim ersten Start ein Konto anlegen. Auf dem eigenen PC braucht das keinen Einmal-Code.

- **Programm:** `C:\Program Files\NebenkostenFix`
- **Daten:** `Dokumente\NebenkostenFix`, im Installer änderbar und nie im Programmordner.
  Liegt „Dokumente“ in OneDrive, schlägt die App einen lokalen Ort vor.
- **Update:** Die neue Setup-Exe über die alte installieren. Die Daten bleiben, vorher wird
  gesichert.
- **Deinstallation:** Die Daten bleiben stehen, der Deinstaller sagt, wo sie liegen.
- **Passwort vergessen:** Menü „Hilfe“.

Die Prüfsumme jeder Setup-Exe steht im Release (`SHA256SUMS.txt`):

```powershell
Get-FileHash .\NebenkostenFix-0.9.1-Setup.exe -Algorithm SHA256
```

---

## Daten

### Wo die Daten liegen

Alles liegt in einem Ordner: bei Docker in `daten/` neben der Compose-Datei (im Container
`/data`), bei Windows in `Dokumente\NebenkostenFix`.

| Pfad | Inhalt |
| --- | --- |
| `nebenkosten.db` | die gesamte Datenbank (SQLite) |
| `belege/` | Rechnungen, Verträge, Zählerfotos und Abrechnungs-PDFs |
| `backups/` | Sicherungen |
| `import/` | hier abgelegte `.nkfix`-Pakete bietet die Übernahme zur Auswahl an |
| `secret_key` | Sitzungsschlüssel, entsteht beim ersten Start |
| `nebenkosten.log` | Protokoll, bei 5 MB umgeschichtet, höchstens fünf alte Stände |

Die Anwendung spricht selbst kein SMB oder NFS. Soll der Ordner auf einem NAS liegen,
binden Sie ihn dort ein oder betreiben den Container direkt auf dem NAS.

### Sichern und Zurückholen

Eine Sicherung ist eine `.nkfix`-Datei, also ein ZIP. Darin stecken die Datenbank, alle
Belege, Vermieterdaten, Logo und Lizenz sowie eine Prüfsumme je Datei. In der Oberfläche
steht das unter Einstellungen → Sicherung. Auf der Kommandozeile:

```bash
docker compose exec web flask backup create
docker compose exec web flask backup info /data/backups/sicherung-20260315-030000.nkfix
```

Zurückholen ersetzt Datenbank und Belege, die Anwendung sollte dabei nicht laufen:

```bash
docker compose stop web
docker compose run --rm --no-deps web flask backup restore /data/backups/sicherung-20260315-030000.nkfix
docker compose up -d
```

Vor dem Ersetzen prüft die Anwendung jede Prüfsumme und sichert den aktuellen Stand als
`sicherung-vor-einspielen-*.nkfix`. Ein älteres Archiv hebt sie auf den aktuellen
Schemastand. Ein Archiv aus einer neueren Version lehnt sie ab.

Eine Sicherung auf derselben Platte schützt nicht vor einem Plattenschaden. Kopieren Sie sie
deshalb auf einen anderen Rechner oder eine externe Platte, oder tragen Sie ein zweites Ziel
in `BACKUP_ZIELE` ein.

### Umzug auf einen anderen Rechner

Dieselbe `.nkfix`-Datei ist auch das Umzugspaket, zwischen Docker und Windows in beide
Richtungen.

1. **Alter Rechner:** Einstellungen → Sicherung → „Alles exportieren“
   (oder `docker compose exec web flask umzug export`).
2. **Neuer Rechner, frisch installiert:** Auf der Einrichtungsseite „Daten aus einer anderen
   Installation übernehmen“ wählen. Danach melden Sie sich mit dem bisherigen Konto an.
3. **Neuer Rechner, schon in Benutzung:** Einstellungen → Sicherung → „Daten übernehmen
   (ersetzt alles)“. Der jetzige Stand wird vorher gesichert.

Große Pakete lädt der Browser in Stücken hoch. Nach einem Abbruch geht es an derselben
Stelle weiter. Unter Docker können Sie das Paket auch nach `daten/import/` legen. Nicht im
Paket sind Sitzungsschlüssel, Sicherungsziele und Anmeldesperren.

### Daten aus Excel übernehmen

In den Bereichen Immobilien, Mieter, Zähler, Rechnungen und Zahlungen führt „Aus Excel
importieren“ durch drei Schritte: Vorlage (XLSX oder CSV), Zuordnung der Spalten und ein
Probelauf mit Fehlern je Zeile. Übernommen wird nur, wenn keine Zeile einen Fehler hat.

---

## Sicherheit

- Ohne Anmeldung öffnet sich keine Seite. Einzige Ausnahme ist `/api/health`.
- Nach 5 Fehlversuchen für ein Konto (oder 20 von einer Adresse) ist die Anmeldung
  15 Minuten gesperrt.
- Schreibende Anfragen von fremden Seiten lehnt die Anwendung ab. Jede Antwort trägt eine
  Content-Security-Policy ohne fremde Quellen.
- Der Container läuft nicht als root.
- Die Anwendung ruft nie von selbst nach Hause.

Sicherheitslücken bitte nicht als öffentliches Issue melden, sondern direkt an den
Maintainer.

---

## Entwicklung

### Voraussetzungen

Python 3.11. Alle Werkzeuge kommen aus `requirements-dev.txt`.

```bash
python3.11 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
make install-dev
make check          # Lint, Glossar, Bandit, Tests, Einzelschwelle, Abdeckung Rechenkern
flask --app app run --port 6070
```

Weitere Prüfungen:

| Befehl | Was |
| --- | --- |
| `make audit` | bekannte Lücken in den Abhängigkeiten (pip-audit) |
| `python scripts/rundgang.py` | Browser-Rundgang in drei Breiten (Playwright) |
| `python desktop.py` | Windows-App aus den Quellen starten |

Tests laufen nie gegen einen Datenordner mit echten Daten.

### Arbeitsablauf

`main` ist immer veröffentlichbar. Direkte Pushes auf `main` gibt es nicht.

1. Einen Feature-Branch von `main` abzweigen, z. B. `feature/zaehler-import` oder
   `fix/pdf-umbruch`.
2. Committen und pushen. Die CI (`ci.yml`) prüft jeden Push.
3. Einen Pull Request nach `main` öffnen. Zusätzlich laufen der Windows-Bau mit
   Installer-, Update- und Umzugsprobe (`windows.yml`) und der Browser-Rundgang
   (`rundgang.yml`).
4. `SOFTWARE_VERSION` in `abrechnung_version.py` anheben. Die CI lehnt einen Pull Request ab,
   dessen Version schon veröffentlicht ist.
5. Nach dem Merge baut `release.yml` alles und veröffentlicht es.

### Versionen und Releases

Die Versionsnummer steht an genau einer Stelle: `SOFTWARE_VERSION` in `abrechnung_version.py`
(Schema `x.y.z`). Jeder Merge nach `main` löst `release.yml` aus:

1. Alle Tests (Linux und Windows), Lint, Bandit, pip-audit, Secret-Scan und
   Browser-Rundgang. Ist eine Prüfung rot, wird nichts veröffentlicht.
2. Windows-App bauen (PyInstaller und Inno Setup), still installieren, über eine Vorversion
   aktualisieren und wieder deinstallieren.
3. Docker-Abbild bauen, Rauchtest, dann für amd64 und arm64 nach
   `ghcr.io/nerbry72/nebenkostenfix:<version>` und `:latest` schieben.
4. GitHub-Release `v<version>` mit `NebenkostenFix-<version>-Setup.exe` und `SHA256SUMS.txt`
   anlegen.

### Aufbau

| Pfad | Inhalt |
| --- | --- |
| `app.py` | Flask-Anwendung und API |
| `rechenkern.py`, `betrkv.py`, `heizung.py`, `co2.py` | Abrechnungsregeln |
| `models.py`, `migrations/` | Datenmodell (SQLAlchemy) und Schema-Wanderungen (Alembic) |
| `pdf_generator.py`, `pdf_cover_page.py` | PDF-Abrechnung (reportlab) |
| `backup.py`, `umzug.py` | Sicherung, Einspielen, Umzugspaket |
| `desktop.py`, `packaging/windows/` | Windows-App und Installer |
| `static/` | Oberfläche (HTML, CSS, JavaScript ohne Framework) |
| `docs/glossar.md` | verbindliche Begriffe der Oberfläche, gegen die `make ui` prüft |
| `tests/` | pytest |
