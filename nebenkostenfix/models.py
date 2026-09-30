from flask_sqlalchemy import SQLAlchemy
from datetime import date, datetime

from nebenkostenfix import zeit
from nebenkostenfix.abrechnungsart import GUELTIG, VORGABE
from nebenkostenfix.betrkv import NUMMERN as BETRKV_NUMMERN
from nebenkostenfix.geld import Einheitspreis, Geld
from nebenkostenfix.haushalt import personen_am
from nebenkostenfix.heizung import (
    ANTEIL_MAX, ANTEIL_MIN, ANTEIL_VORGABE, ABLESUNG, HEIZUNG, VERBUNDEN,
    WW_KALTWASSER_GRAD, ZWISCHENABLESUNG, ABLESUNGSARTEN,
    SCHLUESSEL as HEIZKOSTENARTEN,
    VERSORGT as VERSORGUNGSARTEN,
    WW_WEGE as WARMWASSERWEGE,
)
from nebenkostenfix.nutzung import GUELTIG as NUTZUNGSARTEN
from nebenkostenfix.nutzung import VORGABE as NUTZUNG_VORGABE

from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

class Provider(db.Model):
    __tablename__ = 'providers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    
    invoices = db.relationship('CostInvoice', backref='provider', lazy=True)
    meter_readings = db.relationship('MeterReading', backref='provider', lazy=True)

class Property(db.Model):
    __tablename__ = 'properties'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    is_standalone = db.Column(db.Boolean, default=False, nullable=False)
    # D-114: Tag, an dem das Abrechnungsjahr des Hauses beginnt, als 'MM-TT'.
    # Leer heisst: aus den bisherigen Abrechnungen ableiten, sonst 01.01.
    abrechnungsjahr_beginn = db.Column(db.String(5), nullable=True)

    apartments = db.relationship('Apartment', backref='property', lazy=True, cascade="all, delete-orphan")
    invoices = db.relationship('CostInvoice', backref='property', lazy=True)
    meters = db.relationship('Meter', backref='property', lazy=True)

