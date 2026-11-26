"""Das Layout der Abrechnungs-PDF: welche Blöcke, in welcher Folge, wo der GiroCode.

Die Abrechnung besteht aus Blöcken (``PDFGenerator._block_<id>``). Der
Vermieter kann optionale Blöcke ausschalten, die Reihenfolge ändern und
wählen, wo der GiroCode steht. Gespeichert wird das in der Einstellung
``pdf_layout`` (``einstellungen.py``); ``None`` heißt Werkseinstellung.

Format (JSON)::

    {"bloecke": [{"block": "deckblatt", "an": true},
                 {"block": "uebersicht", "an": false}, ...],
     "girocode": "zahlung" | "deckblatt" | "aus"}

``bloecke`` nennt jeden Block genau einmal, in der Reihenfolge des Blatts.

Pflicht und fest -- was ein Vermieter nicht abwählen kann:

* ``deckblatt`` ist Pflicht und steht fest an erster Stelle: Es ist der
  Brief, der Mieter, Zeitraum, Saldo und Vorauszahlungen nennt; alles
  andere ist Anlage dazu.
* ``kostenaufstellung`` ist Pflicht: Sie trägt die Mindestangaben einer
  Betriebskostenabrechnung (Gesamtkosten, Verteilerschlüssel, Anteil,
  Abzug der Vorauszahlungen; § 556 Abs. 3 BGB, § 259 BGB).
* ``heizung_co2`` ist Pflicht: Die Aufteilung der CO2-Kosten gehört in
  die Heizkostenabrechnung (§ 7 CO2KostAufG); fehlt sie, darf der Mieter
  kürzen. Ohne Heizungsteil bleibt der Block ohnehin leer.
* ``zahlung`` ist Pflicht: Er sagt, was bis wann zu zahlen ist oder
  zurückkommt, und trägt im Standard den GiroCode.

Die übrigen Blöcke (Übersicht, Ausweis nach § 35a EStG, Belegliste,
Verbrauchsnachweise) erläutern die Rechnung nur und dürfen aus.

Zwei Wege mit dem Layout: ``pruefen()`` ist streng und meldet jeden
Fehler auf Deutsch (Speichern und Vorschau). ``laden()`` ist tolerant
und macht aus allem ein gültiges Layout (Erzeugen, Einspielen einer
Sicherung): Unbekanntes fällt weg, Fehlendes rückt an seine Standardstelle,
Pflichtblöcke bleiben an, feste Blöcke an ihrem Platz.

Routen (``init_pdf_layout``)::

    GET    /api/einstellungen/pdf-layout
    PUT    /api/einstellungen/pdf-layout
    DELETE /api/einstellungen/pdf-layout
    POST   /api/einstellungen/pdf-layout/vorschau
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Block:
    id: str
    titel: str
    pflicht: bool = False
    #: Index, an dem der Block stehen muss; ``None`` heißt frei verschiebbar.
    stelle: int | None = None


#: Alle Blöcke in der Reihenfolge des Standardblatts.
BLOECKE = (
    Block('deckblatt', 'Deckblatt mit Anschreiben', pflicht=True, stelle=0),
    Block('uebersicht', 'Übersicht'),
    Block('kostenaufstellung', 'Aufstellung der Kosten', pflicht=True),
    Block('heizung_co2', 'Heizkosten und CO2-Aufteilung', pflicht=True),
    Block('ausweis_35a', 'Ausweis nach § 35a EStG'),
    Block('belegliste', 'Belegliste'),
    Block('zahlung', 'Zahlungshinweis', pflicht=True),
    Block('verbrauchsnachweise', 'Verbrauchsnachweise (ausführliche Fassung)'),
)
STANDARDLAYOUT = tuple(b.id for b in BLOECKE)
_NACH_ID = {b.id: b for b in BLOECKE}

#: Wo der GiroCode stehen kann; der erste ist der Standard.
GIROCODE_ORTE = (
    ('zahlung', 'Beim Zahlungshinweis am Ende'),
    ('deckblatt', 'Auf dem Deckblatt unter „Ihr Anteil“'),
    ('aus', 'Kein GiroCode'),
)
GIROCODE_STANDARD = GIROCODE_ORTE[0][0]
_ORTE = tuple(ort for ort, _ in GIROCODE_ORTE)


class LayoutFehler(ValueError):
    """Ein Layout, das so nicht gespeichert werden kann (Meldung auf Deutsch)."""


def standard() -> dict:
    """Die Werkseinstellung, jedes Mal frisch (der Aufrufer darf ändern)."""
    return {'bloecke': [{'block': b, 'an': True} for b in STANDARDLAYOUT],
            'girocode': GIROCODE_STANDARD}


#: So viele Zeichen eines unbekannten Werts nennt eine Fehlermeldung höchstens.
MELDUNG_HOECHSTENS = 50


def _kurz(wert) -> str:
    """Ein fremder Wert für die Meldung, nach ``MELDUNG_HOECHSTENS`` Zeichen gekappt."""
    text = str(wert)
    if len(text) <= MELDUNG_HOECHSTENS:
        return text
    return text[:MELDUNG_HOECHSTENS] + '…'


def _stellenwort(index: int) -> str:
    return 'erster Stelle' if index == 0 else f'Stelle {index + 1}'


def _fehlende_einfuegen(bloecke: list[dict]) -> list[dict]:
    """Jeder fehlende Block kommt hinter seinen Vorgänger im Standard."""
    ergebnis = list(bloecke)
    for index, block in enumerate(STANDARDLAYOUT):
        if any(e['block'] == block for e in ergebnis):
            continue
        ziel = 0
        for vorgaenger in reversed(STANDARDLAYOUT[:index]):
            stellen = [i for i, e in enumerate(ergebnis) if e['block'] == vorgaenger]
            if stellen:
                ziel = stellen[0] + 1
                break
        ergebnis.insert(ziel, {'block': block, 'an': True})
    return ergebnis


def pruefen(daten) -> dict:
    """Das Layout streng geprüft; fehlende Blöcke ergänzt. Wirft ``LayoutFehler``."""
    if not isinstance(daten, dict):
        raise LayoutFehler('Das Layout fehlt oder ist kein Objekt.')
    roh = daten.get('bloecke')
    if not isinstance(roh, list):
        raise LayoutFehler('„bloecke“ muss eine Liste der Blöcke sein.')
    girocode = daten.get('girocode', GIROCODE_STANDARD)
    if girocode not in _ORTE:
        raise LayoutFehler(
            f'Unbekannter Ort für den GiroCode: „{_kurz(girocode)}“. '
            f'Möglich sind: {", ".join(_ORTE)}.')

    bloecke, gesehen = [], set()
    for eintrag in roh:
        if not isinstance(eintrag, dict) or not isinstance(eintrag.get('block'), str):
            raise LayoutFehler('Jeder Eintrag in „bloecke“ braucht einen Blocknamen.')
        name = eintrag['block']
        if name not in _NACH_ID:
            raise LayoutFehler(f'Unbekannter Block „{_kurz(name)}“.')
        titel = _NACH_ID[name].titel
        if name in gesehen:
            raise LayoutFehler(f'Der Block „{titel}“ steht doppelt im Layout.')
        gesehen.add(name)
        an = eintrag.get('an', True)
        if not isinstance(an, bool):
            raise LayoutFehler(f'Beim Block „{titel}“ muss „an“ wahr oder falsch sein.')
        if _NACH_ID[name].pflicht and not an:
            raise LayoutFehler(
                f'Der Block „{titel}“ ist Pflicht und lässt sich nicht ausschalten.')
        bloecke.append({'block': name, 'an': an})

    bloecke = _fehlende_einfuegen(bloecke)
    for block in BLOECKE:
        if block.stelle is not None and bloecke[block.stelle]['block'] != block.id:
            raise LayoutFehler(
                f'Der Block „{block.titel}“ steht fest an {_stellenwort(block.stelle)}.')
    return {'bloecke': bloecke, 'girocode': girocode}


def laden(roh) -> dict:
    """Aus jedem gespeicherten Wert ein gültiges Layout -- nie ein Fehler."""
    if not isinstance(roh, dict) or not isinstance(roh.get('bloecke'), list):
        return standard()
    bloecke, gesehen = [], set()
    for eintrag in roh['bloecke']:
        if not isinstance(eintrag, dict):
            continue
        name = eintrag.get('block')
        if not isinstance(name, str) or name not in _NACH_ID or name in gesehen:
            continue
        gesehen.add(name)
        an = eintrag.get('an', True)
        an = an if isinstance(an, bool) else True
        bloecke.append({'block': name, 'an': an or _NACH_ID[name].pflicht})
    bloecke = _fehlende_einfuegen(bloecke)
    for block in sorted((b for b in BLOECKE if b.stelle is not None),
                        key=lambda b: b.stelle):
        bloecke = [e for e in bloecke if e['block'] != block.id]
        bloecke.insert(block.stelle, {'block': block.id, 'an': True})
    girocode = roh.get('girocode')
    return {'bloecke': bloecke,
            'girocode': girocode if girocode in _ORTE else GIROCODE_STANDARD}


def aktive_bloecke(layout: dict) -> list[str]:
    """Die eingeschalteten Blöcke eines (geladenen) Layouts, in Reihenfolge."""
    return [e['block'] for e in layout['bloecke'] if e['an']]


def aus_einstellungen(ordner=None) -> dict:
    """Das gespeicherte Layout, tolerant geladen."""
    from nebenkostenfix import einstellungen
    return laden(einstellungen.lesen(ordner).get('pdf_layout'))


def aus_schnappschuss(version) -> dict:
    """Das Layout, mit dem eine festgesetzte Abrechnung gesetzt wurde.

    Es steht im Schnappschuss der Version (``eingangsdaten['pdf_layout']``)
    und wird wie jede Einstellung tolerant geladen. Jedes weitere Blatt
    derselben Version (die zweite Fassung) nimmt dieses Layout, nicht das
    heutige -- beide Fassungen sehen gleich aus, egal was der Vermieter
    seitdem umgestellt hat. Versionen aus der Zeit vor dem einstellbaren
    Aufbau und Abrechnungen ohne Version tragen keins; ihr Blatt entstand
    im Standard, und dabei bleibt es.
    """
    eingangsdaten = getattr(version, 'eingangsdaten', None)
    if not isinstance(eingangsdaten, dict):
        return standard()
    return laden(eingangsdaten.get('pdf_layout'))


def _antwort(layout: dict) -> dict:
    return {
        'layout': layout,
        'standard': standard(),
        'ist_standard': layout == standard(),
        'bloecke': [{'block': b.id, 'titel': b.titel, 'pflicht': b.pflicht,
                     'fest': b.stelle is not None} for b in BLOECKE],
        'girocode_orte': [{'ort': ort, 'titel': titel} for ort, titel in GIROCODE_ORTE],
    }


def init_pdf_layout(app):
    from flask import Response, jsonify, request

    from nebenkostenfix import einstellungen

    def _geprueft():
        daten = request.get_json(silent=True)
        if daten is None:
            raise LayoutFehler('Das Layout fehlt (JSON erwartet).')
        return pruefen(daten)

    @app.route('/api/einstellungen/pdf-layout', methods=['GET'])
    def pdf_layout_anzeigen():
        return jsonify(_antwort(aus_einstellungen()))

    @app.route('/api/einstellungen/pdf-layout', methods=['PUT'])
    def pdf_layout_speichern():
        try:
            layout = _geprueft()
        except LayoutFehler as fehler:
            return jsonify({'error': str(fehler)}), 400
        einstellungen.schreiben(pdf_layout=layout)
        return jsonify(_antwort(layout))

    @app.route('/api/einstellungen/pdf-layout', methods=['DELETE'])
    def pdf_layout_zuruecksetzen():
        einstellungen.schreiben(pdf_layout=None)
        return jsonify(_antwort(standard()))

    @app.route('/api/einstellungen/pdf-layout/vorschau', methods=['POST'])
    def pdf_layout_vorschau():
        try:
            layout = _geprueft()
        except LayoutFehler as fehler:
            return jsonify({'error': str(fehler)}), 400
        from nebenkostenfix.pdf_vorschau import vorschau_pdf
        return Response(vorschau_pdf(layout), mimetype='application/pdf', headers={
            'Content-Disposition': 'inline; filename="Layout-Vorschau.pdf"',
            'X-Content-Type-Options': 'nosniff',
            'Cache-Control': 'no-store',
        })
