"""NK-126 — die Oberfläche lädt nichts aus dem Internet.

Vor NK-126 lud ``static/index.html`` Google Fonts, Phosphor-Icons (unpkg)
und Chart.js (jsdelivr) aus dem Netz — ohne Versionsbindung und ohne
``integrity`` (F-54). Jede neue oder kompromittierte Version dieser Pakete
lief mit vollem Datenzugriff, ohne Internet fehlten Icons und Diagramme,
und Google Fonts übertrug die IP-Adresse jedes Aufrufs (ZIEL Prinzip 1,
DSGVO).

Jetzt liegen alle drei Pakete unter ``static/vendor/`` mit fester Version
und beigeleget Lizenz. Diese Prüfungen halten das fest:

1. Die vom Projekt geschriebenen Dateien (``index.html``, ``style.css``,
   ``app.js``) enthalten keine fremde Adresse. ``data:``-Adressen sind
   erlaubt: sie tragen die Daten in sich (SVG-Namensraum im Kopfpfeil von
   style.css) und gehen an niemanden.
2. Die Pakete liegen mit Lizenzdatei vor — Chart.js (MIT),
   Phosphor-Icons (MIT), die Schriften Geist und Geist Mono
   (Design Aufgaben) sowie Outfit (OFL, noch von den Anmeldeseiten verlinkt).
3. Jede gebündelte Datei ist gegen ihren sha256 gepinnt. Die Kommentare
   im Bündel von Chart.js nennen Webseiten — gesehen wird das nicht als
   Netzadresse, sondern dadurch, dass der Inhalt unveränderlich ist: Wer
   ein Paket tauscht, muss den Pin bewusst fortschreiben.
4. ``index.html`` verweist nur auf die gebündelten Pfade.
5. Das Bündel wird ausgeliefert — ein weggefiltertes Vendor-Verzeichnis
   (.dockerignore, falscher Pfad) würde die Oberfläche unbenutzbar machen.
"""

import hashlib
import re
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / 'static'
VENDOR = STATIC / 'vendor'

# Die Dateien, die das Projekt selbst schreibt. Die Bündel unter vendor/
# bewacht der Pin-Test unten — in ihren Kommentaren stehen Webseiten.
PROJEKT_DATEIEN = ('index.html', 'style.css', 'app.js')

# Paket → (Dateien, Lizenzdatei, Kennzeichen im Inhalt)
PAKETE = {
    'chartjs': (
        ['chartjs/chart.umd.min.js'],
        'chartjs/LICENSE.md',
        b'Chart.js v4.4.4',
    ),
    'phosphor': (
        ['phosphor/regular/style.css', 'phosphor/regular/Phosphor.woff2',
         'phosphor/fill/style.css', 'phosphor/fill/Phosphor-Fill.woff2'],
        'phosphor/LICENSE',
        b'font-family: "Phosphor";',
    ),
    'fonts/outfit': (
        ['fonts/outfit/outfit.css', 'fonts/outfit/outfit-latin.woff2',
         'fonts/outfit/outfit-latin-ext.woff2'],
        'fonts/outfit/OFL.txt',
        None,
    ),
    'fonts/geist': (
        ['fonts/geist/geist.css',
         'fonts/geist/geist-latin.woff2',
         'fonts/geist/geist-latin-ext.woff2'],
        'fonts/geist/OFL.txt',
        b"font-family: 'Geist';",
    ),
    'fonts/geist-mono': (
        ['fonts/geist-mono/geist-mono.css',
         'fonts/geist-mono/geist-mono-latin.woff2',
         'fonts/geist-mono/geist-mono-latin-ext.woff2'],
        'fonts/geist-mono/OFL.txt',
        b"font-family: 'Geist Mono';",
    ),
    # Legacy-Build: läuft auch in der Edge-WebView der Desktop-App.
    'pdfjs': (
        ['pdfjs/pdf.min.js', 'pdfjs/pdf.worker.min.js'],
        'pdfjs/LICENSE',
        b'"4.10.38"',
    ),
}

