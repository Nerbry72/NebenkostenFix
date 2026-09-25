"""Fehlerbehandlung und Protokoll an einer Stelle (NK-030).

Vorher stand es so: 32 ``db.session.commit()`` und zwei ``db.session.rollback()``.
Eine Anweisung, die mittendrin abbricht, liess die Sitzung kaputt zurueck --
SQLAlchemy beantwortet danach jede weitere Abfrage derselben Sitzung mit
``PendingRollbackError``. Der Vermieter sah eine 500 ohne Text und danach eine
Oberflaeche, die auch bei gesunden Eingaben nichts mehr annahm.

Dazu kamen fuenf ``print(`` als einziger Fehlerkanal und elf blanke
``except Exception``, die den englischen Wortlaut der Ausnahme als ``error``
zurueckgaben: "NAS Upload failed: [Errno 13] Permission denied". Das ist
zugleich zu viel (Innenleben nach aussen) und zu wenig (niemand kann es
zuordnen, weil im Protokoll nichts davon steht).

Dieses Modul loest beides:

* ``init_protokoll(app)`` haengt ``logging`` an stderr **und** an eine Datei
  neben der Datenbank (NK-042). Im Container liest ``docker logs`` das erste,
  ein ``print`` haette dort dieselbe Wirkung -- aber ohne Zeitstempel, ohne
  Stufe und ohne die Moeglichkeit, es abzudrehen. Die Datei ist der Grund,
  warum die Vorgangsnummer ueberhaupt etwas wert ist: ``docker logs`` haelt
  nur, was der Daemon gerade aufhebt, und nach einem neu angelegten Container
  ist alles weg. Wer drei Tage spaeter mit einer Nummer anruft, braucht ein
  Protokoll, das den Neustart ueberlebt hat.
* Jede Zeile nennt die Anfrage, aus der sie stammt: ``[POST /api/documents]``.
  Ohne das steht im Protokoll ein Satz ohne Ort -- bei einem Vermieter mit
  einer Instanz reicht das, bei zwoelf gleichzeitigen Anfragen nicht mehr.
  **Die Abfragezeichenkette bleibt draussen**: dort koennen Kennungen und
  Einmal-Token stehen, und ein Protokoll ist die Datei, die man am ehesten
  weiterschickt, wenn etwas kaputt ist.
* ``init_fehlerbehandlung(app)`` faengt jede unbehandelte Ausnahme ab, macht
  ``rollback``, vergibt eine **Vorgangsnummer**, schreibt den Stapelabzug unter
  dieser Nummer ins Protokoll und antwortet mit einem deutschen Satz, der
  dieselbe Nummer nennt. Wer anruft, liest die Nummer vor, und im Protokoll
  steht genau ein Treffer dazu.

Der Stapelabzug geht ins Protokoll, nie in die Antwort. Ein Stapelabzug im
Browser nennt Pfade, Bibliotheksversionen und Zeileninhalte -- das ist eine
Landkarte fuer jeden, der die Instanz aus dem Netz erreicht.
"""

from __future__ import annotations

import logging
import logging.handlers

try:
    import fcntl
except ImportError:  # Windows -- dort laeuft der Installer mit einem Prozess
    fcntl = None
import os
import sys
import uuid
from pathlib import Path

from flask import has_request_context, jsonify, request
from werkzeug.exceptions import HTTPException

# Dieselbe Regel wie die Zugangssperre, nicht eine zweite. Zwei Antworten auf
# "will der Aufrufer JSON oder eine Seite?" wuerden frueher oder spaeter
# auseinanderlaufen, und dann hinge es an der Route, was der Nutzer sieht.
from auth import _wants_json as moechte_json
from models import db

PROTOKOLLNAME = 'nebenkosten'
protokoll = logging.getLogger(PROTOKOLLNAME)

STANDARDSTUFE = 'INFO'

