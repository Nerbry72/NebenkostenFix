// Umzugspaket (NK-164): Hochladen in Stücken, Prüfen, Übernehmen.
//
// Geteilt von der Einrichtungsseite (vor der Anmeldung, ohne app.js) und den
// Einstellungen (app.js ruft window.umzugPaket). Hunderte MB Belege passen
// nicht durch MAX_UPLOAD_MB und nicht durch jeden Reverse Proxy: die Datei
// geht in Stücken (Größe sagt der Server), nach einem Abbruch setzt der
// Upload beim Stand des Servers wieder an. In der Windows-App gibt es kein
// Hochladen: der Datei-Dialog der Hülle gibt einen Pfad frei.
(function () {
    'use strict';

    const VERSUCHE = 5;

    function kopf(code, json) {
        const k = {};
        if (json) k['Content-Type'] = 'application/json';
        if (code) k['X-Einmal-Code'] = code;
        return k;
    }

    async function antwortLesen(antwort) {
        let daten = {};
        try {
            daten = await antwort.json();
        } catch (e) {
            daten = {};
        }
        if (!antwort.ok) {
            const fehler = new Error(daten.error || `Der Server antwortet mit ${antwort.status}.`);
            fehler.status = antwort.status;
            // Wie serverFehler() in app.js: dieser Satz ist für Menschen gemacht.
            fehler.vomServer = !!daten.error;
            throw fehler;
        }
        return daten;
    }

    async function postJson(adresse, daten, code) {
        const antwort = await fetch(adresse, {
            method: 'POST', headers: kopf(code, true), body: JSON.stringify(daten || {}),
            credentials: 'same-origin',
        });
        return antwortLesen(antwort);
    }

    function hinweis(text) {
        const fehler = new Error(text);
        fehler.vomServer = true;
        return fehler;
    }

    function warte(ms) {
        return new Promise(fertig => setTimeout(fertig, ms));
    }

    const umzugPaket = {
        desktop() {
            return !!(window.pywebview && window.pywebview.api && window.pywebview.api.paket_waehlen);
        },

        // Lädt eine Datei hoch und gibt die Upload-Kennung zurück.
        async hochladen(datei, optionen) {
            const code = (optionen && optionen.code) || '';
            const fortschritt = (optionen && optionen.fortschritt) || (() => {});
            const start = await postJson('/api/umzug/hochladen',
                {groesse: datei.size, name: datei.name}, code);
            let ab = start.empfangen;
            let fehlversuche = 0;
            while (ab < datei.size) {
                const ende = Math.min(ab + start.stueck, datei.size);
                try {
                    const antwort = await fetch(`/api/umzug/hochladen/${start.id}?ab=${ab}`, {
                        method: 'PUT', credentials: 'same-origin',
                        headers: Object.assign({'Content-Type': 'application/octet-stream'}, kopf(code)),
                        body: datei.slice(ab, ende),
                    });
                    const stand = await antwortLesen(antwort);
                    ab = stand.empfangen;
                    fehlversuche = 0;
                    fortschritt(ab, datei.size);
                } catch (e) {
                    fehlversuche += 1;
                    if (fehlversuche >= VERSUCHE || (e.status && e.status !== 409 && e.status < 500)) {
                        throw e;
                    }
                    await warte(1000 * 2 ** fehlversuche);
                    // Fortsetzen: dort weitermachen, wo der Server steht.
                    const stand = await antwortLesen(await fetch(`/api/umzug/hochladen/${start.id}`, {
                        headers: kopf(code), credentials: 'same-origin',
                    }));
                    ab = stand.empfangen;
                }
            }
            return start.id;
        },

        pruefen(quelle, code) {
            return postJson('/api/umzug/pruefen', Object.assign({code}, quelle), code);
        },

        uebernehmen(quelle, optionen) {
            const o = optionen || {};
            return postJson('/api/umzug/uebernehmen', Object.assign({
                passphrase: o.passphrase || '', bestaetigung: o.bestaetigung || '', code: o.code || '',
            }, quelle), o.code);
        },

        // Windows-App: Paket über den Dialog der Hülle wählen (Pfad wird freigegeben).
        async desktopWaehlen() {
            return await window.pywebview.api.paket_waehlen();
        },

        async desktopSpeichernUnter(dateiname) {
            return await window.pywebview.api.paket_speichern_unter(dateiname);
        },

        // „1 Beleg“, „2 Belege“ -- der Bericht nennt Zahlen, die auch 1 sein können.
        anzahl(n, einzahl, mehrzahl) {
            return `${n} ${n === 1 ? einzahl : mehrzahl}`;
        },

        lesbar(bytes) {
            if (bytes >= 1024 ** 3) return (bytes / 1024 ** 3).toFixed(1).replace('.', ',') + ' GB';
            if (bytes >= 1024 ** 2) return (bytes / 1024 ** 2).toFixed(1).replace('.', ',') + ' MB';
            return Math.max(1, Math.round(bytes / 1024)) + ' KB';
        },
    };
    window.umzugPaket = umzugPaket;

    // --- Einrichtungsseite ------------------------------------------------------

    function einrichtungVerdrahten() {
        const form = document.getElementById('umzug-form');
        if (!form) return;
        const desktop = form.dataset.desktop === '1';
        const datei = document.getElementById('umzug-datei');
        const waehlen = document.getElementById('umzug-auswahl-knopf');
        const gewaehlt = document.getElementById('umzug-auswahl-name');
        const status = document.getElementById('umzug-status');
        const balken = document.getElementById('umzug-fortschritt');
        let pfad = null;

        datei.hidden = desktop;
        waehlen.hidden = !desktop;
        waehlen.addEventListener('click', async () => {
            try {
                pfad = await umzugPaket.desktopWaehlen();
                gewaehlt.textContent = pfad || '';
            } catch (e) {
                status.textContent = 'Der Datei-Dialog ließ sich nicht öffnen.';
            }
        });

        function melden(text, art) {
            status.textContent = text;
            status.className = art || '';
        }

        form.addEventListener('submit', async ereignis => {
            ereignis.preventDefault();
            const code = (document.getElementById('umzug-code') || {}).value || '';
            const passphrase = document.getElementById('umzug-passphrase').value;
            const knopf = form.querySelector('button[type=submit]');
            knopf.disabled = true;
            try {
                let quelle;
                if (desktop) {
                    if (!pfad) throw hinweis('Bitte wählen Sie zuerst das Paket aus.');
                    quelle = {pfad};
                } else {
                    const gewaehlteDatei = datei.files && datei.files[0];
                    if (!gewaehlteDatei) throw hinweis('Bitte wählen Sie zuerst das Paket aus.');
                    balken.hidden = false;
                    const kennung = await umzugPaket.hochladen(gewaehlteDatei, {
                        code,
                        fortschritt(ab, gesamt) {
                            balken.value = ab / gesamt;
                            melden(`Hochgeladen: ${umzugPaket.lesbar(ab)} von ${umzugPaket.lesbar(gesamt)}`);
                        },
                    });
                    quelle = {hochgeladen: kennung};
                }
                melden('Das Paket wird geprüft und übernommen …');
                const bericht = await umzugPaket.uebernehmen(quelle, {code, passphrase});
                melden(`Übernommen: ${umzugPaket.anzahl(bericht.zeilen, 'Datensatz', 'Datensätze')} und ` +
                    `${umzugPaket.anzahl(bericht.belege, 'Beleg', 'Belege')}. ` +
                    'Melden Sie sich jetzt mit Ihrem bisherigen Benutzernamen und Passwort an.', 'ok');
                const weiter = document.getElementById('umzug-weiter');
                weiter.hidden = false;
                weiter.focus();
            } catch (e) {
                // Ein abgerissenes Netz wirft englische Sätze; die helfen niemandem.
                melden(e.vomServer ? e.message : 'Die Übernahme ist fehlgeschlagen. Prüfen Sie die '
                    + 'Verbindung und versuchen Sie es erneut.', 'fehler');
                knopf.disabled = false;
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', einrichtungVerdrahten);
    } else {
        einrichtungVerdrahten();
    }
})();
