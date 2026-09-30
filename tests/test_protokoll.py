"""Das Protokoll hat ein Ziel, das den Neustart ueberlebt (NK-042).

NK-030 hat den Fehlerkanal von ``print`` auf ``logging`` umgestellt und an
die Konsole gehaengt. Im Container liest ``docker logs`` das -- aber nur, solange
der Daemon es aufhebt, und nach einem neu angelegten Container ist alles weg.
Genau dann ruft jemand mit einer Vorgangsnummer an, die dann nichts mehr wert
ist. Diese Tests halten die drei Zusagen der Karte fest:

1. Neben der Datenbank liegt eine Protokolldatei, die mitrotiert.
2. Sie laesst sich verlegen und abschalten, und wenn sie nicht geschrieben
   werden kann, faehrt die Anwendung trotzdem hoch.
3. Jede Zeile nennt die Anfrage, aus der sie stammt -- ohne die
   Abfragezeichenkette, in der Kennungen und Einmal-Token stehen koennen.

Die Ausgaenge werden in jedem Test gesichert und zurueckgesetzt: ``fehler``
haelt genau einen Modul-Logger, und ein Test, der ihm einen Ausgang
dazuhaengt, veraendert sonst alle nachfolgenden.
"""

from __future__ import annotations

import logging
import logging.handlers
import re
import subprocess
import sys
from pathlib import Path

import pytest

from nebenkostenfix import fehler


@pytest.fixture
def leere_ausgaenge():
    """Der Modul-Logger ohne Ausgaenge, danach wieder wie vorher."""
    vorher = list(fehler.protokoll.handlers)
    stufe = fehler.protokoll.level
    fehler.protokoll.handlers = []
    yield fehler.protokoll
    for ausgang in fehler.protokoll.handlers:
        ausgang.close()
    fehler.protokoll.handlers = vorher
    fehler.protokoll.setLevel(stufe)


class _App:
    """So viel App, wie ``init_protokoll`` anfasst."""

    def __init__(self, uri=''):
        self.config = {'SQLALCHEMY_DATABASE_URI': uri}
        self.logger = logging.getLogger('test.scheinapp')


# --- Wo die Datei liegt ------------------------------------------------------


def test_datei_liegt_neben_der_datenbank(tmp_path, monkeypatch):
    """Kein zweiter konfigurierter Ort.

    Wo die Daten des Betreibers liegen, haengt im Container ohnehin ein
    Volume vom Wirt herein -- dort ueberlebt die Datei den Neustart. Ein
    eigener Pfad waere ein zweiter Weg, es falsch zu machen.
    """
    monkeypatch.delenv('LOG_DATEI', raising=False)
    monkeypatch.delenv('DATA_DIR', raising=False)
    app = _App(f'sqlite:///{tmp_path / "daten" / "nebenkosten.db"}')

    assert fehler.protokolldatei(app) == tmp_path / 'daten' / fehler.LOGDATEINAME


def test_log_datei_verlegt_das_ziel(tmp_path, monkeypatch):
    monkeypatch.setenv('LOG_DATEI', str(tmp_path / 'woanders.log'))

    assert fehler.protokolldatei(_App()) == tmp_path / 'woanders.log'


def test_leeres_log_datei_schaltet_die_datei_ab(monkeypatch):
    """Der dokumentierte Weg fuer journald und ``docker logs``.

    Wer sein Protokoll ohnehin einsammelt, will keine zweite Kopie auf der
    Platte. Ein leerer Wert ist dafuer die eine naheliegende Schreibweise --
    kein eigener Schalter, den man zusaetzlich kennen muss.
    """
    monkeypatch.setenv('LOG_DATEI', '   ')

    assert fehler.protokolldatei(_App('sqlite:////app/data/x.db')) is None


@pytest.mark.parametrize('uri', [
    '',
    'postgresql://nutzer@host/nk',
    'sqlite:///:memory:',
    'sqlite:///',
])
def test_ohne_datei_datenbank_bleibt_es_bei_der_konsole(uri, monkeypatch):
    """Ohne SQLite-Datei gibt es kein Verzeichnis, das dem Betreiber gehoert.

    Dann irgendwohin zu schreiben -- ins Arbeitsverzeichnis, nach /tmp --
    waere geraten. Die Konsole allein ist in dem Fall die ehrlichere Antwort.
    """
    monkeypatch.delenv('LOG_DATEI', raising=False)
    monkeypatch.delenv('DATA_DIR', raising=False)

    assert fehler.protokolldatei(_App(uri)) is None


