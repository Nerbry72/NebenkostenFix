# Qualitaetstor: laeuft mit dem Python des Aufrufers (venv oder CI).
#   make install-dev && make check

PY := python

.PHONY: check lint ui test schwelle kern sicherheit audit install-dev e2e rauchtest

install-dev:
	$(PY) -m pip install -q -r requirements-dev.txt

KERN := nebenkostenfix/rechenkern.py nebenkostenfix/abrechnungsdaten.py nebenkostenfix/billing_engine.py

lint:
	env PYTHONDONTWRITEBYTECODE=1 $(PY) -m compileall -q $(KERN)
	env PYTHONDONTWRITEBYTECODE=1 $(PY) -m ruff check $(KERN)

test:
	env PYTHONDONTWRITEBYTECODE=1 $(PY) -m pytest

# Beschriftungen gegen den Begriffskatalog (NK-074). Der Test in
# tests/test_ui_konsistenz.py prueft dasselbe im Testlauf; dieser
# Schritt liefert den lesbaren Bericht im make check davor und bricht
# mit Zeilenangaben ab, wenn eine Beschriftung abweicht.
ui:
	env PYTHONDONTWRITEBYTECODE=1 $(PY) scripts/ui_beschriftungen.py

# Harte Schwelle je Datei (NK-032). Laeuft nach test, weil es die
# Datendatei auswertet, die pytest-cov gerade hinterlassen hat.
schwelle:
	env PYTHONDONTWRITEBYTECODE=1 $(PY) scripts/einzelschwelle.py

# Zweigabdeckung des Rechenkerns (NK-037). Eigener Lauf, weil coverage.py
# branch nur projektweit kennt und der Gesamtwert dadurch faellt -- das waere
# eine andere Karte. Hier zaehlt, dass jeder Zweig, der Geld verteilt, einmal
# genommen wurde. Die Datendatei liegt getrennt, sonst ueberschreibt dieser
# Lauf die des Gesamtlaufs und `make schwelle` misst die falsche Menge.
# Die Dateien stehen einzeln da, damit nur Kerntests zaehlen -- ein
# Integrationstest wuerde Zweige gratis mitnehmen, die niemand geprueft hat.
# WER EINE NEUE KERNTESTDATEI ANLEGT, TRAEGT SIE HIER EIN. Sonst faellt die
# Zweigabdeckung um den ungetesteten Block, obwohl die Tests gruen sind.
kern:
	env PYTHONDONTWRITEBYTECODE=1 COVERAGE_FILE=/tmp/.coverage.kern $(PY) -m pytest \
	  -o addopts="" -p no:cacheprovider \
	  tests/test_rechenkern.py tests/test_billing_engine_characterization.py \
	  tests/test_heizkostenverteilung.py tests/test_warmwassertrennung.py \
	  tests/test_allgemeinanteil_zeitschnitt.py \
	  tests/test_leerstand_personenschluessel.py \
	  tests/test_zwischenablesung.py tests/test_co2_aufteilung.py \
	  tests/test_ht_nt.py tests/test_golden_fixtures.py \
	  tests/test_allgemein_belegungsabschnitte.py tests/test_leerstand_einzige_wohnung.py \
	  tests/test_leerstand_zaehlerzweig.py tests/test_wohnungsrechnung_leerstand.py \
	  tests/test_rechnungen_bestand.py tests/test_rechnungsabdeckung.py \
	  tests/test_grundpreis_leerstand.py tests/test_stichtagswerte.py \
	  tests/test_allgemein_messabschnitte.py tests/test_allgemein_negativ.py \
	  tests/test_zahlformat_umlage.py \
	  tests/test_vorauszahlung.py tests/test_jahressprung.py \
	  tests/test_heizung_kostenarten.py \
	  -q --no-header \
	  --cov=nebenkostenfix.rechenkern --cov-branch --cov-report=term-missing --cov-fail-under=95

# NK-146: statische Sicherheitspruefung des Quellcodes. Laeuft offline und
# ist deshalb Teil von check. Ausnahmen stehen im Code (# nosec Bxxx mit
# Begruendung in der Zeile darueber), der Rest bricht ab.
sicherheit:
	env PYTHONDONTWRITEBYTECODE=1 $(PY) -m bandit -q -c pyproject.toml -r .

# NK-146: bekannte Schwachstellen der gepinnten Abhaengigkeiten. Braucht
# Netz (PyPI/OSV) und laeuft deshalb in der CI und von Hand, nicht in check.
audit:
	$(PY) -m pip_audit -r requirements.txt

check:
	$(MAKE) install-dev lint ui sicherheit test schwelle kern

# NK-031: der einzige Lauf, der NICHT durch geht. Er baut das Abbild,
# in dem sonst sitzt -- also Wirt statt Container, eigener
# Compose-Projektname nk-e2e, eigener Port. Nicht Teil von check: ein Bau ohne
# Cache dauert Minuten, das darf kein Commit kosten.
# HOST_PY, nicht $(PY): auf dem Wirt heisst es python3.
HOST_PY := python3

e2e:
	@if [ -n "$(wildcard /.dockerenv)" ]; then \
	  echo "make e2e gehoert auf den Wirt, nicht in den Container:"; \
	  echo "es baut das Abbild, in dem es sonst selbst saesse."; \
	  exit 1; \
	fi
	$(HOST_PY) scripts/e2e.py $(E2E_ARGS)

# DOM-Rauchtest des Design-Systems (NK-067). Wirtswerkzeug wie e2e:
# im Container gibt es kein Node. Die CI faehrt ihn in rundgang.yml (F-108);
# die statischen Zusicherungen laufen zusaetzlich als pytest in `make check`
# (tests/test_ui_konsistenz.py).
rauchtest:
	@if [ -n "$(wildcard /.dockerenv)" ]; then \
	  echo "make rauchtest gehoert auf den Wirt, nicht in den Container:"; \
	  echo "im Container gibt es kein Node."; \
	  exit 1; \
	fi
	node scripts/rauchtest_design.js
