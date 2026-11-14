"""Die Karte „Angemeldete Geräte“ in Einstellungen → Konto (#52).

Hier stehen die Rechner, auf denen die Desktop-App angemeldet bleibt:
Rechnername, Konto, angemeldet am, zuletzt benutzt und „Abmelden“. Das
eigene Gerät ist markiert. Meldet man es ab, endet auch die Sitzung hier;
die Seite geht dann über ``/login?abgemeldet=1``, damit die App ihr Token
löscht. Im offenen Modus gibt es keine Konten und damit keine Geräte.

Muster wie ``tests/test_zugriffsschluessel_oberflaeche.py``: der echte
Funktionsrumpf aus ``app.js`` läuft in node gegen ein Mini-DOM.
"""

from __future__ import annotations

import pytest

from tests.test_zugriffsschluessel_oberflaeche import (
    DOM, SEITE, WURZEL, _funktionsrumpf, _konstante, _node, braucht_node)


def _karte():
    karte = SEITE[SEITE.index('id="geraete-karte"'):]
    return karte[:karte.index('<!-- NK-175')]


def test_die_seite_hat_die_karte():
    karte = _karte()
    assert 'data-gruppe="konto"' in SEITE[SEITE.index('id="geraete-karte"') - 80:
                                          SEITE.index('id="geraete-karte"')]
    assert '<h3>Angemeldete Geräte</h3>' in karte
    assert 'id="geraete-zeilen"' in karte
    for spalte in ('Rechner', 'Konto', 'Angemeldet am', 'Zuletzt benutzt'):
        assert f'>{spalte}</th>' in karte, spalte
    # Die Karte steht unter den Zugriffsschlüsseln.
    assert SEITE.index('id="zugriffsschluessel-karte"') < SEITE.index('id="geraete-karte"')


def test_der_offene_modus_blendet_die_karte_aus():
    rumpf = _funktionsrumpf('zeigeAngemeldetenBenutzer')
    liste = rumpf[rumpf.index("['angemeldeterBenutzer'"):]
    liste = liste[:liste.index(']') + 1]
    assert "'geraete-karte'" in liste


@pytest.mark.parametrize('weg', ['initApp', 'initTabs'])
def test_beide_ladewege_laden_auch_die_geraete(weg):
    assert 'ladeGeraete();' in _funktionsrumpf(weg)


def test_die_gruppe_konto_laedt_die_geraete_neu():
    rumpf = _funktionsrumpf('zeigeEinstellungsgruppe')
    assert "ladeGeraete();" in rumpf[rumpf.index("gruppe === 'konto'"):]


@braucht_node
def test_die_liste_maskiert_und_markiert_dieses_geraet():
    code = DOM + _funktionsrumpf('ladeGeraete') + '''
const fetch = async () => ({ ok: true, json: async () => [
    { id: 1, name: '<b>Büro</b>', konto: 'vermieter', angelegt_am: '01.11.2026 09:00',
      zuletzt_benutzt: '01.11.2026 10:00', dieses_geraet: true },
    { id: 2, name: 'Laptop', konto: 'partnerin', angelegt_am: '02.11.2026 09:00',
      zuletzt_benutzt: '02.11.2026 10:00', dieses_geraet: false }] });
ladeGeraete().then(() => console.log(JSON.stringify({
    html: elemente['geraete-zeilen'].innerHTML })));
'''
    html = _node(code)['html']
    assert '&lt;b&gt;Büro&lt;/b&gt;' in html and '<b>' not in html
    assert html.count('(dieses Gerät)') == 1
    assert html.index('(dieses Gerät)') < html.index('Laptop')
    for wert in ('vermieter', 'partnerin', '01.11.2026 09:00', '02.11.2026 10:00'):
        assert wert in html
    assert 'geraetAbmelden(1, true, this.dataset.name)' in html
    assert 'geraetAbmelden(2, false, this.dataset.name)' in html
    # Der Name steht nur maskiert im Attribut, nie im onclick-Text.
    assert 'data-name="&lt;b&gt;Büro&lt;/b&gt;"' in html
    assert '>Abmelden</button>' in html


@braucht_node
def test_ohne_geraete_erklaert_ein_satz_die_liste():
    code = DOM + _funktionsrumpf('ladeGeraete') + '''
const fetch = async () => ({ ok: true, json: async () => [] });
ladeGeraete().then(() => console.log(JSON.stringify({
    html: elemente['geraete-zeilen'].innerHTML })));
'''
    html = _node(code)['html']
    assert 'colspan="5"' in html
    assert 'Angemeldet bleiben' in html


@braucht_node
@pytest.mark.parametrize('dieses, ok, ziel, geladen, meldungen', [
    (False, True, None, 1, [['ok', 'Gerät abgemeldet.']]),
    (True, True, '/login?abgemeldet=1', 0, []),
    # Scheitert das Abmelden, bleibt die Seite stehen und sagt es.
    (False, False, None, 0, [['fehler', 'Das Gerät konnte nicht abgemeldet werden.']]),
    (True, False, None, 0, [['fehler', 'Das Gerät konnte nicht abgemeldet werden.']]),
])
def test_abmelden(dieses, ok, ziel, geladen, meldungen):
    """Ein fremdes Gerät verschwindet aus der Liste. Das eigene beendet die
    Sitzung hier; die Seite geht zur Anmeldung, und die App löscht ihr Token."""
    code = DOM + _funktionsrumpf('geraetAbmelden') + f'''
let geladen = 0; const ladeGeraete = () => {{ geladen++; }};
const frage = async () => true;
const gesendet = [];
const fetch = async (pfad, opt) => {{
    gesendet.push([pfad, opt.method]); return {{ ok: {str(ok).lower()} }}; }};
let ziel = null; const window = {{ location: {{ assign: (z) => {{ ziel = z; }} }} }};
geraetAbmelden(7, {str(dieses).lower()}, 'Laptop').then(() => console.log(JSON.stringify({{
    gesendet, geladen, ziel, meldungen }})));
'''
    erg = _node(code)
    assert erg['gesendet'] == [['/api/geraete/7', 'DELETE']]
    assert erg['ziel'] == ziel
    assert erg['geladen'] == geladen
    assert erg['meldungen'] == meldungen