# Das Datei-Ziel (NK-042). Der Name liegt neben der Datenbank, nicht an einem
# eigenen konfigurierten Ort: wo die Daten des Betreibers liegen, haengt im
# Container ohnehin ein Volume vom Wirt herein, und ein zweiter Pfad waere ein
# zweiter Weg, etwas falsch zu machen. LOG_DATEI ueberschreibt ihn, ein leerer
# Wert schaltet die Datei ab.
LOGDATEINAME = 'nebenkosten.log'
STANDARD_MAX_MB = 5
STANDARD_ANZAHL = 5

FORMAT = '%(asctime)s %(levelname)s %(name)s%(anfrage)s: %(message)s'
DATUMSFORMAT = '%Y-%m-%d %H:%M:%S'

# Der Satz fuer alles, was niemand vorhergesehen hat. Er sagt bewusst auch,
# was mit den Daten ist: die zweithaeufigste Frage nach "was ist passiert?"
# ist "ist jetzt die Haelfte gespeichert?", und die Antwort ist nein, weil
# genau dieser Handler zurueckrollt.
ALLGEMEIN = ('Es ist ein Fehler aufgetreten. Die Änderung wurde nicht '
             'gespeichert.')

# Werkzeug liefert zu jedem HTTP-Fehler einen englischen Satz. Die hier sind
# deutsch und sagen, was der Vermieter tun kann, statt den Status zu wiederholen.
HTTP_MELDUNGEN = {
    400: 'Die Anfrage war unvollständig oder nicht lesbar.',
    401: 'Nicht angemeldet.',
    403: 'Dafür fehlt die Berechtigung.',
    404: 'Das Gesuchte gibt es nicht (mehr).',
    405: 'Diese Adresse nimmt diese Art von Anfrage nicht an.',
    409: 'Das passt nicht zum aktuellen Stand der Daten.',
    410: 'Das Gesuchte gibt es nicht mehr.',
    415: 'Dieses Format nimmt die Anwendung nicht an.',
    422: 'Die Angaben sind in sich nicht schlüssig.',
    429: 'Zu viele Anfragen in kurzer Zeit. Bitte kurz warten.',
    500: ALLGEMEIN,
    502: 'Ein Dienst dahinter hat nicht geantwortet.',
    503: 'Die Anwendung ist gerade nicht bereit. Bitte später erneut versuchen.',
}


def vorgangsnummer() -> str:
    """Eine kurze Nummer, die Antwort und Protokollzeile verbindet.

    Acht Stellen aus einer UUID: kurz genug, um sie am Telefon vorzulesen oder
    abzutippen, und weit genug gestreut, dass zwei Fehler am selben Tag nicht
    dieselbe Nummer bekommen. Fortlaufende Nummern waeren schoener zu lesen,
    braeuchten aber einen Zaehler, der einen Neustart ueberlebt -- also eine
    Tabelle, die ausgerechnet dann beschrieben werden muesste, wenn die
    Datenbank gerade der Grund des Fehlers ist.
    """
    return uuid.uuid4().hex[:8].upper()


def _stufe(rohwert=None) -> int:
    """Die Protokollstufe aus LOG_LEVEL, mit Rueckfall auf INFO.

    Wie bei MAX_UPLOAD_MB (NK-029): ein Tippfehler in der .env darf die
    Instanz nicht am Start hindern. Ein zu gespraechiges Protokoll ist
    harmloser als eine Anwendung, die nicht hochkommt.
    """
    if rohwert is None:
        rohwert = os.environ.get('LOG_LEVEL', '')
    name = str(rohwert).strip().upper() or STANDARDSTUFE
    stufe = logging.getLevelName(name)
    if not isinstance(stufe, int):
        return logging.getLevelName(STANDARDSTUFE)
    return stufe