class Apartment(db.Model):
    __tablename__ = 'apartments'
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    sqm = db.Column(db.Float, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    # Wofuer die Einheit da ist, seit NK-045 (Revision d2f8b16c05a9). Welche
    # Arten es gibt, steht in nutzung.py und nirgends sonst. Das Programm
    # rechnet nach dem Recht fuer Wohngebaeude; ohne dieses Feld konnte es
    # ein Gewerbeobjekt nicht von einem Wohnhaus unterscheiden (R-CO2-04).
    nutzungsart = db.Column(
        db.String(20), nullable=False,
        default=NUTZUNG_VORGABE, server_default=NUTZUNG_VORGABE)
    # Wer seine Waerme selbst erzeugt -- eigene Gastherme, eigener Ofen --
    # nimmt an der Heizungsanlage des Hauses nicht teil. Fuer solche
    # Einheiten duerfen Heizkosten des Gebaeudes nicht umgelegt werden
    # (R-CO2-03, § 6 CO2KostAufG). Vorerst nur ein Datenfall: das Rechnen
    # der CO2-Aufteilung kommt mit dem Heizkostenmodul.
    selbstversorger = db.Column(
        db.Boolean, nullable=False, default=False, server_default='0')
    # Eine vom Vermieter selbst bewohnte Einheit ist nicht leer und hat doch
    # keinen Mieter. Ohne dieses Feld sind beide Faelle nicht zu trennen,
    # und der Leerstandsanteil nach R-NUM-05 waere falsch ausgewiesen.
    eigennutzung = db.Column(
        db.Boolean, nullable=False, default=False, server_default='0')

    tenants = db.relationship('Tenant', backref='apartment', lazy=True, cascade="all, delete-orphan")
    meters = db.relationship('Meter', backref='apartment', lazy=True)

    # Dasselbe Argument wie beim CHECK auf der Abrechnungsart (NK-096): die
    # Eingabepruefung deckt die Oberflaeche ab, nicht die eingespielte
    # Sicherung, den Import oder die Zeile per sqlite3.
    __table_args__ = (
        db.CheckConstraint(
            'nutzungsart IN (%s)' % ', '.join("'%s'" % a for a in sorted(NUTZUNGSARTEN)),
            name='ck_apartments_nutzungsart'),
    )

class Tenant(db.Model):
    __tablename__ = 'tenants'
    id = db.Column(db.Integer, primary_key=True)
    apartment_id = db.Column(db.Integer, db.ForeignKey('apartments.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    move_in_date = db.Column(db.Date, nullable=False)
    move_out_date = db.Column(db.Date, nullable=True)
    last_billed_until = db.Column(db.Date, nullable=True)
    contract_path = db.Column(db.String(500), nullable=True)
    # NK-153 (E-11 → D-89): gesetzt, wenn der Vermieter das Mietverhaeltnis
    # geloescht hat, aber festgesetzte Abrechnungen oder Zahlungen noch einer
    # Aufbewahrungsfrist unterliegen. Bis zu diesem Tag bleibt die Zeile als
    # Anker gesperrt (aus allen Listen ausgeblendet), danach loescht der Start
    # sie ganz.
    gesperrt_bis = db.Column(db.Date, nullable=True)
    
    cost_profiles = db.relationship('TenantCostProfile', backref='tenant', lazy=True, cascade="all, delete-orphan")
    payments = db.relationship('Payment', backref='tenant', lazy=True, cascade="all, delete-orphan")
    haushaltsgroessen = db.relationship(
        'Haushaltsgroesse', backref='tenant', lazy=True,
        cascade="all, delete-orphan", order_by='Haushaltsgroesse.gueltig_ab')

    def personenanzahl_am(self, stichtag: date) -> int:
        """Wie viele Personen an diesem Tag in der Einheit wohnten.

        Genommen wird der juengste Eintrag, der am Stichtag schon galt.
        Gibt es keinen -- ein Mietverhaeltnis aus der Zeit vor NK-045, an
        dem nie etwas gepflegt wurde -- ist die Antwort 1. Das ist das
        bisherige Verhalten: vor NK-045 zaehlte jedes Mietverhaeltnis als
        ein Kopf, und ein Update darf die Abrechnung nicht stillschweigend
        verschieben.

        Gerechnet wird das in ``haushalt.py`` (NK-046) -- derselbe Ort, aus
        dem auch der Rechenkern seine Personentage nimmt. Zwei Treppen
        nebeneinander waeren zwei Wahrheiten.
        """
        return personen_am(
            [(h.gueltig_ab, h.personenanzahl) for h in self.haushaltsgroessen], stichtag
        )


class Haushaltsgroesse(db.Model):
    """Wie viele Personen ab wann zu einem Mietverhaeltnis gehoeren (NK-045).

    Eine Kopfzahl am Mietverhaeltnis genuegt nicht. Zieht im Juli ein Kind
    aus, muessen die nach Personen umgelegten Kosten fuer das halbe Jahr mit
    drei und fuer das halbe mit zwei Personen gerechnet werden -- nach
    **Personentagen**, nicht nach einer Momentaufnahme (R-NUM-04). Dafuer
    braucht es die Aenderungen mit Datum, nicht nur den letzten Stand.

    Ein Eintrag gilt ab ``gueltig_ab`` bis zum naechsten Eintrag oder bis zum
    Ende des Mietverhaeltnisses. Das Rechnen daraus ist NK-046; hier stehen
    nur die Daten.
    """

    __tablename__ = 'haushaltsgroessen'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    gueltig_ab = db.Column(db.Date, nullable=False)
    personenanzahl = db.Column(db.Integer, nullable=False)

    # Zwei Eintraege auf denselben Tag waeren zwei Wahrheiten -- welcher
    # gilt, koennte niemand sagen. Und null Personen ist kein Haushalt: wer
    # nicht mehr da ist, hat ein Auszugsdatum, keine Null.
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'gueltig_ab',
                            name='uq_haushaltsgroessen_tenant_gueltig_ab'),
        db.CheckConstraint('personenanzahl >= 1',
                           name='ck_haushaltsgroessen_personenanzahl'),
    )

class TenantCostProfile(db.Model):
    __tablename__ = 'tenant_cost_profiles'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('cost_categories.id'), nullable=False)
    # Welche Arten es gibt, steht in abrechnungsart.py und nirgends sonst
    # (NK-096). Die Bedingung unten wird daraus erzeugt, damit eine sechste Art
    # nicht an zwei Stellen nachgetragen werden muss.
    billing_type = db.Column(db.String(50), nullable=False, default=VORGABE)

    # CHECK seit NK-096 (Revision b4e7f2a91c65). Geprueft wird schon an der
    # Eingabe (validation.kostenprofile) und im Rechenkern -- aber eine Regel
    # in der Datenbank gilt auch fuer den Weg, an den niemand gedacht hat:
    # eine eingespielte Sicherung, ein Import, eine Zeile per sqlite3.
    __table_args__ = (
        db.CheckConstraint(
            'billing_type IN (%s)' % ', '.join("'%s'" % a for a in sorted(GUELTIG)),
            name='ck_tenant_cost_profiles_billing_type'),
    )