@braucht_node
def test_abmelden_fragt_vorher():
    code = DOM + _funktionsrumpf('geraetAbmelden') + '''
const ladeGeraete = () => {};
const fragen = []; const frage = async (...a) => { fragen.push(a); return false; };
let abrufe = 0; const fetch = async () => { abrufe++; return { ok: true }; };
geraetAbmelden(7, false, 'Laptop').then(() => console.log(JSON.stringify({ abrufe, fragen })));
'''
    erg = _node(code)
    assert erg['abrufe'] == 0
    text, knopf, gefahr, titel = erg['fragen'][0]
    # Welcher Rechner, und dass es sofort gilt (Review #52).
    assert '„Laptop“' in text and 'sofort' in text
    assert 'Passwort' in text and knopf == 'Abmelden' and gefahr is True
    assert titel == 'Gerät abmelden?'


def test_das_handbuch_erklaert_die_liste():
    handbuch = ' '.join((WURZEL / 'docs' / 'handbuch' / 'handbuch.md')
                        .read_text(encoding='utf-8').split())
    absatz = handbuch[handbuch.index('**Angemeldete Geräte**'):]
    absatz = absatz[:absatz.index('- **Updates**')]
    for wort in ('Angemeldet bleiben', 'Abmelden', '30 Tage', 'Passwort',
                 'Jedes Konto sieht alle Rechner'):
        assert wort in absatz, wort


def test_der_logout_der_seite_geht_ueber_abgemeldet():
    """Daran erkennt die Desktop-App das Abmelden (#52)."""
    assert "window.location.assign('/login?abgemeldet=1');" in _funktionsrumpf('abmelden')


# --- Leerlauf-Hinweis ----------------------------------------------------------
# Mit Häkchen meldet die App sich nach der Leerlauf-Grenze still wieder an.
# „Sie werden abgemeldet“ stimmt dann nicht, und der Knopf hieß wie das
# Häkchen: „Angemeldet bleiben“ (App-Test #52).

LEERLAUF = (DOM + _konstante('LEERLAUF_WARNUNG_MS')
            + 'let leerlaufMs = 60 * 60 * 1000; let letzteBedienung = 0; let leerlaufStill = false;\n')


@braucht_node
@pytest.mark.parametrize('geraet', [True, False])
def test_die_seite_merkt_sich_die_geraete_sitzung(geraet):
    code = LEERLAUF + _funktionsrumpf('initLeerlauf') + f'''
document.addEventListener = () => {{}}; const setInterval = () => {{}};
const leerlaufPruefen = () => {{}}; const window = {{}};
const fetch = async () => ({{ ok: true, json: async () => ({{ leerlauf_s: 120, geraet: {str(geraet).lower()} }}) }});
initLeerlauf().then(() => console.log(JSON.stringify({{ still: leerlaufStill, ms: leerlaufMs }})));
'''
    assert _node(code) == {'still': geraet, 'ms': 120000}


def _pruefen(still, rest_ms):
    code = LEERLAUF + _funktionsrumpf('leerlaufPruefen') + f'''
leerlaufStill = {str(still).lower()};
elemente['leerlauf-hinweis'] = {{ hidden: true }};
let ziel = null; let gesichert = 0; const entwurfSichern = () => {{ gesichert++; }};
const window = {{ nkLetzteAnfrage: Date.now() - (leerlaufMs - {rest_ms}),
                  location: {{ pathname: '/einstellungen', assign: (z) => {{ ziel = z; }} }} }};
leerlaufPruefen();
console.log(JSON.stringify({{ verborgen: elemente['leerlauf-hinweis'].hidden,
    text: (elemente['leerlauf-text'] || {{}}).textContent || '', ziel, gesichert }}));
'''
    return _node(code)


@braucht_node
def test_ohne_geraet_warnt_die_seite_wie_bisher():
    erg = _pruefen(False, 60 * 1000)
    assert erg['verborgen'] is False
    assert 'in 1 Minute abgemeldet' in erg['text']


@braucht_node
def test_mit_geraet_warnt_die_seite_nicht():
    erg = _pruefen(True, 60 * 1000)
    assert erg['verborgen'] is True and erg['ziel'] is None


@braucht_node
def test_mit_geraet_bleibt_die_seite_nach_der_grenze_stehen():
    """Ginge die Seite selbst zur Anmeldung, meldete die App sich still an,
    die Seite lüde neu, und nach der nächsten Grenze ginge es von vorn: Das
    Fenster blitzte im Leerlauf ständig (App-Test #52). Die Sitzung läuft auf
    dem Server trotzdem ab; erst der nächste Klick bekommt 401, und
    zurAnmeldung sichert die Eingabe wie bisher."""
    erg = _pruefen(True, -1000)
    assert erg['ziel'] is None and erg['gesichert'] == 0
    assert erg['verborgen'] is True


@braucht_node
def test_ohne_geraet_geht_die_seite_nach_der_grenze_zur_anmeldung():
    erg = _pruefen(False, -1000)
    assert erg['ziel'] == '/login?next=%2Feinstellungen'
    assert erg['gesichert'] == 1
