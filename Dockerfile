# Produktionsbuild (NK-076, F-58). Mehrarchitektur (amd64, arm64) ueber den
# Index-Digest: dasselbe Abbild baut auf dem PC und auf dem Raspberry Pi bzw.
# der Synology, und ein Bau von morgen nimmt dieselbe Basis wie heute.
# python:3.11-slim (Debian trixie, Python 3.11.16), Stand 2026-09-24.
FROM python:3.11-slim@sha256:da047cb8f9d1d98e5c070f5300ba9f7274e33b8fc0e5be5ed88740aed1b95ba9

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIR=/data \
    PUID=1000 \
    PGID=1000

WORKDIR /app

# Keine apt-Schicht (NK-022). Alle Abhaengigkeiten aus requirements.txt als
# Wheel im nackten python:3.11-slim.
COPY requirements.txt .
# Hinter einem TLS-pruefenden Firmen-Proxy (auch in der CI) kann dessen
# Zertifikat als Build-Secret "ca" mitgegeben werden; ohne Secret aendert
# sich nichts:  docker build --secret id=ca,src=<ca-bundle.crt> .
RUN --mount=type=secret,id=ca,required=false \
    if [ -f /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca; fi; \
    pip install --no-cache-dir -r requirements.txt

# Positivliste ueber .dockerignore: Entwicklung, Doku, Tests und Daten
# bleiben draussen (NK-040, NK-133 folgt).
COPY . .

# Eigener Nutzer ohne Anmeldung (NK-076): die Anwendung laeuft nie als root.
# Der Einstieg startet als root nur, um den Datenordner einem Bind-Mount vom
# Wirt passend zu machen, und wechselt dann per setpriv auf PUID/PGID.
RUN groupadd --system --gid 1000 nebenkosten \
 && useradd --system --uid 1000 --gid nebenkosten --home-dir /app \
        --shell /usr/sbin/nologin nebenkosten \
 && mkdir -p /data \
 && chown nebenkosten:nebenkosten /data \
 && chmod 0755 /app/docker-entrypoint.sh

VOLUME ["/data"]
EXPOSE 6060

# Der Port folgt FLASK_PORT (Vorgabe 6060): Dev- und Abgleich-Stapel binden
# gunicorn auf 6061/6062 und galten sonst als "unhealthy".
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python", "-c", "import os,sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('FLASK_PORT', '6060'), timeout=3).status == 200 else 1)"]

ENTRYPOINT ["/app/docker-entrypoint.sh"]
# E-3 → D-91: ein Prozess mit Threads auf einer SQLite-Datei (WAL).
# Gebunden wird wie beim Healthcheck an FLASK_PORT (Vorgabe 6060); exec hält
# gunicorn als Hauptprozess, damit SIGTERM ankommt.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${FLASK_PORT:-6060} --workers 1 --threads 8 --timeout 120 --access-logfile - app:app"]
