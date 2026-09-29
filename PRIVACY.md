# Datenschutz

**Kurz: Ihre Daten bleiben bei Ihnen.** NebenkostenFix hat keinen Server, kein Konto beim
Herausgeber, keine Telemetrie und keine Werbung.

## Was wo liegt

Alles, was Sie eingeben, liegt in einem Ordner auf Ihrem Rechner oder Server: Immobilien,
Mieter, Zählerstände, Rechnungen, Belege und Abrechnungen. Bei Docker ist das `daten/`
neben der Compose-Datei, bei Windows `Dokumente\NebenkostenFix`. Der Herausgeber sieht davon
nichts. Er kann die Daten auch nicht wiederherstellen, wenn sie verloren gehen. Legen Sie
deshalb Sicherungen an (Einstellungen → Sicherung).

## Wann die Anwendung ins Internet geht

Genau in einem Fall von sich aus:

- **Suche nach Updates.** Beim Start, höchstens einmal in 24 Stunden, lädt die Anwendung die
  Datei `update.json` des neuesten Releases von GitHub. Dabei wird nichts übertragen außer der
  Anfrage selbst. GitHub sieht, wie bei jedem Seitenaufruf, Ihre IP-Adresse
  ([Datenschutzerklärung von GitHub](https://docs.github.com/de/site-policy/privacy-policies/github-general-privacy-statement)).
  Abschalten lässt sich das unter Einstellungen → Updates. Die Version aus dem Microsoft
  Store sucht nie selbst, dort aktualisiert der Store.

Alles andere geschieht nur auf Ihren Klick: ein Update herunterladen, die Projektseite,
„Fehler melden“ oder Ko-fi im Browser öffnen. „Fehler melden“ füllt nur Version,
Installationsweg und Betriebssystem vor, nie etwas aus Ihren Daten. Was Sie ins Issue
schreiben, ist öffentlich.

## Microsoft Store

Wer die App aus dem Microsoft Store installiert, dessen Installation verarbeitet Microsoft
nach den eigenen Bedingungen. Der Herausgeber erhält daraus nur zusammengefasste Zahlen
(z. B. Installationen je Land), keine Namen.

## Fragen

Über die [Discussions](https://github.com/Nerbry72/NebenkostenFix/discussions) oder ein Issue.
