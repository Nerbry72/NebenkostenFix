"""Kostenarten eindeutig halten (NK-095).

``cost_categories.name`` hatte kein ``UNIQUE``. Die Folge stand schon einmal
im Protokoll: beim Start legte ``seed_database()`` bei vier gunicorn-Arbeitern
neun Kostenkategorien statt acht an, weil es erst liest und dann schreibt.
NK-024 hat das mit einer Sperrdatei entschaerft -- aber nur den Start. Zwei
Kategorien "Heizung" bleiben auch danach moeglich, ueber die Oberflaeche,
ueber einen Import, ueber eine eingespielte Sicherung.

Zwei gleichnamige Kostenarten sind kein Schoenheitsfehler. Der Vermieter sieht
zweimal "Heizung" in derselben Auswahlliste und kann nicht erkennen, welche
die Rechnungen traegt; die Abrechnung rechnet dann mit der einen und laesst
die andere weg. Das faellt erst auf, wenn die Summe nicht stimmt.

Die Regel gehoert deshalb ins Schema, nicht in den Anwendungscode: eine
Bedingung, die die Datenbank durchsetzt, gilt auch fuer den Weg, an den
niemand gedacht hat. Die Revision ``9c1f4a2b7d33`` traegt sie nach.

Der schwierige Teil ist nicht das ``UNIQUE``, sondern der Weg dorthin. Eine
Instanz, die seit Monaten laeuft, kann Dubletten schon haben -- und dann
scheitert die Wanderung beim Hochfahren mit einem ``IntegrityError``, der
niemandem sagt, was zu tun ist. Darum:

* Die Revision prueft **vorher** und bricht mit einem deutschen Satz ab, der
  die betroffenen Namen nennt. Kein Datensatz wird dabei angefasst.
* Dieses Modul bringt das Werkzeug zum Aufraeumen mit:

      flask kategorien dubletten
      flask kategorien zusammenfuehren "Heizung"

  Zusammenfuehren haengt alles um, was an den ueberzaehligen Eintraegen
  haengt (Rechnungen, Zaehler, Mieterprofile, Positionen fertiger
  Abrechnungen), und loescht danach die leeren Eintraege. Die kleinste ``id``
  bleibt stehen, weil sie die aelteste ist und mit hoher Wahrscheinlichkeit
  die aus dem Seed.

**Henne und Ei (F-16).** ``app.py`` wandert beim *Import*, nicht erst beim
Bedienen eines Ports -- die Zeilen stehen auf Modulebene. Damit loest auch
``flask kategorien dubletten`` die Wanderung aus, und eine Wanderung, die an
Dubletten abbricht, sperrt ausgerechnet das Werkzeug mit weg, das sie in der
Fehlermeldung empfiehlt. Darum gibt es den Weg zweimal:

* ``flask kategorien ...`` fuer den Normalfall -- die Instanz laeuft, jemand
  will vor einer Aktualisierung nachsehen.
* ``python scripts/kostenarten.py ...`` fuer den Notfall. Das Skript kennt
  weder Flask noch ``models.py``, es oeffnet die SQLite-Datei direkt. Es
  laeuft also auch dann noch, wenn die Anwendung nicht mehr hochkommt.

Die Fehlermeldung der Wanderung nennt deshalb den Skriptweg. Der andere waere
ein Verweis auf eine verschlossene Tuer.

Zusammengefuehrt wird nur auf Ansage. Eine Wanderung, die von sich aus
Datensaetze verschmilzt, trifft eine Entscheidung, die dem Vermieter gehoert:
vielleicht waren die zwei "Heizung" gar nicht dasselbe, sondern zwei Haeuser.

Verglichen wird **genau**, Zeichen fuer Zeichen. "Heizung" und "heizung" sind
damit zwei Kostenarten, und ``UNIQUE`` laesst sie nebeneinander stehen. Das
ist bewusst so: derselbe exakte Vergleich steckt schon im Seed
(``filter_by(name=...)``), und ein Constraint, der anders vergleicht als der
Code darueber, waere die naechste Ueberraschung. Fastdubletten meldet
``flask kategorien dubletten`` trotzdem -- als Hinweis, nicht als Fehler.
"""

from __future__ import annotations

# Alles, was auf eine Kostenart zeigt. Beim Zusammenfuehren muss jede dieser
# Tabellen mitkommen, sonst haengt hinterher eine Zeile an einer geloeschten
# id -- SQLite prueft Fremdschluessel nicht von sich aus.
ABHAENGIGE = (
    ('cost_invoices', 'Rechnungen'),
    ('meters', 'Zaehler'),
    ('tenant_cost_profiles', 'Mieterprofile'),
    ('billing_report_categories', 'Positionen in Abrechnungen'),
)

