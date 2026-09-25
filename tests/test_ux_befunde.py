"""Befunde aus dem Rundgang als neuer Nutzer (NK-154, 2026-09-25).

Ein Klickrundgang mit leerem Datenordner fand sechs Fehler, die kein
Wächter sah: Sicherungsfelder in der falschen Karte, ungestaltete
Passwortfelder, eine leere Statistikseite, die den Weg zur
Beispielimmobilie versperrte, ein grüner Haken „nichts fällig“ ohne einen
einzigen Mieter, Umschrift in sichtbarem Text und Entwicklersprache.
"""

from __future__ import annotations

import re
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
SEITE = (WURZEL / 'static' / 'index.html').read_text(encoding='utf-8')
SKRIPT = (WURZEL / 'static' / 'app.js').read_text(encoding='utf-8')
STIL = (WURZEL / 'static' / 'style.css').read_text(encoding='utf-8')


def _karte(ueberschrift: str) -> str:
    """Der HTML-Text der Einstellungskarte mit dieser Überschrift."""
    beginn = SEITE.index(f'<h3>{ueberschrift}</h3>')
    ende = SEITE.find('class="dashboard-card', beginn)
    return SEITE[beginn:ende if ende != -1 else len(SEITE)]


def test_sicherungsfelder_stehen_in_der_sicherungskarte():
    sicherung = _karte('Sicherung')
    konto = _karte('Konto')
    for kennung in ('sicherung-erlaubt', 'sicherung-verschluesseln',
                    'sicherung-passphrase', 'sicherung-festplatte'):
        assert f'id="{kennung}"' in sicherung, kennung
        assert f'id="{kennung}"' not in konto, kennung


def test_jedes_eingabefeld_im_formular_ist_gestaltet():
    """Jede Feldart, die index.html in einem Formular benutzt, hat eine Regel."""
    arten = set(re.findall(r'<input[^>]*type="([a-z]+)"', SEITE))
    ohne_regel = {'checkbox', 'file', 'hidden', 'radio'}
    for art in sorted(arten - ohne_regel):
        assert f'.form-group input[type="{art}"]' in STIL, art


def test_statistik_ohne_immobilie_zeigt_den_weg_zur_beispielimmobilie():
    assert 'id="analytics-leer"' in SEITE
    anfang = SKRIPT.index('async function fetchAnalytics()')
    rumpf = SKRIPT[anfang:SKRIPT.index('\n}\n', anfang)]
    assert "getElementById('analytics-leer')" in rumpf
    assert 'beispielAnlegen(this)' in rumpf
    # der frühe Ausstieg kommt erst nach dem Leerzustand
    assert rumpf.index('leerzustand(') < rumpf.index('return;')


def test_abrechnungen_ohne_mieter_kein_gruener_haken():
    anfang = SKRIPT.index('async function fetchBillingSuggestions()')
    rumpf = SKRIPT[anfang:anfang + 3000]
    assert "titel: 'Noch keine Mieter'" in rumpf
    assert "wechsleZuTab('dashboard')" in rumpf
    assert 'openFreieAbrechnung()' in rumpf


UMSCHRIFT = re.compile(
    r'\b\w*(haelt|waehl|fuer\b|ueber|koenn|zaehl|moeglich|geloescht|pruef|aender|'
    r'muess|groess|schluess|loesch|zurueck|naechst|spaet|verfueg|erklaer|gueltig|'
    r'fuehr|laeuft|haeng|waer|haett|oeffn)\w*', re.IGNORECASE)


def test_kein_umschriebener_umlaut_im_sichtbaren_text():
    """Der Umlaut-Wächter (NK-149) prüft Python-Module; hier der sichtbare
    Text der Seite: ohne Kommentare, Tags und Attributwerte außer title und
    placeholder."""
    ohne_kommentare = re.sub(r'<!--.*?-->', ' ', SEITE, flags=re.S)
    ohne_skript = re.sub(r'<script.*?</script>', ' ', ohne_kommentare, flags=re.S)
    attribute = ' '.join(re.findall(r'(?:title|placeholder)="([^"]*)"', ohne_skript))
    text = re.sub(r'<[^>]+>', ' ', ohne_skript) + ' ' + attribute
    funde = sorted({m.group(0) for m in UMSCHRIFT.finditer(text)})
    assert funde == [], funde


def test_keine_entwicklersprache_und_kein_serverbefehl_in_der_oberflaeche():
    ohne_kommentare = re.sub(r'<!--.*?-->', ' ', SEITE, flags=re.S)
    assert 'der Kern' not in ohne_kommentare
    assert 'flask users' not in ohne_kommentare


def test_me_meldet_die_windows_app(auth_client, app_ctx, monkeypatch):
    assert auth_client.get('/api/auth/me').get_json()['desktop'] is False
    monkeypatch.setitem(app_ctx.app.config, 'DESKTOP', True)
    assert auth_client.get('/api/auth/me').get_json()['desktop'] is True


def test_beispielimmobilie_laedt_alle_bestaende_neu():
    """Sonst meldet die Mieterübersicht nach dem Anlegen „keine Mieter“,
    während die Kachel darüber zwei ausstehende Abrechnungen zählt."""
    anfang = SKRIPT.index('async function beispielAnlegen(')
    rumpf = SKRIPT[anfang:SKRIPT.index('\n}\n', anfang)]
    for lader in ('fetchProperties()', 'fetchAllApartments()', 'fetchTenants()', 'fetchMeters()'):
        assert lader in rumpf, lader