class CostCategory(db.Model):
    __tablename__ = 'cost_categories'
    id = db.Column(db.Integer, primary_key=True)
    # UNIQUE seit NK-095 (Revision 9c1f4a2b7d33). Zwei gleichnamige Kostenarten
    # sieht der Vermieter doppelt in der Auswahlliste und kann nicht erkennen,
    # welche die Rechnungen traegt.
    name = db.Column(db.String(100), nullable=False, unique=True)
    allocation_method = db.Column(db.String(50), nullable=False) # e.g. 'PER_SQM', 'PER_ACTIVE_HEAD', 'METER_READING'
    requires_meter = db.Column(db.Boolean, default=False, nullable=False)
    # Die Nummer aus § 2 BetrKV, seit NK-044 (Revision c9a5d3f81e47). Sie ist
    # Pflicht, weil die Abrechnung die Kostenart benennen muss (R-DOC-01) und
    # weil die Aufzaehlung des Gesetzes abschliessend ist (R-KAT-01): eine
    # Kostenart ohne Nummer ist eine Kostenart, von der niemand sagen kann,
    # ob sie umgelegt werden darf. Der eine Ort ist betrkv.py.
    betrkv_nr = db.Column(db.Integer, nullable=False)

    invoices = db.relationship('CostInvoice', backref='category', lazy=True)
    meters = db.relationship('Meter', backref='category', lazy=True)

    # Dasselbe Argument wie beim CHECK auf der Abrechnungsart (NK-096): die
    # Eingabepruefung deckt die Oberflaeche ab, nicht die eingespielte
    # Sicherung, den Import oder die Zeile per sqlite3.
    __table_args__ = (
        db.CheckConstraint(
            'betrkv_nr BETWEEN %d AND %d' % (min(BETRKV_NUMMERN), max(BETRKV_NUMMERN)),
            name='ck_cost_categories_betrkv_nr'),
    )