def test_mit_data_dir_liegt_die_datei_im_datenordner(tmp_path, monkeypatch):
    """NK-132: der Datenordner schlaegt die Datenbankadresse."""
    monkeypatch.delenv('LOG_DATEI', raising=False)
    monkeypatch.setenv('DATA_DIR', str(tmp_path / 'daten'))
    app = _App('postgresql://nutzer@host/nk')
    assert fehler.protokolldatei(app) == tmp_path / 'daten' / fehler.LOGDATEINAME


# --- Wie gross und wie viele -------------------------------------------------


@pytest.mark.parametrize('wert,erwartet', [('12', 12), (' 3 ', 3), ('1', 1)])
def test_zahl_aus_der_umgebung_wird_uebernommen(wert, erwartet, monkeypatch):
    monkeypatch.setenv('LOG_MAX_MB', wert)

    assert fehler._zahl('LOG_MAX_MB', 5) == erwartet


@pytest.mark.parametrize('murks', ['', '   ', 'fuenf', '5 MB', '0', '-3', '2.5'])
def test_unbrauchbare_zahl_faellt_auf_die_vorgabe_zurueck(murks, monkeypatch):
    """Wie bei LOG_LEVEL und MAX_UPLOAD_MB: ein Tippfehler legt nichts lahm.

    ``0`` und negative Werte sind keine Tippfehler, sondern Unsinn: eine Datei
    mit ``maxBytes=0`` waechst unbegrenzt -- das Gegenteil dessen, was jemand
    meint, der eine Groessengrenze eintraegt.
    """
    monkeypatch.setenv('LOG_MAX_MB', murks)

    assert fehler._zahl('LOG_MAX_MB', 5) == 5


def test_groesse_und_anzahl_kommen_in_der_datei_an(tmp_path, monkeypatch, leere_ausgaenge):
    monkeypatch.setenv('LOG_DATEI', str(tmp_path / 'nk.log'))
    monkeypatch.setenv('LOG_MAX_MB', '2')
    monkeypatch.setenv('LOG_ANZAHL', '7')

    fehler.init_protokoll(_App())

    datei = _dateiausgang()
    assert datei.maxBytes == 2 * 1024 * 1024
    assert datei.backupCount == 7


# --- Dass wirklich etwas ankommt ---------------------------------------------


def _dateiausgang():
    treffer = [a for a in fehler.protokoll.handlers if getattr(a, '_nk_datei', False)]
    assert len(treffer) == 1, f'erwartet genau einen Dateiausgang, gefunden {len(treffer)}'
    return treffer[0]


def test_eine_zeile_landet_in_der_datei(tmp_path, monkeypatch, leere_ausgaenge):
    ziel = tmp_path / 'nk.log'
    monkeypatch.setenv('LOG_DATEI', str(ziel))

    fehler.init_protokoll(_App())
    fehler.protokoll.error('Vorgang 1234ABCD: es hat geknallt')
    _dateiausgang().flush()

    assert 'Vorgang 1234ABCD' in ziel.read_text(encoding='utf-8')


def test_die_datei_rotiert(tmp_path, monkeypatch, leere_ausgaenge):
    """Ohne Rotation frisst das Protokoll irgendwann die Platte.

    Eine volle Platte trifft bei dieser Anwendung die Datenbank mit -- die
    liegt im selben Verzeichnis. Deshalb ein ``RotatingFileHandler`` und nicht
    ein ``FileHandler``, dem niemand zusieht.
    """
    ziel = tmp_path / 'nk.log'
    monkeypatch.setenv('LOG_DATEI', str(ziel))

    fehler.init_protokoll(_App())
    datei = _dateiausgang()
    assert isinstance(datei, logging.handlers.RotatingFileHandler)

    datei.maxBytes = 200
    for nummer in range(40):
        fehler.protokoll.error('Zeile %02d mit genug Text, um die Datei zu fuellen', nummer)
    datei.flush()

    assert (tmp_path / 'nk.log.1').exists()


def test_das_verzeichnis_wird_angelegt(tmp_path, monkeypatch, leere_ausgaenge):
    """Beim ersten Start eines frischen Containers gibt es data/ noch nicht."""
    ziel = tmp_path / 'noch' / 'nicht' / 'da' / 'nk.log'
    monkeypatch.setenv('LOG_DATEI', str(ziel))

    fehler.init_protokoll(_App())

    assert ziel.parent.is_dir()