def _zahl(name: str, vorgabe: int, kleinstwert: int = 1) -> int:
    """Eine Zahl aus der Umgebung, mit Rueckfall auf die Vorgabe.

    Dieselbe Haltung wie bei ``_stufe`` und MAX_UPLOAD_MB (NK-029): ein
    Tippfehler in der .env darf die Instanz nicht am Start hindern. Null und
    negative Werte sind keine Tippfehler, sondern Unsinn -- eine Datei mit
    ``maxBytes=0`` waechst unbegrenzt, und das ist das Gegenteil dessen, was
    jemand meint, der eine Groessengrenze eintraegt.
    """
    roh = os.environ.get(name, '')
    try:
        wert = int(str(roh).strip())
    except (TypeError, ValueError):
        return vorgabe
    return wert if wert >= kleinstwert else vorgabe


def protokolldatei(app) -> Path | None:
    """Wohin das Protokoll zusaetzlich geschrieben wird, oder ``None``.

    Drei Faelle, in dieser Reihenfolge:

    * ``LOG_DATEI`` gesetzt und nicht leer -> genau dieser Pfad.
    * ``LOG_DATEI`` ausdruecklich leer -> **kein** Datei-Ziel. Das ist der Weg
      fuer jeden, der sein Protokoll ueber ``docker logs`` oder journald
      einsammelt und keine zweite Kopie auf der Platte will.
    * nicht gesetzt -> neben die SQLite-Datei. Steht dort keine SQLite-URI
      (oder ``:memory:``), gibt es kein Verzeichnis, das dem Betreiber gehoert
      -- dann bleibt es bei der Konsole.
    """
    roh = os.environ.get('LOG_DATEI')
    if roh is not None:
        roh = roh.strip()
        return Path(roh) if roh else None

    if (os.environ.get('DATA_DIR') or '').strip():
        # NK-132: das Protokoll gehoert in den Datenordner.
        return Path(os.environ['DATA_DIR'].strip()) / LOGDATEINAME
    uri = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    if not uri.startswith('sqlite:///'):
        return None
    datei = uri[len('sqlite:///'):]
    if not datei or datei.endswith(':memory:'):
        return None
    return Path(datei).parent / LOGDATEINAME


class Anfragekontext(logging.Filter):
    """Ergaenzt jede Zeile um die Anfrage, aus der sie stammt.

    Der Filter haengt an den **Ausgaengen**, nicht am Logger: Filter eines
    Loggers laufen nur fuer Zeilen, die an genau diesem Logger entstehen.
    ``nebenkosten.nas`` schreibt in dieselben Ausgaenge, wuerde am Logger
    vorbeilaufen und dem Formatter ein fehlendes ``anfrage`` hinterlassen --
    was ``logging`` mit einer Fehlermeldung quittiert, die zwischen den
    echten Zeilen steht und wie eine davon aussieht.

    **Ohne Abfragezeichenkette.** ``request.full_path`` haengt alles an, was
    hinter dem Fragezeichen stand; dort landen Kennungen und Einmal-Token, und
    ein Protokoll ist die Datei, die man am ehesten weiterschickt, wenn etwas
    kaputt ist.
    """

    def filter(self, satz: logging.LogRecord) -> bool:
        satz.anfrage = ''
        if has_request_context():
            satz.anfrage = f' [{request.method} {request.path}]'
        return True


def _ausgang_bauen(handler, merkmal: str):
    """Format, Filter und Erkennungsmerkmal an einen Ausgang haengen.

    Der Ausgang bekommt **keine** eigene Stufe. Zwei Stellen, die entscheiden,
    was durchkommt, sind eine zu viel: wer spaeter ``protokoll.setLevel`` ruft
    -- ein Test, ein Wartungsskript -- bekaeme sonst weiter nichts zu sehen und
    suchte den Grund am falschen Ort.
    """
    handler.setFormatter(logging.Formatter(FORMAT, datefmt=DATUMSFORMAT))
    handler.addFilter(Anfragekontext())
    setattr(handler, merkmal, True)
    return handler