class Heizungsanlage(db.Model):
    """Die zentrale Heizungsanlage eines Gebaeudes, seit NK-048.

    Heizkosten sind kein einzelner Betrag, sondern die Summe der Posten des
    § 7 Abs. 2 HeizkostenV (R-HK-02). Die Masse, die nach § 7 Abs. 1 zu 50 bis
    70 vom Hundert nach Verbrauch verteilt wird, ist diese Summe -- nicht die
    einzelne Rechnung. Ohne eine Anlage als eigene Sache gibt es keinen Ort,
    an dem sie gebildet werden koennte: welche Arten es gibt und in welchem
    Rahmen der Anteil liegen darf, steht in heizung.py und nirgends sonst.

    Ein Gebaeude kann zwei Anlagen haben, und eine Anlage versorgt die
    Heizung, das Warmwasser oder beides -- das sind die Nummern 4, 5 und 6
    des § 2 BetrKV. Verteilt wird mit alldem erst ab NK-049.

    Versorgt sie beides, traegt sie seit NK-050 ausserdem die Angaben, mit
    denen § 9 HeizkostenV die eine Rechnung in zwei Kostenarten teilt: den
    gewaehlten Weg zur Waermemenge des Warmwassers, seine Eingangsgroessen
    und den Gesamtverbrauch der Anlage als Nenner.
    """

    __tablename__ = 'heizungsanlagen'
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(
        db.Integer, db.ForeignKey('properties.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    # Was sie versorgt. Bei 'verbunden' wird vor dem Verteilen das Warmwasser
    # abgetrennt (§ 9 HeizkostenV, R-HK-03, seit NK-050) -- die Felder dafuer
    # stehen weiter unten.
    versorgt = db.Column(
        db.String(20), nullable=False,
        default=HEIZUNG, server_default=HEIZUNG)
    # Der Anteil, der nach erfasstem Verbrauch verteilt wird (§ 7 Abs. 1
    # Satz 1). Der Rest geht nach Flaeche. Pro Anlage, nicht pro Kostenart
    # und nicht global: das Gesetz knuepft an die Anlage und ihr Gebaeude an.
    verbrauchsanteil_prozent = db.Column(
        db.Integer, nullable=False,
        default=ANTEIL_VORGABE, server_default=str(ANTEIL_VORGABE))
    # Der Sonderfall des § 7 Abs. 1 Satz 2: Gebaeude ohne das
    # Anforderungsniveau der Waermeschutzverordnung 1994, Oel- oder
    # Gasheizung, ueberwiegend gedaemmte Leitungen. Liegen alle drei
    # zugleich vor, *sind* 70 vom Hundert nach Verbrauch zu verteilen -- der
    # Satz ist zwingend formuliert, nicht als Wahlrecht. Der CHECK darunter
    # haelt das fest.
    sonderfall_70 = db.Column(
        db.Boolean, nullable=False, default=False, server_default='0')

    # --- Die Trennung der verbundenen Anlage (§ 9 HeizkostenV, NK-050) -----
    #
    # Nur fuer 'verbunden' von Bedeutung: eine Anlage, die allein die Heizung
    # oder allein das Warmwasser versorgt, hat nichts zu trennen. Alle Felder
    # sind deshalb nullable, und ein CHECK haelt fest, dass der Weg ohne eine
    # verbundene Anlage nicht gesetzt sein darf.
    #
    # **Die Mengen gelten fuer den laufenden Abrechnungszeitraum** und tragen
    # keine Historie (F-35). Der Verbrauchsanteil daneben ist ein Stammdatum,
    # das jahrelang steht; diese Zahlen sind es nicht -- sie muessen zu jeder
    # Abrechnung neu eingetragen werden. Eine eigene Tabelle mit Zeitraum
    # waere richtiger und ist als Befund eingestellt.

    # Welcher der drei Wege des § 9 Abs. 2 genommen wurde. Er steht in der
    # Abrechnung (R-HK-03), damit der Mieter weiss, ob gemessen oder
    # geschaetzt wurde.
    warmwasser_weg = db.Column(db.String(20), nullable=True)
    # Weg 'zaehler': die am Warmwasserbereiter gemessene Waermemenge in kWh.
    warmwasser_kwh = db.Column(db.Numeric(12, 3), nullable=True)
    # Weg 'formel': das gemessene Warmwasservolumen V in m3 und die
    # Warmwassertemperatur tw in Grad Celsius.
    warmwasser_volumen_m3 = db.Column(db.Numeric(12, 3), nullable=True)
    warmwasser_temperatur_c = db.Column(db.Numeric(5, 1), nullable=True)
    # Der Nenner: was die Anlage im Zeitraum insgesamt verbraucht hat --
    # Kilowattstunden von der Gasrechnung, Liter vom Lieferschein, Kilogramm
    # von der Pelletsrechnung.
    brennstoff_menge = db.Column(db.Numeric(14, 3), nullable=True)
    # Der Heizwert Hi in kWh je Einheit des Brennstoffs. Steht die Menge
    # ohnehin in Kilowattstunden, bleibt er leer: der Heizwert kuerzt sich
    # dann aus dem Bruch heraus.
    heizwert_kwh = db.Column(db.Numeric(8, 3), nullable=True)

    invoices = db.relationship('CostInvoice', backref='heizungsanlage', lazy=True)

    __table_args__ = (
        db.CheckConstraint(
            'versorgt IN (%s)' % ', '.join(
                "'%s'" % a for a in sorted(VERSORGUNGSARTEN)),
            name='ck_heizungsanlagen_versorgt'),
        db.CheckConstraint(
            'verbrauchsanteil_prozent BETWEEN %d AND %d' % (
                ANTEIL_MIN, ANTEIL_MAX),
            name='ck_heizungsanlagen_verbrauchsanteil'),
        db.CheckConstraint(
            'NOT sonderfall_70 OR verbrauchsanteil_prozent = %d' % ANTEIL_MAX,
            name='ck_heizungsanlagen_sonderfall'),
        db.CheckConstraint(
            'warmwasser_weg IS NULL OR warmwasser_weg IN (%s)' % ', '.join(
                "'%s'" % w for w in WARMWASSERWEGE),
            name='ck_heizungsanlagen_ww_weg'),
        # Zu trennen gibt es nur bei einer verbundenen Anlage etwas. Ein Weg
        # an einer reinen Heizung waere eine Angabe, die nie zur Anwendung
        # kaeme -- und beim naechsten Umstellen auf 'verbunden' stillschweigend
        # doch.
        db.CheckConstraint(
            "warmwasser_weg IS NULL OR versorgt = '%s'" % VERBUNDEN,
            name='ck_heizungsanlagen_ww_nur_verbunden'),
        # Keine negativen Mengen und keine Warmwassertemperatur unterhalb der
        # angenommenen Kaltwassertemperatur: die Formel des § 9 Abs. 2 Satz 4
        # gaebe dann eine negative Waermemenge her.
        db.CheckConstraint(
            '(warmwasser_kwh IS NULL OR warmwasser_kwh > 0) AND '
            '(warmwasser_volumen_m3 IS NULL OR warmwasser_volumen_m3 > 0) AND '
            '(warmwasser_temperatur_c IS NULL OR warmwasser_temperatur_c > %d) AND '
            '(brennstoff_menge IS NULL OR brennstoff_menge > 0) AND '
            '(heizwert_kwh IS NULL OR heizwert_kwh > 0)' % WW_KALTWASSER_GRAD,
            name='ck_heizungsanlagen_ww_mengen'),
    )


class CostInvoice(db.Model):
    __tablename__ = 'cost_invoices'
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('cost_categories.id'), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False)
    apartment_id = db.Column(db.Integer, db.ForeignKey('apartments.id'), nullable=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    # Geld ist Decimal, nicht Float (R-NUM-01, NK-036). Siehe geld.py.
    amount = db.Column(Geld, nullable=False)
    invoice_number = db.Column(db.String(100), nullable=True)
    description = db.Column(db.String(255), nullable=True)
    provider_id = db.Column(db.Integer, db.ForeignKey('providers.id'), nullable=True) # Will be made non-nullable later
    document_path = db.Column(db.String(255), nullable=True) # Legacy for standalone files
    
    invoice_document_id = db.Column(db.Integer, db.ForeignKey('invoice_documents.id'), nullable=True)
    document_pages = db.Column(db.String(50), nullable=True)

    # Das Datum des Belegs, wie der Beleg es ausweist (NK-058, Wanderung
    # d4e6f8a90b12). Der Rechnungszeitraum darueber (start_date/end_date)
    # ist etwas anderes: eine Rechnung fuer Januar bis Maerz kann im April
    # ausgestellt sein. Nullable, weil der Altbestand kein Datum traegt --
    # aus einem NULL wird nichts geraten; das PDF schweigt, wo es fehlt.
    rechnungsdatum = db.Column(db.Date, nullable=True)

    # Gehoert diese Rechnung zu den Kosten des Betriebs einer Heizungsanlage?
    # Seit NK-048 (Revision e5b2c74f9a16). Die Zuordnung haengt am Vorgang,
    # nicht an der Kostenart (D-44): dieselbe Kostenart "Heizung" traegt im
    # Jahr die Brennstoffrechnung, die Wartungsrechnung und die des
    # Ablesedienstes. Wer die Zuordnung an die Kostenart haengt, zwingt den
    # Vermieter, acht Kostenarten zu pflegen, die er nie trennen wollte.
    heizungsanlage_id = db.Column(
        db.Integer, db.ForeignKey('heizungsanlagen.id'), nullable=True)
    # Welcher Posten des § 7 Abs. 2 HeizkostenV die Rechnung ist. Der eine
    # Ort ist heizung.py.
    heizkostenart = db.Column(db.String(30), nullable=True)

    # Die CO2-Angaben der Lieferantenrechnung (NK-053, Revision
    # b8e2f41a90c3): die Emissionsmenge in Kilogramm und die CO2-Kosten in
    # Euro, wie der Beleg sie ausweist. NULL heisst "keine Angabe" -- der
    # Altbestand bleibt unberuehrt (Derselbe Grundsatz wie bei der
    # Heizkostenart), und ohne beide Zahlen kann das Gebaeude nicht
    # eingestuft werden (R-CO2-01), was die Abrechnung als blockierenden
    # Befund meldet statt zu raten.
    co2_kosten = db.Column(db.Numeric(12, 2), nullable=True)
    co2_emission_kg = db.Column(db.Numeric(12, 2), nullable=True)

    # Die Preise je Tarif einer Dualtarifrechnung (NK-055). Ein Zaehler mit
    # Hoch- und Niedertarif liefert zwei Mengen, und der Versorger stellt
    # ihnen zwei Preise -- HT teurer, NT billiger. Wer beide einfach addiert
    # und einen Mischpreis daraus zieht, laesst den NT-Kunden den HT-Anteil
    # mitfinanzieren. NULL heisst: Einheitstarif oder keine Angabe -- der
    # Altbestand bleibt unberuehrt, der Rechenkern faellt auf einen Preis
    # zurueck. Beides oder keines: ein Preis ohne seinen Partner wuerde eine
    # Aufteilung behaupten, die der Beleg nicht hergibt.
    preis_ht = db.Column(Einheitspreis, nullable=True)
    preis_nt = db.Column(Einheitspreis, nullable=True)

    __table_args__ = (
        db.CheckConstraint(
            'heizkostenart IS NULL OR heizkostenart IN (%s)' % ', '.join(
                "'%s'" % a for a in sorted(HEIZKOSTENARTEN)),
            name='ck_cost_invoices_heizkostenart'),
        # Beides oder keines. Eine Rechnung an einer Anlage ohne Posten
        # laesst sich nicht ausweisen (R-DOC-01), und ein Posten ohne Anlage
        # gehoert zu keiner Masse, die verteilt wuerde -- er verschwaende.
        db.CheckConstraint(
            '(heizungsanlage_id IS NULL) = (heizkostenart IS NULL)',
            name='ck_cost_invoices_heizung_vollstaendig'),
        # Keine negativen CO2-Angaben. Emissionen und Kosten sind Mengen,
        # keine Salden; eine negative Zahl waere ein Vorzeichenfehler beim
        # Erfassen, den die Datenbank frueher fangt als der Rechenkern.
        db.CheckConstraint(
            '(co2_kosten IS NULL OR co2_kosten >= 0) AND '
            '(co2_emission_kg IS NULL OR co2_emission_kg >= 0)',
            name='ck_cost_invoices_co2_nichtnegativ'),
        # CO2-Angaben nur an Rechnungen mit Heizkostenart. Nur der
        # Brennstoff emittiert -- eine Rechnung ohne Posten traegt keine
        # Masse, die eine Emission erklaren koennte.
        db.CheckConstraint(
            '(co2_kosten IS NULL AND co2_emission_kg IS NULL) '
            'OR heizkostenart IS NOT NULL',
            name='ck_cost_invoices_co2_nur_heizung'),
        # Die Tarifpreise gehoeren zusammen (beides oder keines) und sind
        # Mengenpreise, keine Salden -- ein negativer Preis waere ein
        # Vorzeichenfehler beim Erfassen (dieselbe Regel wie bei den
        # CO2-Angaben).
        db.CheckConstraint(
            '(preis_ht IS NULL) = (preis_nt IS NULL)',
            name='ck_cost_invoices_dualtarif_vollstaendig'),
        db.CheckConstraint(
            '(preis_ht IS NULL OR preis_ht >= 0) AND '
            '(preis_nt IS NULL OR preis_nt >= 0)',
            name='ck_cost_invoices_dualtarif_nichtnegativ'),
    )

class InvoiceDocument(db.Model):
    __tablename__ = 'invoice_documents'
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    document_path = db.Column(db.String(500), nullable=False)
    upload_date = db.Column(db.Date, nullable=False, default=date.today)
    description = db.Column(db.String(255), nullable=True)
    is_collective = db.Column(db.Boolean, default=True, server_default='true', nullable=False)
    
    invoices = db.relationship('CostInvoice', backref='document', lazy=True)
    property = db.relationship('Property')

class Meter(db.Model):
    __tablename__ = 'meters'
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('cost_categories.id'), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False)
    apartment_id = db.Column(db.Integer, db.ForeignKey('apartments.id'), nullable=True) # Null if main meter
    is_main_meter = db.Column(db.Boolean, default=False, nullable=False)
    meter_number = db.Column(db.String(100), nullable=False)
    has_dual_tariff = db.Column(db.Boolean, default=False, nullable=False)
    is_official = db.Column(db.Boolean, default=False, nullable=False)
    # Fuer welche Heizungsanlage dieser Zaehler die Waerme erfasst (NK-049,
    # D-45). NULL heisst: er gehoert zu keiner -- der Regelfall fuer Strom,
    # Wasser und alles andere.
    #
    # Die Zuordnung steht hier und wird nicht aus der Kostenart erraten. Ein
    # Haus kann zwei Anlagen haben, Vorderhaus und Hinterhaus, und beide
    # buchen ihren Brennstoff auf dieselbe Kostenart "Heizung"; ueber die
    # Kostenart waeren ihre Zaehler nicht zu trennen. Dieselbe Art zu raten
    # hat das Projekt bei F-32 schon einmal als Befund erhoben.
    heizungsanlage_id = db.Column(
        db.Integer, db.ForeignKey('heizungsanlagen.id'), nullable=True)

    # NK-125: fuer die Zaehlerliste (Name der Anlage, die der Zaehler misst).
    heizungsanlage = db.relationship('Heizungsanlage', foreign_keys=[heizungsanlage_id])

    readings = db.relationship('MeterReading', backref='meter', lazy=True, cascade="all, delete-orphan")

class MeterReading(db.Model):
    __tablename__ = 'meter_readings'
    id = db.Column(db.Integer, primary_key=True)
    meter_id = db.Column(db.Integer, db.ForeignKey('meters.id'), nullable=False)
    reading_date = db.Column(db.Date, nullable=False)
    value = db.Column(db.Float, nullable=False) # Used for single tariff or HT
    value_nt = db.Column(db.Float, nullable=True) # Used for NT if dual tariff
    is_official_invoice = db.Column(db.Boolean, default=False, nullable=False) # True if reading is from an official invoice
    provider_id = db.Column(db.Integer, db.ForeignKey('providers.id'), nullable=True) # Set if is_official_invoice
    document_path = db.Column(db.String(255), nullable=True)
    # Die Art der Ablesung (NK-051, R-HK-04). Vorgabe ist die gewoehnliche
    # Ablesung; nur der Stand zum Datum eines Nutzerwechsels ist eine
    # Zwischenablesung -- der einzige Messwert, der die Grenze zwischen zwei
    # Mietverhaeltnissen misst (§ 9b HeizkostenV). Der Vorgabewert traegt der
    # Altbestand, der keine Art kennt.
    ablesungsart = db.Column(db.String(20), nullable=False,
                             default=ABLESUNG, server_default=ABLESUNG)

    __table_args__ = (
        # Dasselbe Argument wie beim CHECK auf der Abrechnungsart (NK-096):
        # die Eingabepruefung deckt die Oberflaeche ab, nicht die
        # eingespielte Sicherung, den Import oder die Zeile per sqlite3.
        db.CheckConstraint(
            'ablesungsart IN (%s)' % ', '.join(
                "'%s'" % a for a in ABLESUNGSARTEN),
            name='ck_meter_readings_ablesungsart'),
    )

class TenantBillingReport(db.Model):
    __tablename__ = 'tenant_billing_reports'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.Date, nullable=False, default=date.today)
    # Fristen des § 556 Abs. 3 BGB (R-FRIST-02, NK-054). frist_ende ist der
    # letzte gültige Tag der Abrechnungsfrist (AZ-Ende + 12 Monate) und wird
    # bei der Erzeugung gesetzt; NULL gibt es seit der Wanderung nicht mehr.
    # zugestellt_am ist die ehrliche Korrektur: maßgeblich ist der Zugang
    # beim Mieter, nicht das Erstellungsdatum -- die Software kann nur das
    # Erstellungsdatum kennen, das Zustelldatum sagt der Vermieter.
    frist_ende = db.Column(db.Date, nullable=False)
    zugestellt_am = db.Column(db.Date, nullable=True)
    document_path = db.Column(db.String(500), nullable=True)           # Simple PDF
    document_path_detailed = db.Column(db.String(500), nullable=True)  # Detailed PDF

    tenant = db.relationship('Tenant', backref=db.backref('billing_reports', lazy=True, cascade="all, delete-orphan"))

    @property
    def aktuelle_version(self):
        """Die gueltige Version der Abrechnung (R-DOC-02, NK-061).

        Die hoechste Nummer ist die, die zaehlt; aeltere bleiben als
        Geschichte stehen und werden von keiner Route mehr ausgeliefert.
        Abrechnungen aus dem Altbestand (vor NK-061) tragen keine Version.
        """
        if not self.versionen:
            return None
        return self.versionen[-1]