TABELLE = 'cost_categories'


def _fahre(verbindung, sql, werte=()):
    """Ein SQL-Befehl, egal ob auf SQLAlchemy oder auf einer sqlite3-Verbindung.

    Die beiden koennen dasselbe, heissen aber verschieden. Diese drei Zeilen
    sind der Preis dafuer, dass die Logik nur einmal existiert -- sonst haette
    das Notfallskript eine eigene Kopie, und Kopien laufen auseinander.
    """
    if hasattr(verbindung, 'exec_driver_sql'):
        return verbindung.exec_driver_sql(sql, werte)
    return verbindung.execute(sql, werte)


class KategorieFehler(RuntimeError):
    """Etwas an den Kostenarten steht dem verlangten Schritt im Weg."""


def dubletten_finden(verbindung) -> dict[str, list[int]]:
    """Namen, die mehr als einmal vorkommen, je mit ihren ids aufsteigend.

    Nimmt eine SQLAlchemy-Verbindung und kein Modell, damit die Revision
    dieselbe Funktion benutzen kann: in einer Wanderung gibt es ``models.py``
    noch nicht verlaesslich -- die Klassen beschreiben den Zielzustand, die
    Datenbank steht aber noch auf dem alten.
    """
    # Bandit-Ausnahme: Tabellenname aus Konstante, Werte gebunden
    zeilen = _fahre(verbindung, f'SELECT id, name FROM {TABELLE} ORDER BY id').fetchall()  # nosec B608
    nach_name: dict[str, list[int]] = {}
    for kennung, name in zeilen:
        nach_name.setdefault(name, []).append(kennung)
    return {name: ids for name, ids in nach_name.items() if len(ids) > 1}


def fastdubletten_finden(verbindung) -> dict[str, list[str]]:
    """Namen, die sich nur in Gross-/Kleinschreibung oder Leerraum unterscheiden.

    Kein Fehler -- ``UNIQUE`` laesst sie zu. Aber wer "Heizung" und "heizung"
    nebeneinander stehen hat, hat sich fast sicher vertippt, und es ist
    freundlicher, das beim Aufraeumen gleich mit zu zeigen.
    """
    # Bandit-Ausnahme: Tabellenname aus Konstante, Werte gebunden
    zeilen = _fahre(verbindung, f'SELECT name FROM {TABELLE} ORDER BY id').fetchall()  # nosec B608
    nach_schluessel: dict[str, list[str]] = {}
    for (name,) in zeilen:
        nach_schluessel.setdefault(name.strip().casefold(), []).append(name)
    return {
        schluessel: namen for schluessel, namen in nach_schluessel.items()
        if len(set(namen)) > 1
    }


def meldung_zu_dubletten(dubletten: dict[str, list[int]]) -> str:
    """Der Satz, den ein Mensch liest, wenn die Wanderung abbricht."""
    zeilen = [
        'Es gibt Kostenarten mit gleichem Namen. Sie müssen zusammengeführt '
        'oder umbenannt werden, bevor der Name eindeutig werden kann:',
        '',
    ]
    for name, ids in sorted(dubletten.items()):
        zeilen.append(f'  "{name}" — {len(ids)}x, ids {", ".join(str(i) for i in ids)}')
    zeilen += [
        '',
        'Aufräumen. Der Weg über "flask" fällt hier aus: die Anwendung',
        'wandert schon beim Start, also bricht auch jeder flask-Befehl mit',
        'dieser Meldung ab (F-16). Das Skript kommt ohne sie aus:',
        '',
        '  python scripts/kostenarten.py sichern      # erst eine Kopie!',
        '  python scripts/kostenarten.py dubletten',
        '  python scripts/kostenarten.py zusammenfuehren "<Name>"',
    ]
    return '\n'.join(zeilen)


