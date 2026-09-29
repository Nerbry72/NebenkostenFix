# Sicherheit

## Eine Lücke melden

Bitte **kein öffentliches Issue**. Melden Sie die Lücke vertraulich über
[„Report a vulnerability“](https://github.com/Nerbry72/NebenkostenFix/security/advisories/new)
(Reiter *Security* des Repositorys).

Hilfreich sind:

- betroffene Version und Installationsweg (Docker, Windows-App, Store),
- die Schritte, mit denen sich die Lücke zeigen lässt,
- was ein Angreifer damit erreichen könnte.

NebenkostenFix ist ein Freizeitprojekt. Eine erste Antwort kommt in der Regel innerhalb einer
Woche. Ist die Lücke bestätigt, erscheint die Behebung als neues Release, und die Meldung
wird danach veröffentlicht. Wer möchte, wird dort genannt.

## Unterstützte Versionen

Sicherheitskorrekturen gibt es nur für die jeweils neueste Version. Die Windows-App und
Docker weisen auf neue Versionen hin (abschaltbar unter Einstellungen → Updates).

## Was die Anwendung selbst tut

- Ohne Anmeldung öffnet sich keine Seite außer `/api/health`.
- Nach fünf Fehlversuchen je Konto oder zwanzig je Adresse ist die Anmeldung 15 Minuten gesperrt.
- Schreibende Anfragen von fremden Seiten lehnt sie ab. Jede Antwort trägt eine
  Content-Security-Policy ohne fremde Quellen.
- Der Container läuft nicht als root.
- Updates der Windows-App sind mit Ed25519 signiert. Ein verändertes Manifest oder ein
  Installer mit falscher Prüfsumme wird verworfen, bevor irgendetwas ausgeführt wird.