def test_init_protokoll_haengt_die_datei_nur_einmal_an(tmp_path, monkeypatch, leere_ausgaenge):
    monkeypatch.setenv('LOG_DATEI', str(tmp_path / 'nk.log'))

    fehler.init_protokoll(_App())
    fehler.init_protokoll(_App())

    assert len([a for a in fehler.protokoll.handlers if getattr(a, '_nk_datei', False)]) == 1


def test_ein_unbeschreibbares_ziel_haelt_den_start_nicht_auf(tmp_path, monkeypatch, leere_ausgaenge):
    """Eine Anwendung, die am Protokoll scheitert, hat dessen Zweck verfehlt.

    Der Pfad zeigt hier durch eine Datei hindurch -- ``mkdir`` beantwortet das
    mit einem ``OSError``. Erwartet wird: kein Absturz, kein Dateiausgang, und
    ein Satz auf der Konsole, der den Grund nennt.
    """
    sperre = tmp_path / 'keine-datei'
    sperre.write_text('ich bin eine Datei, kein Verzeichnis', encoding='utf-8')
    monkeypatch.setenv('LOG_DATEI', str(sperre / 'unten' / 'nk.log'))

    fehler.init_protokoll(_App())

    assert not any(getattr(a, '_nk_datei', False) for a in fehler.protokoll.handlers)
    assert any(getattr(a, '_nk_ausgang', False) for a in fehler.protokoll.handlers)


def test_der_grund_des_fehlschlags_steht_im_protokoll(tmp_path, monkeypatch, leere_ausgaenge):
    gesammelt = []

    class _Mitschnitt(logging.Handler):
        def emit(self, satz):
            gesammelt.append(satz.getMessage())

    fehler.protokoll.addHandler(_Mitschnitt())
    sperre = tmp_path / 'keine-datei'
    sperre.write_text('x', encoding='utf-8')
    monkeypatch.setenv('LOG_DATEI', str(sperre / 'unten' / 'nk.log'))

    fehler.init_protokoll(_App())

    assert any('nicht beschreibbar' in zeile for zeile in gesammelt)


# --- Aus welcher Anfrage die Zeile stammt ------------------------------------


def _anfrage_zu(satz='egal'):
    aufzeichnung = logging.LogRecord(
        fehler.PROTOKOLLNAME, logging.INFO, __file__, 1, satz, None, None)
    fehler.Anfragekontext().filter(aufzeichnung)
    return aufzeichnung.anfrage


def test_ohne_anfrage_bleibt_das_feld_leer():
    """Startmeldungen und Wartungsskripte haben keine Anfrage."""
    assert _anfrage_zu() == ''


def test_die_anfrage_steht_in_der_zeile(app_ctx):
    with app_ctx.app.test_request_context('/api/documents', method='POST'):
        assert _anfrage_zu() == ' [POST /api/documents]'


def test_die_abfragezeichenkette_bleibt_draussen(app_ctx):
    """Dort stehen Kennungen und Einmal-Token.

    Ein Protokoll ist die Datei, die man am ehesten weiterschickt, wenn etwas
    kaputt ist -- ``request.full_path`` haette ``?token=...`` mit darin.
    """
    with app_ctx.app.test_request_context('/api/documents?token=geheim123&id=7'):
        anfrage = _anfrage_zu()

    assert anfrage == ' [GET /api/documents]'
    assert 'geheim' not in anfrage


def test_auch_zeilen_der_kindlogger_bekommen_das_feld(tmp_path, monkeypatch, leere_ausgaenge, app_ctx):
    """Der Fallstrick, an dem der Filter am Logger gescheitert waere.

    ``nebenkosten.nas`` schreibt in dieselben Ausgaenge, entsteht aber an einem
    anderen Logger. Ein Filter am Logger ``nebenkosten`` laeuft fuer solche
    Zeilen nicht -- dem Formatter fehlte dann ``anfrage``, und ``logging``
    quittiert das mit einer Meldung auf stderr, also genau dort, wo in dem
    Moment niemand hinsieht.
    """
    ziel = tmp_path / 'nk.log'
    monkeypatch.setenv('LOG_DATEI', str(ziel))
    fehler.init_protokoll(_App())

    kind = logging.getLogger(f'{fehler.PROTOKOLLNAME}.nas')
    with app_ctx.app.test_request_context('/api/backup/run', method='POST'):
        kind.error('Freigabe nicht erreichbar')
    _dateiausgang().flush()

    geschrieben = ziel.read_text(encoding='utf-8')
    assert 'nebenkosten.nas [POST /api/backup/run]: Freigabe nicht erreichbar' in geschrieben