def zusammenfuehren(verbindung, name: str) -> dict[str, int]:
    """Alle Kostenarten dieses Namens auf die kleinste id zusammenziehen.

    Gibt zurueck, wie viele Zeilen je abhaengiger Tabelle umgehaengt wurden.
    Committet nicht -- das entscheidet der Aufrufer, und bei einem Fehler
    mittendrin soll nichts halb umgehaengt stehenbleiben.
    """
    ids = [
        kennung for (kennung,) in _fahre(
            # Bandit-Ausnahme: Tabellenname aus Konstante, Werte gebunden
            verbindung, f'SELECT id FROM {TABELLE} WHERE name = ? ORDER BY id', (name,)  # nosec B608
        ).fetchall()
    ]
    if len(ids) < 2:
        raise KategorieFehler(
            f'Es gibt keine zwei Kostenarten mit dem Namen "{name}".'
        )

    behalten, aufloesen = ids[0], ids[1:]
    platzhalter = ', '.join('?' * len(aufloesen))
    bilanz: dict[str, int] = {}

    for tabelle, beschriftung in ABHAENGIGE:
        ergebnis = _fahre(
            verbindung,
            # Bandit-Ausnahme: Tabellenname aus Konstante, Werte gebunden
            f'UPDATE {tabelle} SET category_id = ? '  # nosec B608
            f'WHERE category_id IN ({platzhalter})',
            (behalten, *aufloesen),
        )
        bilanz[beschriftung] = ergebnis.rowcount or 0

    # Ein Mieter kann jetzt zweimal dieselbe Kostenart im Profil haben -- einmal
    # ueber die behaltene Kostenart, einmal ueber eine umgehaengte. Das waere
    # keine kaputte Zeile, aber eine, die die Oberflaeche doppelt anzeigt.
    # Es bleibt die kleinste id, also das aelteste Profil.
    # ... und zwar nur fuer die behaltene Kostenart. Ein ``NOT IN (SELECT MIN(id)
    # ... GROUP BY tenant_id, category_id)`` ohne diese Einschraenkung raeumt im
    # ganzen Bestand auf -- auch dort, wo niemand darum gebeten hat. Eine
    # Aufraeumaktion, die nebenbei fremde Zeilen loescht, ist keine.
    entdoppelt = _fahre(
        verbindung,
        'DELETE FROM tenant_cost_profiles WHERE category_id = ? AND id NOT IN ('
        '  SELECT MIN(id) FROM tenant_cost_profiles WHERE category_id = ?'
        '  GROUP BY tenant_id'
        ')',
        (behalten, behalten),
    )
    bilanz['Entdoppelte Mieterprofile'] = entdoppelt.rowcount or 0

    # Bandit-Ausnahme: Tabellenname aus Konstante, Werte gebunden
    _fahre(verbindung, f'DELETE FROM {TABELLE} WHERE id IN ({platzhalter})',  # nosec B608
           tuple(aufloesen))
    bilanz['Gelöschte Kostenarten'] = len(aufloesen)
    bilanz['Behalten als id'] = behalten
    return bilanz


def init_kategorien(app):
    """flask kategorien dubletten|zusammenfuehren (NK-095)."""
    import click
    from flask.cli import AppGroup

    from nebenkostenfix.models import db

    kategorien_cli = AppGroup(
        'kategorien', help='Kostenarten prüfen und aufräumen (NK-095).')

    @kategorien_cli.command('dubletten')
    def zeigen():
        """Gleichnamige Kostenarten auflisten, ohne etwas zu aendern."""
        verbindung = db.session.connection()
        dubletten = dubletten_finden(verbindung)
        if dubletten:
            click.echo(meldung_zu_dubletten(dubletten))
        else:
            click.echo('Keine gleichnamigen Kostenarten.')

        fast = fastdubletten_finden(verbindung)
        if fast:
            click.echo('')
            click.echo('Hinweis — unterscheiden sich nur in Schreibweise:')
            for namen in fast.values():
                click.echo('  ' + ' / '.join(f'"{n}"' for n in sorted(set(namen))))

    @kategorien_cli.command('zusammenfuehren')
    @click.argument('name')
    @click.option('--ja', is_flag=True, default=False,
                  help='Ohne Rückfrage ausführen.')
    def verschmelzen(name, ja):
        """Alle Kostenarten mit diesem NAMEN zu einer machen."""
        if not ja:
            click.echo(
                'Das hängt Rechnungen, Zähler, Mieterprofile und Positionen '
                'fertiger Abrechnungen um und löscht danach die überzähligen '
                'Kostenarten. Vorher eine Sicherung anlegen: flask backup create'
            )
            click.confirm(f'"{name}" jetzt zusammenführen?', abort=True)
        try:
            bilanz = zusammenfuehren(db.session.connection(), name)
        except KategorieFehler as fehler:
            db.session.rollback()
            raise click.ClickException(str(fehler))
        db.session.commit()
        for beschriftung, anzahl in bilanz.items():
            click.echo(f'{beschriftung}: {anzahl}')

    app.cli.add_command(kategorien_cli)
    return app
