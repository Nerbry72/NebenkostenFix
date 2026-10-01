# Store-Eintrag Deutsch (NK-172)

Texte für das Partner Center, Store listings → Deutsch (Deutschland).
Jeder Abschnitt ist ein Feld. `tests/test_store_eintrag.py` prüft die
Längengrenzen des Partner Centers und dass der Haftungshinweis wörtlich
drinsteht (`nebenkostenfix/haftung.py`).

## Beschreibung

NebenkostenFix erstellt die Nebenkostenabrechnung für private Vermieter mit einer bis fünfzehn Wohnungen. Immobilien, Wohnungen, Mieter, Zählerstände und Rechnungen liegen an einer Stelle. Am Ende steht eine fertige Abrechnung als PDF, mit Deckblatt, Anschreiben und Zahlungs-QR-Code.

Die Regeln folgen der Betriebskostenverordnung (BetrKV), der Heizkostenverordnung (HeizkostenV) und dem Kohlendioxidkostenaufteilungsgesetz (CO2KostAufG). Jede Kostenart und jeder Umlageschlüssel ist in der Abrechnung nachvollziehbar, auch bei Ein- und Auszug im Jahr und bei Leerstand.

Ihre Daten bleiben bei Ihnen: kein Konto beim Herausgeber, kein Server, keine Telemetrie, keine Werbung. Alles liegt in einem Ordner auf Ihrem PC, standardmäßig unter Dokumente\NebenkostenFix. Updates kommen über den Microsoft Store.

Für den Einstieg gibt es eine Beispielimmobilie, den Assistenten „Jahr abrechnen“ und eine Hilfe mit Begriffen von A bis Z. Eine Sicherung oder ein Umzug auf einen anderen Rechner ist eine einzige Datei. Dieselbe Datei nimmt auch die Docker-Fassung für NAS und Heimserver an.

NebenkostenFix ist freie Software unter der GPL-3.0. Der Quelltext liegt auf GitHub.

NebenkostenFix ist kostenlos und wird ohne Gewähr bereitgestellt. Der Entwickler übernimmt keine Haftung für die Richtigkeit Ihrer Abrechnungen, soweit das Gesetz das zulässt. Die Anwendung ist keine Rechtsberatung. Prüfen Sie jede Abrechnung selbst, bevor Sie sie verschicken.

## Kurzbeschreibung

Die Nebenkostenabrechnung für private Vermieter. Kostenlos, und Ihre Daten bleiben bei Ihnen.

## Neuerungen in dieser Version

Version 0.11.0: Die Abrechnung rechnet Zeiträume, Leerstand und Mieterwechsel genauer.

- Zeiträume über zwölf Monate werden vollständig gerechnet, mit Hinweis auf § 556 BGB.
- Der Auszugstag ist der letzte Miettag. Der Nachmieter beginnt am Tag danach.
- Vorschlag für den Abrechnungszeitraum, mit Begründung und der Schaltfläche „Übernehmen“.
- Das Abrechnungsjahr kann je Immobilie an einem anderen Tag als dem 01.01. beginnen.
- Leerstand: Den Anteil einer leeren Wohnung trägt der Vermieter, auch bei Zählern und beim Grundpreis.
- Fehlt der Stand des Wärmezählers am Stichtag, wird er nach Gradtagszahlen geschätzt.
- Meldungen sind kürzer, höchstens drei auf einmal, jede mit „Was tun:“.
- Stromzähler heißen in der Oberfläche „Strom“.

## Produktmerkmale

- Immobilien und Wohnungen mit beliebig vielen Einheiten und Umlageschlüsseln
- Mieter mit Ein- und Auszug, anteilige Abrechnung und Leerstand inbegriffen
- Rechnungen einzeln, als Sammelrechnung oder aus einer Tabelle
- Belege als PDF oder Foto
- Zähler mit Beweisfoto, Zwischenablesung und Doppeltarif
- Heizkosten nach HeizkostenV
- CO2-Kostenaufteilung nach dem Stufenmodell
- Abrechnung als PDF mit Deckblatt, Anschreiben und Zahlungs-QR-Code (GiroCode)
- Assistent „Jahr abrechnen“ und Beispielimmobilie
- Hilfe mit Begriffen von A bis Z in der App
- Import aus Excel oder CSV
- Sicherung und Umzug als eine Datei
- Anmeldung mit Benutzername und Passwort
- Keine Telemetrie, keine Werbung, kein Konto beim Herausgeber

## Suchbegriffe

- Nebenkostenabrechnung
- Betriebskosten
- Vermieter
- Heizkostenabrechnung
- Mietverwaltung
- Hausverwaltung
- Nebenkosten

## Copyright

© 2026 NerbrY72. Freie Software unter der GNU General Public License 3.0.

## Zusätzliche Lizenzbedingungen

NebenkostenFix steht unter der GNU General Public License, Version 3 (GPL-3.0): https://github.com/Nerbry72/NebenkostenFix/blob/main/LICENSE
Die Lizenzen der mitgelieferten Software stehen in der App unter Hilfe → Über NebenkostenFix.