# Der Pin: sha256 jeder gebündelten Datei. Ein neues Paket heißt: Datei
# tauschen, Version im Kennzeichen prüfen, Pin fortschreiben — bewusst,
# nicht still. Aenderungen hier sind ein Release-Ereignis.
PINS = {
    'chartjs/chart.umd.min.js':
        'fed6a739f8d0f0687174de6cd14745fc0fc7809144ab113d22908a26bf0d7fea',
    'phosphor/regular/style.css':
        '873761b8711147dc516b6102936e9ad005f3a3015349efcde1a496f0326f1051',
    'phosphor/regular/Phosphor.woff2':
        'c2ea45ea05ff5c7df1936770c104725f2a68f43fd343f35f3da23a30b27de32a',
    'phosphor/fill/style.css':
        '555980683a582c1910a954648b4ae38f58d76e797f02bfdc2c5e817901e6d4fc',
    'phosphor/fill/Phosphor-Fill.woff2':
        '660bd6045c0e0d9756cddb8ba2ece3aad855df7d4a170ef23f7b1c0bf511c430',
    'fonts/outfit/outfit.css':
        '9383a2ab828bfcc1cd64958340eaafc73289b1fdee4fb7d416c5156958394ca6',
    'fonts/outfit/outfit-latin.woff2':
        '6c18d579fd87c3776be068b762cbc83fde3acb543d49eabd3ade842eb987e887',
    'fonts/outfit/outfit-latin-ext.woff2':
        '0f53d1c03b3918d744a843b5039001ee31695ca1e255e3914188df81beb461e9',
    'fonts/geist/geist.css':
        '64d6d98df287c81e0d03783000c17716af56dfe7a98ee772e4c1e79ce09b0e80',
    'fonts/geist/geist-latin.woff2':
        '19f9c92546aa300c312235e3125af1b81394d8db9a4bc4a425cd5b641d2d54e1',
    'fonts/geist/geist-latin-ext.woff2':
        '824f485b5d26e2f2da3c2b236132ece1bc8e4e43373452950bb0e40548b4313f',
    'fonts/geist-mono/geist-mono.css':
        '16c22d13f6ec8507a92e802dbf0561e926f64ee161c92d1cea9328f868ddec0f',
    'fonts/geist-mono/geist-mono-latin.woff2':
        '684ad5b531f81d43c1e8c7038262d5db7cdc1f68006e04d6c7769efa8d33c8cc',
    'fonts/geist-mono/geist-mono-latin-ext.woff2':
        '1a189eb997c3e2ece68373e387afaec9e8617424186c4b1ab3cff7c54ba6223b',
    'pdfjs/pdf.min.js':
        '44ec6f011027ee77791386b66c14876a5fc29e20bf0433c07c6726fff7212b72',
    'pdfjs/pdf.worker.min.js':
        'bd88805178a26c729db8c0107a5b630cb900ec070f4d8c7529a3e45530afd41d',
}


def _ohne_data_uris(text):
    """Nimmt ``data:``-Adressen heraus, bevor nach http gesucht wird.

    In einem eingebetteten SVG steht der Namensraum
    ``http://www.w3.org/2000/svg`` — ein Bezeichner, keine Adresse, die
    geholt würde. Die Adresse in style.css steht in doppelten
    Anführungszeichen und trägt in sich einfach zitierte Attribute
    (``xmlns='…'``); sie endet deshalb am schließenden doppelten
    Anführungszeichen, nicht am ersten einfachen. Zuerst die zitierte
    Form nehmen, dann eine unzitierte als Rückfall.
    """
    text = re.sub(r'"data:[^"]*"', '""', text)
    return re.sub(r'data:[a-z]+/[a-z0-9.+-]+;[^\s"\'<>)]*', '', text)