class Mehrprozessrotierend(logging.handlers.RotatingFileHandler):
    """Ein rotierendes Protokoll, das zwei gunicorn-Arbeiter vertraegt.

    Das Abbild startet mit ``--workers 2``. Beide Prozesse haengen einen
    eigenen Handler an dieselbe Datei, und der eingebaute
    ``RotatingFileHandler`` weiss nichts davon. Rotiert Arbeiter A, benennt er
    die Datei um und legt eine neue an -- B schreibt danach weiter in den alten
    Dateideskriptor, der inzwischen ``nebenkosten.log.1`` heisst und beim
    naechsten Durchlauf geloescht wird.

    Nachgemessen mit ungleicher Last (ein Arbeiter viel, einer wenig, gleiche
    Parameter): von 20 Zeilen des leisen Arbeiters ueberlebten in **einem**
    Prozess 19, auf zwei Prozesse verteilt **keine einzige**. Das trifft genau
    die falschen Zeilen -- wer wenig protokolliert, meldet Seltenes, und das
    ist das, was man spaeter sucht.

    Zwei Zusaetze beheben das, beide ohne neue Abhaengigkeit:

    * vor jeder Zeile wird geprueft, ob die Datei in der Hand noch die Datei
      auf der Platte ist (Inode-Vergleich, wie ``WatchedFileHandler``);
    * das Umschichten selbst laeuft unter einer Dateisperre, und wer sie
      bekommt, sieht nach, ob ein anderer die Arbeit schon getan hat.

    Ohne ``fcntl`` -- also unter Windows -- bleibt es beim alten Verhalten.
    Dort laeuft die Anwendung mit einem Prozess, und der Fall tritt nicht ein.
    """

    @property
    def _sperrpfad(self) -> str:
        return self.baseFilename + '.sperre'

    def emit(self, satz):
        self._wieder_anhaengen()
        super().emit(satz)

    def _wieder_anhaengen(self):
        """Neu oeffnen, falls ein anderer Prozess die Datei fortrotiert hat."""
        if self.stream is None or self._haengt_noch_an_der_richtigen_datei():
            return
        self.stream.close()
        self.stream = self._open()

    def _haengt_noch_an_der_richtigen_datei(self) -> bool:
        """Zeigt der offene Deskriptor auf das, was heute unter dem Namen liegt?

        Verglichen wird ueber Inode und Geraet, nicht ueber den Namen: nach einer
        fremden Rotation heisst dieselbe Datei nebenkosten.log.1, und der Name
        nebenkosten.log gehoert einer neuen. Laesst sich das nicht feststellen --
        die Datei ist weg oder nicht lesbar --, lautet die Antwort **Nein**: dann
        oeffnet der Aufrufer neu, und ein dabei auftretender Fehler geht den
        ueblichen Weg ueber handleError(), statt hier verschluckt zu werden.
        """
        try:
            auf_der_platte = os.stat(self.baseFilename)
            in_der_hand = os.fstat(self.stream.fileno())
        except OSError:
            return False
        return ((auf_der_platte.st_ino, auf_der_platte.st_dev)
                == (in_der_hand.st_ino, in_der_hand.st_dev))

    def doRollover(self):
        if fcntl is None:
            super().doRollover()
            return
        with open(self._sperrpfad, 'a', encoding='utf-8') as sperre:
            fcntl.flock(sperre.fileno(), fcntl.LOCK_EX)
            try:
                # Zwischen dem Entschluss zu rotieren und der Sperre kann ein
                # anderer Prozess fertig geworden sein. Dann ist die Datei
                # jetzt klein, und ein zweites Umschichten wuerfe einen
                # frischen Stand weg.
                self._wieder_anhaengen()
                try:
                    gross_genug = os.path.getsize(self.baseFilename) >= self.maxBytes
                except OSError:
                    gross_genug = True
                if self.maxBytes > 0 and not gross_genug:
                    return
                super().doRollover()
            finally:
                fcntl.flock(sperre.fileno(), fcntl.LOCK_UN)