class BillingReportVersion(db.Model):
    """Ein unveränderlicher Schnappschuss einer finalisierten Abrechnung.

    Die erste Version entsteht mit der Festsetzung (nummer 1), jede Korrektur
    legt die nächste an und verweist mit ``ersetzt_version_id`` auf die
    ersetzte (R-DOC-02). Eingangsdaten und Ergebnis liegen als JSON-Schnappschuss
    bei -- Geld als Zeichenkette, Datum als ISO-Zeichen (siehe
    ``abrechnung_version.json_sicher``). Versionen werden nur geschrieben,
    nie geändert; keine Route updated sie.
    """
    __tablename__ = 'billing_report_versions'
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('tenant_billing_reports.id'), nullable=False)
    # Die Nummer innerhalb der Abrechnung: 1 = die Festsetzung, jede
    # Korrektur zaehlt weiter. Die Paarung ist einzigartig.
    nummer = db.Column(db.Integer, nullable=False)
    eingangsdaten = db.Column(db.JSON, nullable=False)
    ergebnis = db.Column(db.JSON, nullable=False)
    # Der Stand, mit dem gerechnet und gedruckt wurde (R-DOC-02). Beide
    # Konstanten leben in abrechnung_version.py.
    software_version = db.Column(db.String(50), nullable=False)
    regel_version = db.Column(db.String(50), nullable=False)
    erstellt_am = db.Column(db.Date, nullable=False, default=date.today)
    # Der Verweis auf die ersetzte Version; bei nummer 1 leer.
    ersetzt_version_id = db.Column(db.Integer, db.ForeignKey('billing_report_versions.id'), nullable=True)

    report = db.relationship('TenantBillingReport', backref=db.backref(
        'versionen', lazy=True, cascade="all, delete-orphan",
        order_by='BillingReportVersion.nummer'))

    __table_args__ = (
        db.UniqueConstraint('report_id', 'nummer', name='uq_version_pro_abrechnung'),
    )