def test_die_zeile_nennt_zeit_stufe_und_quelle(tmp_path, monkeypatch, leere_ausgaenge):
    """Das ist der Unterschied zu einem ``print`` (NK-030, NK-042).

    Ein ``print`` haette im Container dieselbe sichtbare Wirkung -- aber ohne
    Zeitstempel, ohne Stufe, ohne Herkunft und ohne die Moeglichkeit, es
    abzudrehen.
    """
    ziel = tmp_path / 'nk.log'
    monkeypatch.setenv('LOG_DATEI', str(ziel))
    fehler.init_protokoll(_App())

    fehler.protokoll.error('etwas ist passiert')
    _dateiausgang().flush()
    zeile = ziel.read_text(encoding='utf-8').strip()

    assert ' ERROR ' in zeile
    assert fehler.PROTOKOLLNAME in zeile
    assert zeile[:4].isdigit()  # Jahr aus %Y-%m-%d


# --- Was beim Start schon drinsteht ------------------------------------------


def _startzeilen(monkeypatch, **umgebung):
    """Faengt ab, was ``init_protokoll`` selbst schreibt."""
    gesammelt = []

    class _Mitschnitt(logging.Handler):
        def emit(self, satz):
            gesammelt.append(satz.getMessage())

    for name, wert in umgebung.items():
        monkeypatch.setenv(name, wert)
    fehler.protokoll.addHandler(_Mitschnitt())
    fehler.init_protokoll(_App())
    return gesammelt


def test_der_start_hinterlaesst_eine_zeile_in_der_datei(tmp_path, monkeypatch, leere_ausgaenge):
    """Eine leere Datei beantwortet die wichtigste Frage nicht.

    Sie sagt nicht, ob das Protokoll traegt und nur nichts passiert ist, oder
    ob es klemmt. Wer das erst an dem Tag merkt, an dem er die Datei wirklich
    braucht, hat sie umsonst gehabt. Deshalb steht der Pfad in der Datei, die
    er bezeichnet.
    """
    ziel = tmp_path / 'nk.log'
    monkeypatch.setenv('LOG_DATEI', str(ziel))

    fehler.init_protokoll(_App())
    _dateiausgang().flush()
    inhalt = ziel.read_text(encoding='utf-8')

    assert 'Protokoll bereit' in inhalt
    assert str(ziel) in inhalt


def test_die_startzeile_nennt_die_eingestellte_stufe(tmp_path, monkeypatch, leere_ausgaenge):
    zeilen = _startzeilen(
        monkeypatch, LOG_DATEI=str(tmp_path / 'nk.log'), LOG_LEVEL='DEBUG')

    assert any('Stufe DEBUG' in zeile for zeile in zeilen)


def test_ohne_dateiziel_sagt_die_startzeile_das_auch(monkeypatch, leere_ausgaenge):
    """``LOG_DATEI=`` schaltet die Datei ab -- dann soll niemand danach suchen."""
    zeilen = _startzeilen(monkeypatch, LOG_DATEI='')

    assert any('nur Konsole' in zeile for zeile in zeilen)


def test_die_startzeile_geht_nach_stderr_und_laesst_stdout_frei(
        tmp_path, monkeypatch, capsys, leere_ausgaenge):
    """F-30: auf stdout schreiben die Konsolenbefehle ihre Nutzdaten.

    ``flask users list`` gibt eine Tabelle aus, ``flask backup info`` einen
    Bericht, der Probelauf aus NK-040 reines JSON. Seit es eine Startzeile
    gibt, stand sie jedem davon voran -- der JSON-Leser bricht daran ab, und
    wer die Ausgabe durch ein Skript schickt, bekommt eine Zeile Protokoll in
    seine Daten. ``docker compose logs`` zeigt beide Stroeme, der Betreiber
    merkt von der Verlegung also nichts; nur das Rohr daneben wird wieder
    sauber.
    """
    monkeypatch.setenv('LOG_DATEI', str(tmp_path / 'nk.log'))

    fehler.init_protokoll(_App())
    for ausgang in fehler.protokoll.handlers:
        ausgang.flush()
    gefangen = capsys.readouterr()

    assert 'Protokoll bereit' in gefangen.err
    assert gefangen.out == '', f'auf stdout gelandet: {gefangen.out!r}'