def init_protokoll(app):
    """Haengt das Protokoll an stderr und an eine Datei, gibt den Logger zurueck.

    Idempotent: die Tests importieren app.py einmal, aber ein zweiter Aufruf
    (etwa aus einer Anwendungsfabrik) soll nicht jede Zeile doppelt schreiben.
    Erkannt werden die eigenen Ausgaenge an den Merkmalen ``_nk_ausgang`` und
    ``_nk_datei``.

    **Das Datei-Ziel darf den Start nicht verhindern.** Ein Verzeichnis ohne
    Schreibrecht, eine volle Platte, ein Pfad, den es nicht gibt: dann bleibt
    es bei der Konsole, und der Grund steht als Warnung in derselben Ausgabe. Eine
    Anwendung, die nicht hochkommt, weil sie ihr Protokoll nicht schreiben
    kann, hat den Zweck des Protokolls missverstanden.
    """
    stufe = _stufe()

    if not any(getattr(a, '_nk_ausgang', False) for a in protokoll.handlers):
        # stderr, nicht stdout: auf stdout schreiben die Konsolenbefehle ihre
        # Nutzdaten -- `flask users list`, `flask backup info`. Eine Zeile
        # Protokoll davor macht jedes `| jq` und jedes Skript kaputt, das die
        # Ausgabe weiterverarbeitet. `docker compose logs` zeigt beide Stroeme,
        # fuer den Betreiber aendert sich damit nichts.
        protokoll.addHandler(_ausgang_bauen(
            logging.StreamHandler(sys.stderr), '_nk_ausgang'))

    ziel = protokolldatei(app)
    if ziel is not None and not any(
            getattr(a, '_nk_datei', False) for a in protokoll.handlers):
        try:
            ziel.parent.mkdir(parents=True, exist_ok=True)
            datei = Mehrprozessrotierend(
                ziel,
                maxBytes=_zahl('LOG_MAX_MB', STANDARD_MAX_MB) * 1024 * 1024,
                backupCount=_zahl('LOG_ANZAHL', STANDARD_ANZAHL),
                encoding='utf-8',
            )
        except OSError as fehler:
            protokoll.warning(
                'Protokolldatei %s nicht beschreibbar (%s) -- es bleibt bei '
                'der Ausgabe auf der Konsole.', ziel, fehler)
        else:
            protokoll.addHandler(_ausgang_bauen(datei, '_nk_datei'))

    protokoll.setLevel(stufe)
    # Sonst schreibt der Wurzel-Logger dieselbe Zeile ein zweites Mal, sobald
    # irgendwer (gunicorn, pytest, eine Bibliothek) ihn konfiguriert hat.
    protokoll.propagate = False

    # Flasks eigener Logger meldet Dinge, die nicht durch unsere Handler gehen
    # (Start, Abbruch im Server). Dieselbe Stufe, damit LOG_LEVEL=DEBUG nicht
    # die Haelfte ausblendet.
    app.logger.setLevel(stufe)

    # Eine Zeile gleich beim Start, damit die Datei nie leer bleibt. Eine leere
    # Datei sagt naemlich nicht, ob das Protokoll traegt oder klemmt -- und der
    # Betreiber merkt es sonst erst an dem Tag, an dem er sie wirklich braucht.
    # Hier steht beides: welche Stufe gilt und wohin geschrieben wird.
    dateiausgang = next(
        (a for a in protokoll.handlers if getattr(a, '_nk_datei', False)), None)
    protokoll.info(
        'Protokoll bereit, Stufe %s, Ziel %s.',
        logging.getLevelName(stufe),
        getattr(dateiausgang, 'baseFilename', 'nur Konsole'))
    return protokoll