class AnschreibenVorlage(db.Model):
    """Die editierbare Vorlage des Anschreibens, je Objekt (NK-064).

    Das Anschreiben ist die Stimme des Vermieters, nicht die der
    Software: der Text steht je Objekt in der Tabelle, ohne eigenen
    Eintrag gilt der Vorgabetext aus ``anschreiben.py``. Die
    Platzhalter ({mieter_name}, {saldo_betrag}, ...) füllt die
    Renderfunktion aus dem Ergebnis der Abrechnung (``anschreiben.text_fuer``).
    """
    __tablename__ = 'anschreiben_vorlagen'
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False, unique=True)
    text = db.Column(db.Text, nullable=False)
    aktualisiert_am = db.Column(db.Date, nullable=False, default=date.today)

    property = db.relationship('Property')


class Vermieterdaten(db.Model):
    """Der Ausweis des Vermieters, einmal je Instanz (NK-124).

    Wofuer: das Deckblatt spricht für den Vermieter, und der GiroCode
    braucht Empfänger und IBAN (R-NUM-05). Bis NK-124 kamen beide aus
    den Umgebungsvariablen VERMIETER_NAME/VERMIETER_IBAN — ohne
    Terminal nicht zu setzen, und wenn sie fehlten, verschwand der
    GiroCode still vom Blatt.

    Die Umgebungsvariablen bleiben Rückfall (Bestand vor NK-124, D-81):
    was hier steht, gewinnt; was hier fehlt, kommt aus der Umgebung;
    beides leer heißt weiter "kein GiroCode", aber jetzt sichtbar —
    die Route meldet girocode_bereit, die Oberfläche zeigt es an.
    """
    __tablename__ = 'vermieterdaten'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=True)
    iban = db.Column(db.String(34), nullable=True)
    aktualisiert_am = db.Column(db.Date)

    @classmethod
    def einziger(cls):
        """Die eine Zeile der Tabelle, oder None, wenn noch nichts steht."""
        return cls.query.first()


