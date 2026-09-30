"""Dateiablage: neutrale Namen, sprechender Export (NK-131, E-5 → D-87).

Seit NK-132 heisst die Klasse ``Ablage`` (Modul ``ablage``); 
``handlers.nas_handler.NASHandler`` bleibt eine Version lang als Alias.

Bis NK-131 legte die Ablage jede Datei unter sprechenden Namen ab:
``<Immobilie>/Wohnungen/<Wohnung>/<Mieter>/Mietvertraege/Mietvertrag_Mueller.pdf``.
Wer den Ordner sah, sah die Mieter, jede Sicherung trug ihre Namen im Index,
und eine DSGVO-Loeschung haette Ordner umbenennen muessen (F-60).

Jetzt liegt jede Datei unter einem Namen ohne jeden Personenbezug:

  <Belegwurzel>/
    <Jahr>/
      <uuid>.<endung>

Das Jahr ist das fachliche Jahr, wo es eines gibt (Ablesedatum, Ende des
Rechnungszeitraums), sonst das Jahr des Hochladens; die Endung kommt aus
dem Inhalt (NK-129). Was eine Datei ist, weiss die Datenbank: die Zeile, die
auf den Pfad zeigt, und bei Sammelbelegen der Anzeigename in
``invoice_documents.filename``. Wer die Belege mit sprechenden Namen braucht
-- fuer den Steuerberater, fuer den Mieter, fuer den Umzug --, nimmt den
Knopf "Belege exportieren" (``belege_export.py``): der baut den alten Baum als
ZIP.

Die fuenf save_*-Methoden behalten ihre Parameter, damit die Aufrufer
unveraendert bleiben; Namen von Immobilie, Wohnung und Mieter fliessen nicht
mehr in den Pfad. In der Datenbank steht immer der **relative** Pfad.

Der vorhandene Bestand wandert beim Start (``ablage_migration.py``).

Faellt die Ablage aus, ist das kein Grund, die Anwendung nicht zu starten:
das Basisverzeichnis wird beim Anlegen des Handlers nur versucht, ein
Fehlschlag landet als Warnung im Protokoll. delete_file() lehnt Pfade mit
'..' oder fuehrendem Schraegstrich ab.
"""

import logging
import os
import re
import uuid
from datetime import date

# Kindlogger von fehler.PROTOKOLLNAME (NK-030): die Zeilen landen in demselben
# Ausgang, den init_protokoll() einhaengt, und tragen trotzdem 'ablage' im Namen,
# sodass im Protokoll steht, wer meckert. Bewusst nicht 'from fehler import
# protokoll' -- der Dateiablage-Handler soll nicht die halbe Webschicht
# nachziehen, nur um eine Warnung schreiben zu koennen.
protokoll = logging.getLogger('nebenkosten.ablage')