def _zurueckrollen():
    """Die Sitzung sauber zuruecklassen, was immer vorher passiert ist.

    Der Rollback selbst kann scheitern, etwa wenn die Verbindung weg ist. Dann
    bleibt nur, das zu protokollieren: wer hier eine Ausnahme durchliesse,
    bekaeme statt der deutschen 500 doch wieder die Standardseite von Flask.
    """
    try:
        db.session.rollback()
    except Exception:
        protokoll.exception('Rollback nach einem Fehler ist selbst gescheitert')


# Die Notseite fuer Aufrufer, die kein JSON lesen. Bewusst ohne Stylesheet und
# ohne Skript: sie muss auch dann noch ankommen, wenn die Anwendung so kaputt
# ist, dass sie keine Datei mehr ausliefern kann.
SEITE = (
    '<!doctype html>\n'
    '<html lang="de"><head><meta charset="utf-8">'
    '<title>Fehler</title></head>\n'
    '<body style="font-family:sans-serif;margin:3rem;max-width:34rem">\n'
    '<h1>Es ist ein Fehler aufgetreten.</h1>\n'
    '<p>{text}</p>\n'
    '<p>Vorgangsnummer <strong>{nummer}</strong> &mdash; bitte bei einer '
    'Rückfrage mit angeben.</p>\n'
    '<p><a href="/">Zurück zur Übersicht</a></p>\n'
    '</body></html>\n'
)


def antwort_zu_fehler(nummer: str):
    """Die Antwort zu einer unbehandelten Ausnahme, als JSON oder als Seite.

    Dieselbe Unterscheidung wie bei den HTTP-Fehlern: das Frontend holt alles
    per ``fetch`` und liest ``error``, ein Vermieter mit der Adresse im Browser
    bekaeme davon nur geschweifte Klammern zu sehen. Beide Wege nennen denselben
    Satz und dieselbe Nummer.
    """
    satz = f'{ALLGEMEIN} Vorgangsnummer {nummer}.'
    if not moechte_json():
        return (
            SEITE.format(text=ALLGEMEIN, nummer=nummer),
            500,
            {'Content-Type': 'text/html; charset=utf-8'},
        )
    return jsonify({'error': satz, 'vorgang': nummer}), 500


def init_fehlerbehandlung(app):
    """Registriert die beiden Handler und das Protokoll.

    Reihenfolge der Handler spielt keine Rolle, Flask sucht ueber die
    Klassenhierarchie: EingabeFehler (NK-028) und der 413 (NK-029) sind
    naeher an ihrer Ausnahme als HTTPException beziehungsweise Exception und
    gewinnen deshalb, obwohl sie frueher registriert wurden.
    """
    init_protokoll(app)

    @app.errorhandler(HTTPException)
    def _http_fehler(fehler):
        """400 bis 503 als deutsche JSON-Antwort statt Werkzeug-Standardseite.

        Nur fuer Aufrufer, die JSON erwarten. Wer mit dem Browser eine falsche
        Adresse eintippt, soll weiter die HTML-Seite sehen -- ein nackter
        JSON-Rumpf im Browserfenster sieht nach Absturz aus, obwohl nur der
        Link falsch war.
        """
        _zurueckrollen()
        if fehler.code and fehler.code >= 500:
            protokoll.error('%s %s -> %s %s', request.method, request.path,
                            fehler.code, fehler.name)
        if not moechte_json():
            return fehler
        rumpf = {'error': HTTP_MELDUNGEN.get(fehler.code, fehler.description)}
        return jsonify(rumpf), fehler.code

    @app.errorhandler(Exception)
    def _unbehandelt(fehler):
        """Alles, was keine HTTPException ist: rollback, protokollieren, 500."""
        _zurueckrollen()
        nummer = vorgangsnummer()
        protokoll.exception(
            'Vorgang %s: %s %s brach ab (%s)',
            nummer, request.method, request.path, type(fehler).__name__,
        )
        return antwort_zu_fehler(nummer)

    return app