def test_eine_hochgesetzte_stufe_unterdrueckt_die_startzeile(tmp_path, monkeypatch, leere_ausgaenge):
    """Wer ``LOG_LEVEL=WARNING`` setzt, hat Betriebsmeldungen abbestellt.

    Die Startzeile ist eine davon. Sie auf WARNING zu heben, nur damit die
    Datei nicht leer bleibt, waere eine Umgehung der eigenen Einstellung.
    """
    zeilen = _startzeilen(
        monkeypatch, LOG_DATEI=str(tmp_path / 'nk.log'), LOG_LEVEL='WARNING')

    assert not any('Protokoll bereit' in zeile for zeile in zeilen)


# --- Zwei Arbeiter, eine Datei -----------------------------------------------


# Wie viele Zeilen der leise Arbeiter schreibt, nachdem der laute fertig ist.
# Jede einzelne muss ueberleben -- die Begruendung steht im Test unten.
SCHLUSSZEILEN = 5

SCHREIBER = '''
import logging, os, sys, time
sys.path.insert(0, {wurzel!r})
from nebenkostenfix.fehler import Mehrprozessrotierend
ziel, marke, anzahl, pause, marke_datei = sys.argv[1:6]
anzahl, pause = int(anzahl), float(pause)
h = Mehrprozessrotierend(ziel, maxBytes=2000, backupCount=3, encoding='utf-8')
h.setFormatter(logging.Formatter('%(message)s'))
log = logging.getLogger(marke); log.setLevel(logging.INFO); log.addHandler(h)
for i in range(anzahl):
    log.info('%s-%03d ' + '.' * 60, marke, i)
    time.sleep(pause)
if marke_datei != '-':
    # Warten, bis der laute Arbeiter fertig ist; die Marke legt der Test an,
    # nachdem er ihn eingesammelt hat. Erst danach die Schlusszeilen.
    frist = time.time() + 120
    while not os.path.exists(marke_datei) and time.time() < frist:
        time.sleep(0.01)
    for i in range({schluss}):
        log.info('SCHLUSS-%03d ' + '.' * 60, i)
'''


def test_der_leise_arbeiter_wird_nicht_vom_lauten_ueberrollt(tmp_path):
    """Das Abbild startet mit ``--workers 2`` -- beide schreiben dieselbe Datei.

    Der eingebaute ``RotatingFileHandler`` weiss nichts von einem zweiten
    Prozess: rotiert der laute Arbeiter, schreibt der leise weiter in einen
    Dateideskriptor, der inzwischen anders heisst und gleich geloescht wird.
    Getroffen wird damit genau die falsche Sorte Zeile -- wer wenig
    protokolliert, meldet Seltenes.

    Gemessen wird das an einem Zeitpunkt, an dem die Rotation nachweislich
    vorbei ist: der leise Arbeiter setzt seine letzten ``SCHLUSSZEILEN``
    Zeilen erst ab, nachdem der laute beendet und eingesammelt ist. Was danach
    geschrieben wird, kann niemand mehr rechtmaessig fortrotieren, also muss
    jede dieser Zeilen in der Datei stehen. Dreimal gemessen: mit dem
    eingebauten Handler kamen 0 von 5 an, mit ``Mehrprozessrotierend`` 5 von 5.
    """
    skript = tmp_path / 'schreiber.py'
    skript.write_text(
        SCHREIBER.format(
            wurzel=str(Path(__file__).resolve().parent.parent),
            schluss=SCHLUSSZEILEN),
        encoding='utf-8')
    ziel = tmp_path / 'nk.log'
    marke = tmp_path / 'laut-fertig'

    laut = subprocess.Popen(
        [sys.executable, str(skript), str(ziel), 'VIEL', '2000', '0', '-'])
    leise = subprocess.Popen(
        [sys.executable, str(skript), str(ziel), 'WENIG', '20', '0.02',
         str(marke)])
    laut.wait(timeout=60)
    marke.write_text('fertig', encoding='utf-8')
    leise.wait(timeout=60)

    schluss = set()
    zeilen = []
    for stand in tmp_path.glob('nk.log*'):
        if stand.name.endswith('.sperre'):
            continue
        inhalt = stand.read_text(encoding='utf-8')
        zeilen += [z for z in inhalt.splitlines() if z]
        schluss |= {
            int(nr) for nr in re.findall(r'^SCHLUSS-(\d+)', inhalt, re.M)}

    # Erstens: jede Schlusszeile ist da. Die Aussage kommt ohne jede Annahme
    # darueber aus, wie sich die Laufzeit der beiden Prozesse zueinander
    # verhaelt -- der Synchronisationspunkt stellt die Reihenfolge her, nicht
    # das Glueck. Zwei fruehere Entwuerfe hingen genau daran: erst die
    # namentlichen Zeilen {15..19}, dann die blosse Frage, ob ueberhaupt etwas
    # vom leisen Arbeiter uebrig ist. Beide wurden unter der Last eines vollen
    # `make check` rot, obwohl nichts kaputt war: der laute Arbeiter lief dort
    # laenger als der leise und rotierte dessen Zeilen rechtmaessig fort.
    fehlend = set(range(SCHLUSSZEILEN)) - schluss
    assert not fehlend, (
        f'nach dem Ende des lauten Arbeiters geschriebene Zeilen fehlen: '
        f'{sorted(fehlend)}')

    # Zweitens: keine Zeile ist zerschnitten. Das waere dieselbe Ursache, nur
    # an der anderen Stelle sichtbar -- zwei Prozesse auf einem Deskriptor.
    # ``\d+``, nicht ``\d{3}``: der Formatierer schreibt ``%03d``, das ist
    # eine Mindestbreite -- ab VIEL-1000 sind es vier Stellen.
    unfertig = [
        z for z in zeilen
        if not re.match(r'^(VIEL|WENIG|SCHLUSS)-\d+ \.{60}$', z)]
    assert not unfertig, f'zerschnittene Zeilen: {unfertig[:3]}'


