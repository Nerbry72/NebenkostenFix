"""NK-018: kein save_* darf einen vorhandenen Beleg ueberschreiben.

save_reading_photo und save_invoice_document bauen deterministische Namen aus
Kategorie, Immobilie und Zeitraum. Zwei Ablesefotos derselben Kategorie am
selben Tag ergaben denselben Pfad, und der zweite Upload hat den ersten
ueberschrieben. Bei einem echten Abrechnungsordner heisst das: Beleg weg,
bevor es eine Sicherung gibt.

Der Test deckt alle fuenf Speicherfunktionen ab, nicht nur die zwei reparierten,
damit die drei bereits korrekten nicht spaeter still zurueckfallen.
"""

from __future__ import annotations

import os
from datetime import date
from io import BytesIO

import pytest
from werkzeug.datastructures import FileStorage

from handlers.nas_handler import NASHandler


@pytest.fixture
def nas(tmp_path, monkeypatch):
    """Frischer Handler auf einem leeren Verzeichnis pro Test."""
    monkeypatch.setenv("NAS_MOUNT_PATH", str(tmp_path / "nas"))
    return NASHandler()


# Seit NK-129 prueft die Ablage den Inhalt: ohne PDF-Kopf keine Ablage.
PDF_KOPF = b"%PDF-1.4\n"


def _file(name: str, payload: bytes) -> FileStorage:
    return FileStorage(stream=BytesIO(PDF_KOPF + payload), filename=name)


def _read(nas: NASHandler, relative_path: str) -> bytes:
    with open(os.path.join(nas.nas_mount_path, relative_path), "rb") as fh:
        inhalt = fh.read()
    assert inhalt.startswith(PDF_KOPF)
    return inhalt[len(PDF_KOPF):]


# Jede Zeile: Name, Aufruf mit identischen Fachdaten, Rueckgabe ist (Pfad, Name)?
SAVERS = [
    (
        "save_reading_photo",
        lambda nas, f: nas.save_reading_photo(f, "Wasser", "Hauptstr 1", "WE 1", date(2025, 3, 4)),
        False,
    ),
    (
        "save_invoice_document",
        lambda nas, f: nas.save_invoice_document(
            f, "Heizung", "Hauptstr 1", date(2025, 1, 1), date(2025, 12, 31)
        ),
        False,
    ),
    (
        "save_general_document",
        lambda nas, f: nas.save_general_document(f, "Hauptstr 1"),
        True,
    ),
    (
        "save_billing_report",
        lambda nas, f: nas.save_billing_report(f, "Hauptstr 1", "WE 1", "Mueller"),
        True,
    ),
    (
        "save_tenant_contract",
        lambda nas, f: nas.save_tenant_contract(f, "Hauptstr 1", "WE 1", "Mueller"),
        False,
    ),
]


def _relpath(result, returns_tuple: bool) -> str:
    return result[0] if returns_tuple else result


@pytest.mark.parametrize("name,save,returns_tuple", SAVERS, ids=[s[0] for s in SAVERS])
def test_zweiter_beleg_ueberschreibt_den_ersten_nicht(nas, name, save, returns_tuple):
    """Gleiche Fachdaten, gleicher Dateiname, unterschiedlicher Inhalt."""
    erst = _relpath(save(nas, _file("beleg.pdf", b"erster beleg")), returns_tuple)
    zweit = _relpath(save(nas, _file("beleg.pdf", b"zweiter beleg")), returns_tuple)

    assert erst != zweit, f"{name}: beide Uploads landen auf demselben Pfad"
    assert _read(nas, erst) == b"erster beleg", f"{name}: der erste Beleg wurde ueberschrieben"
    assert _read(nas, zweit) == b"zweiter beleg"


@pytest.mark.parametrize("name,save,returns_tuple", SAVERS, ids=[s[0] for s in SAVERS])
def test_zaehler_laeuft_ueber_mehrere_belege(nas, name, save, returns_tuple):
    """Fuenf Uploads, fuenf Dateien, jede mit ihrem eigenen Inhalt."""
    pfade = [
        _relpath(save(nas, _file("beleg.pdf", f"beleg {i}".encode())), returns_tuple)
        for i in range(5)
    ]

    assert len(set(pfade)) == 5, f"{name}: {5 - len(set(pfade))} Beleg(e) verloren"
    for i, pfad in enumerate(pfade):
        assert _read(nas, pfad) == f"beleg {i}".encode()


@pytest.mark.parametrize("name,save,returns_tuple", SAVERS, ids=[s[0] for s in SAVERS])
def test_endung_bleibt_erhalten(nas, name, save, returns_tuple):
    """Der Zaehler haengt vor der Endung, nicht dahinter."""
    save(nas, _file("beleg.pdf", b"erster"))
    zweit = _relpath(save(nas, _file("beleg.pdf", b"zweiter")), returns_tuple)

    assert zweit.endswith(".pdf"), f"{name}: Endung zerstoert -> {zweit}"


@pytest.mark.parametrize("name,save,returns_tuple", SAVERS, ids=[s[0] for s in SAVERS])
def test_rueckgabe_ist_relativ_und_zeigt_auf_die_datei(nas, name, save, returns_tuple):
    """Die DB speichert den relativen Pfad. Er muss aufloesbar bleiben."""
    relativ = _relpath(save(nas, _file("beleg.pdf", b"inhalt")), returns_tuple)

    assert not os.path.isabs(relativ), f"{name}: absoluter Pfad in der DB"
    assert os.path.exists(os.path.join(nas.nas_mount_path, relativ))


def test_unique_path_ohne_kollision_haengt_nichts_an(nas, tmp_path):
    """Ohne Kollision bleibt der Name unveraendert. Bestandspfade brechen nicht."""
    ordner = str(tmp_path / "nas" / "ordner")
    os.makedirs(ordner, exist_ok=True)

    pfad, name = nas._unique_path(ordner, "Rechnung_Heizung_2025", "pdf")

    assert name == "Rechnung_Heizung_2025.pdf"
    assert pfad == os.path.join(ordner, "Rechnung_Heizung_2025.pdf")


def test_general_document_meldet_den_anzeigenamen(nas):
    """save_general_document und save_billing_report geben den Anzeigenamen
    mit zurueck (fuer invoice_documents.filename).

    Seit NK-131 (D-87) liegt die Datei unter einem neutralen Namen; der
    Anzeigename ist der hochgeladene, entschaerft, und darf sich wiederholen
    -- die Pfade kollidieren trotzdem nie.
    """
    erst, name1 = nas.save_general_document(_file("Sammelrechnung.pdf", b"erste"), "Hauptstr 1")
    zweit, name2 = nas.save_general_document(_file("Sammelrechnung.pdf", b"zweite"), "Hauptstr 1")

    assert name1 == name2 == "Sammelrechnung.pdf"
    assert erst != zweit
