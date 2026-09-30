# Mitmachen

Danke, dass Sie NebenkostenFix besser machen wollen. Fehlerberichte, Ideen, Korrekturen an
Texten und Pull Requests sind willkommen.

## Bevor Sie anfangen

- **Fehler:** über [„Fehler melden“](https://github.com/Nerbry72/NebenkostenFix/issues/new?template=fehler.yml).
  In der App füllt Hilfe → „Über NebenkostenFix“ → „Fehler melden“ Version und System schon vor.
- **Ideen und Fragen:** in den [Discussions](https://github.com/Nerbry72/NebenkostenFix/discussions).
  Bei größeren Änderungen bitte erst dort fragen, dann bauen. Das spart Ihnen Arbeit, falls
  etwas nicht passt.
- **Sicherheitslücken:** nie als Issue, siehe [SECURITY.md](SECURITY.md).
- **Keine echten Mieterdaten**, weder in Issues noch in Tests oder Screenshots. Die
  Beispielimmobilie der App ist dafür gedacht.

## Entwicklungsumgebung

Python 3.11. Alle Werkzeuge kommen aus `requirements-dev.txt`.

```bash
python3.11 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
make install-dev
flask --app app run --port 6070
```

## Regeln für Änderungen

1. **Ein Branch je Thema**, von `main` abgezweigt, z. B. `fix/pdf-umbruch` oder
   `feature/zaehler-import`. `main` ist immer veröffentlichbar.
2. **Tests zuerst.** Jede Fehlerbehebung bringt einen Test mit, der ohne die Behebung rot ist.
   Jede neue Abrechnungsregel bringt einen Fall mit Rechenweg mit.
3. **`make check` muss grün sein.** Das sind Lint, Glossar, Bandit, Tests, Einzelschwelle und
   Abdeckung des Rechenkerns, dieselben Prüfungen wie in der CI.
4. **Begriffe aus dem Glossar.** Jede Beschriftung der Oberfläche folgt
   [`docs/glossar.md`](docs/glossar.md), `make ui` prüft das. Die Oberfläche siezt, Knöpfe
   beginnen mit einem Verb.
5. **Tests laufen nie gegen echte Daten.** Die Fixtures legen einen eigenen Datenordner an.

Die CI prüft jeden Pull Request unter Linux und Windows. Dazu gehören der Bau des Installers
mit Update- und Umzugsprobe und ein Browser-Rundgang in drei Breiten. Ein Release entsteht
erst, wenn `SOFTWARE_VERSION` in `abrechnung_version.py` angehoben und nach `main` gemergt ist.

## Lizenz

Beiträge stehen unter derselben Lizenz wie das Projekt, der
[GNU General Public License v3.0](LICENSE).