class BillingReportCategory(db.Model):
    __tablename__ = 'billing_report_categories'
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('tenant_billing_reports.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('cost_categories.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(50), nullable=False, default='completed')
    
    report = db.relationship('TenantBillingReport', backref=db.backref('categories', lazy=True, cascade="all, delete-orphan"))
    category = db.relationship('CostCategory')

class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    billing_report_id = db.Column(db.Integer, db.ForeignKey('tenant_billing_reports.id'), nullable=True)
    # Geld ist Decimal, nicht Float (R-NUM-01, NK-036). Siehe geld.py.
    amount = db.Column(Geld, nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    type = db.Column(db.String(50), nullable=False) # 'Miete', 'Nebenkostenvorauszahlung', 'Kaution', 'Nebenkostenzahlung'
    
    billing_report = db.relationship('TenantBillingReport', backref='payments', lazy=True)

class User(db.Model):
    """Anmeldekonto (NK-019).

    Bewusst kein einzelnes Passwort in der .env, sondern
    mehrere Konten, Hash in der Datenbank. Das Klartextpasswort steht nirgends
    im Repo und nirgends in der Umgebung, es geht nur durch das CLI hinein.
    """
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False,
                           default=zeit.jetzt_utc)
    last_login_at = db.Column(db.DateTime, nullable=True)

    def set_password(self, password):
        # scrypt ist der Standard von werkzeug 3.1. Kein zusaetzliches Paket.
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