@pytest.mark.skipif(sys.platform == 'win32',
                    reason='Windows gibt eine offene Datei nicht zum Umbenennen frei')
def test_ein_ersetzter_dateistand_wird_neu_geoeffnet(tmp_path):
    """Der Inode-Vergleich, den ``WatchedFileHandler`` vormacht."""
    ziel = tmp_path / 'nk.log'
    ausgang = fehler.Mehrprozessrotierend(ziel, maxBytes=0, encoding='utf-8')
    try:
        ausgang.emit(logging.LogRecord('t', logging.INFO, '', 0, 'erste', (), None))
        ziel.rename(tmp_path / 'weggezogen.log')   # so wirkt fremde Rotation

        ausgang.emit(logging.LogRecord('t', logging.INFO, '', 0, 'zweite', (), None))
        ausgang.flush()

        assert 'zweite' in ziel.read_text(encoding='utf-8')
        assert 'zweite' not in (tmp_path / 'weggezogen.log').read_text(encoding='utf-8')
    finally:
        ausgang.close()


@pytest.mark.skipif(sys.platform == 'win32',
                    reason='Windows gibt eine offene Datei nicht zum Umbenennen frei')
def test_eine_geloeschte_datei_wird_neu_angelegt(tmp_path):
    """Wer aufraeumt, soll das Protokoll nicht fuer den Rest des Tages abwuergen.

    Laesst sich nicht feststellen, ob der offene Deskriptor noch zur Datei
    gehoert, lautet die Antwort Nein -- es wird neu geoeffnet. Ein ``pass`` an
    dieser Stelle waere bequemer und wuerde denselben Weg nehmen, aber niemand
    saehe ihm an, dass er gemeint ist.
    """
    ziel = tmp_path / 'nk.log'
    ausgang = fehler.Mehrprozessrotierend(ziel, maxBytes=0, encoding='utf-8')
    try:
        ausgang.emit(logging.LogRecord('t', logging.INFO, '', 0, 'erste', (), None))
        ziel.unlink()   # jemand raeumt auf

        ausgang.emit(logging.LogRecord('t', logging.INFO, '', 0, 'zweite', (), None))
        ausgang.flush()

        assert ziel.exists(), 'die Datei kam nicht wieder'
        assert 'zweite' in ziel.read_text(encoding='utf-8')
    finally:
        ausgang.close()


def test_wer_die_sperre_bekommt_schichtet_nicht_ein_zweites_mal_um(tmp_path):
    """Sonst wirft der zweite Prozess den frischen Stand des ersten weg."""
    ziel = tmp_path / 'nk.log'
    ausgang = fehler.Mehrprozessrotierend(ziel, maxBytes=10_000, encoding='utf-8')
    try:
        ausgang.emit(logging.LogRecord('t', logging.INFO, '', 0, 'frisch', (), None))
        ausgang.flush()

        ausgang.doRollover()   # Datei ist klein -- ein anderer war schneller

        assert not (tmp_path / 'nk.log.1').exists()
        assert 'frisch' in ziel.read_text(encoding='utf-8')
    finally:
        ausgang.close()