def test_projektdateien_holen_nichts_vom_netz():
    """Keine vom Projekt geschriebene Datei verweist auf einen Server (F-54)."""
    verstoesse = []
    for name in PROJEKT_DATEIEN:
        inhalt = _ohne_data_uris((STATIC / name).read_text(encoding='utf-8'))
        for fund in re.findall(r'https?://[^\s"\'<>)\]]+', inhalt):
            verstoesse.append(f'{name}: {fund}')
    assert verstoesse == [], (
        'Die Oberfläche lädt Code aus dem Internet (F-54): '
        + '; '.join(verstoesse))


@pytest.mark.parametrize('paket', sorted(PAKETE), ids=sorted(PAKETE))
def test_paket_liegt_komplett_mit_lizenz(paket):
    dateien, lizenz, kennzeichen = PAKETE[paket]
    for rel in dateien:
        assert (VENDOR / rel).is_file(), f'{rel} fehlt im Bündel.'
    assert (VENDOR / lizenz).is_file(), (
        f'Lizenz {lizenz} fehlt (Drittlizenzen mitliefern).')
    if kennzeichen is not None:
        erstes = VENDOR / dateien[0]
        assert kennzeichen in erstes.read_bytes(), (
            f'{paket}: die gebündelte Datei trägt nicht das erwartete Paket.')


def test_gebuendelte_dateien_sind_gepinnt():
    """Der sha256 jedes Bündels steht im Test — Tausch nur bewusst."""
    abweichungen = []
    for rel, pin in sorted(PINS.items()):
        datei = VENDOR / rel
        if not datei.is_file():
            abweichungen.append(f'{rel}: fehlt')
            continue
        ist = hashlib.sha256(datei.read_bytes()).hexdigest()
        if ist != pin:
            abweichungen.append(f'{rel}: Pin fortschreiben (neuer sha256 {ist})')
    assert abweichungen == [], '; '.join(abweichungen)


def test_index_laedt_nur_gebuendeltes():
    """index.html kennt nur lokale Pfade, keine CDN-Namen mehr."""
    html = (STATIC / 'index.html').read_text(encoding='utf-8')
    for fremd in ('fonts.googleapis', 'fonts.gstatic', 'unpkg.com',
                  'cdn.jsdelivr.net'):
        assert fremd not in html, f'index.html verweist noch auf {fremd}.'
    for gebuendelt in ('vendor/fonts/geist/geist.css',
                       'vendor/fonts/geist-mono/geist-mono.css',
                       'vendor/phosphor/regular/style.css',
                       'vendor/phosphor/fill/style.css',
                       'vendor/chartjs/chart.umd.min.js'):
        assert gebuendelt in html, f'index.html bindet {gebuendelt} nicht ein.'


def test_gebuendelte_dateien_werden_ausgeliefert(auth_client):
    """Das Vendor-Verzeichnis erreicht den Browser — nicht nur das Dateisystem."""
    antwort = auth_client.get('/static/vendor/chartjs/chart.umd.min.js')
    assert antwort.status_code == 200
    assert b'Chart.js' in antwort.data
    for schrift in ('outfit/outfit-latin.woff2',
                    'geist/geist-latin.woff2',
                    'geist-mono/geist-mono-latin.woff2'):
        antwort = auth_client.get(f'/static/vendor/fonts/{schrift}')
        assert antwort.status_code == 200, schrift
        assert antwort.data[:4] == b'wOF2', schrift


def test_pdfjs_wird_als_skript_ausgeliefert(auth_client):
    """pdf.js lädt als Modul und Worker: das geht nur mit JS-Medientyp."""
    for datei in ('pdf.min.js', 'pdf.worker.min.js'):
        antwort = auth_client.get(f'/static/vendor/pdfjs/{datei}')
        assert antwort.status_code == 200, datei
        assert 'javascript' in antwort.content_type, (datei, antwort.content_type)