class Ablage:
    def __init__(self):
        # Ensure base path exists
        try:
            os.makedirs(self.wurzel, exist_ok=True)
        except Exception:
            # Kein Abbruch: ohne Belegordner laeuft alles, was keine Datei
            # anfasst, weiter. Wer eine hochlaedt, bekommt den Fehler dann an
            # der Stelle, an der er entsteht.
            protokoll.warning('Belegordner nicht anlegbar', exc_info=True)

    @property
    def wurzel(self):
        """Die Belegwurzel ``DATA_DIR/belege`` (NK-132), bei jedem Zugriff
        neu bestimmt -- wer den Datenordner aendert (Tests, Umzug), wird
        ueberall gleich verstanden. ``NAS_MOUNT_PATH`` gilt eine Version lang
        als Alias."""
        from nebenkostenfix import datenordner

        return str(datenordner.belegordner())

    @property
    def nas_mount_path(self):
        """Alter Name fuer ``wurzel`` (bis zur naechsten Version)."""
        return self.wurzel

    def sanitize_name(self, name):
        """Sanitize names for folders and files (replace spaces/special chars with underscores)"""
        # Replace umlauts
        name = name.replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue')
        name = name.replace('Ä', 'Ae').replace('Ö', 'Oe').replace('Ü', 'Ue').replace('ß', 'ss')
        # Replace non-alphanumeric with underscores
        name = re.sub(r'[^a-zA-Z0-9]', '_', name)
        # Remove consecutive underscores
        name = re.sub(r'_+', '_', name)
        return name.strip('_')

    def sanitize_basename(self, filename):
        """Der Namensteil vor der Endung, entschaerft und nie leer.

        sanitize_name() streicht alles, was kein Buchstabe und keine Ziffer
        ist. Bei einem Namen wie "..." oder "###.pdf" bleibt nichts uebrig,
        und aus dem Rest entstuende die versteckte Datei ".pdf".
        """
        roh = (filename or '').rsplit('.', 1)[0] if '.' in (filename or '') else (filename or '')
        return self.sanitize_name(roh) or 'Dokument'

    def sanitize_ext(self, filename, fallback):
        """Die Endung aus einem Uploadnamen, auf das eingedampft, was eine
        Endung sein darf.

        Bis NK-026 ging der Teil hinter dem letzten Punkt roh in den Pfad. Ein
        Name wie "scan.<300 Zeichen>" warf damit einen ungefangenen OSError
        (Errno 36, File name too long) bis in die Route, also 500 statt einer
        Absage. "a.b/c" schob Schraegstriche in den Dateinamen. Beides kommt
        nicht von einem Vermieter, sondern von irgendeinem Client.
        """
        if '.' not in (filename or ''):
            return fallback
        roh = filename.rsplit('.', 1)[-1].lower()
        sauber = re.sub(r'[^a-z0-9]', '', roh)[:16]
        return sauber or fallback

    def endung_nach_inhalt(self, file):
        """Die Endung aus dem Inhalt, nicht aus dem Namen (NK-129, D-88).

        Lehnt alles ausser PDF, JPEG, PNG, WebP und HEIC mit einem
        EingabeFehler ab (400), bevor ein Ordner oder eine Datei entsteht.
        """
        from nebenkostenfix.uploads import pruefe
        return pruefe(file)

    def _unique_path(self, folder_path, base_name, ext):
        """Return a (path, filename) pair that no existing file occupies.

        All five save_* helpers build deterministic names, so two documents for
        the same category and period collide. Without this counter the first one
        is silently overwritten and is gone before any backup exists (NK-018).
        """
        filename = f"{base_name}.{ext}"
        full_path = os.path.join(folder_path, filename)
        counter = 1
        while os.path.exists(full_path):
            filename = f"{base_name}_{counter}.{ext}"
            full_path = os.path.join(folder_path, filename)
            counter += 1
        return full_path, filename

    # --- Ablegen unter neutralem Namen (NK-131) --------------------------

    NEUTRAL = re.compile(r'^\d{4}/[0-9a-f]{32}\.[a-z0-9]{1,16}$')

    def _ablegen(self, file, jahr, ext):
        """Speichert unter ``<Jahr>/<uuid>.<ext>`` und liefert den relativen
        Pfad. Die uuid kollidiert nicht; ein Zaehler wie bis NK-131 (NK-018)
        ist nicht mehr noetig, ueberschrieben wird trotzdem nie."""
        jahr = f'{int(jahr):04d}'
        ordner = os.path.join(self.wurzel, jahr)
        os.makedirs(ordner, exist_ok=True)
        name = f'{uuid.uuid4().hex}.{ext}'
        pfad = os.path.join(ordner, name)
        while os.path.exists(pfad):  # pragma: no cover - 122 Bit Zufall
            name = f'{uuid.uuid4().hex}.{ext}'
            pfad = os.path.join(ordner, name)
        file.save(pfad)
        return f'{jahr}/{name}'

    def anzeigename(self, file, ext):
        """Der hochgeladene Name, entschaerft, mit der Endung nach Inhalt --
        fuer die Anzeige und den sprechenden Export, nie fuer den Pfad."""
        return f'{self.sanitize_basename(file.filename)}.{ext}'

    def save_reading_photo(self, file, category_name, property_name, apartment_name, reading_date):
        """Foto eines Zaehlerstands; Jahr = Ablesedatum."""
        ext = self.endung_nach_inhalt(file)  # vor jedem Ordner (NK-129)
        return self._ablegen(file, reading_date.year, ext)

    def save_invoice_document(self, file, category_name, property_name, start_date, end_date):
        """Rechnung eines Versorgers; Jahr = Ende des Rechnungszeitraums."""
        ext = self.endung_nach_inhalt(file)  # vor jedem Ordner (NK-129)
        return self._ablegen(file, end_date.year, ext)

    def save_general_document(self, file, property_name):
        """Sammelrechnung und alles ohne feste Zuordnung.

        Liefert (relativer Pfad, Anzeigename); der Anzeigename kommt in
        invoice_documents.filename.
        """
        ext = self.endung_nach_inhalt(file)  # vor jedem Ordner (NK-129)
        return self._ablegen(file, date.today().year, ext), self.anzeigename(file, ext)

    def delete_file(self, relative_path):
        """Loescht eine Datei der Ablage per relativem Pfad."""
        if not relative_path: return False
        # security check to prevent path traversal
        if '..' in relative_path or relative_path.startswith('/'):
            return False
            
        full_path = os.path.join(self.wurzel, relative_path)
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
                return True
            except Exception:
                protokoll.warning('Datei nicht loeschbar: %s', full_path,
                                  exc_info=True)
                return False
        return False

    def save_billing_report(self, file, property_name, apartment_name, tenant_name):
        """Erzeugte Abrechnung; liefert (relativer Pfad, Anzeigename)."""
        ext = self.endung_nach_inhalt(file)  # vor jedem Ordner (NK-129)
        return self._ablegen(file, date.today().year, ext), self.anzeigename(file, ext)

    def save_tenant_contract(self, file, property_name, apartment_name, tenant_name):
        """Mietvertrag; der Name des Mieters kommt nicht in den Pfad."""
        ext = self.endung_nach_inhalt(file)  # vor jedem Ordner (NK-129)
        return self._ablegen(file, date.today().year, ext)
