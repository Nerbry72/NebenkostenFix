#!/bin/sh
# Einstieg des Containers (NK-076). Laeuft er als root, macht er den
# Datenordner dem Anwendungsnutzer zugaenglich und startet die Anwendung dann
# ohne root-Rechte. Laeuft er schon als anderer Nutzer (compose "user:"),
# startet er sie direkt.
set -eu

DATA_DIR="${DATA_DIR:-/data}"
PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

if [ "$(id -u)" = "0" ]; then
    mkdir -p "$DATA_DIR"
    # Nur wenn etwas darin (z. B. frisch vom Wirt eingehaengt, oder Datenbank
    # und Belege aus einem frueheren root-Container) noch nicht dem
    # Anwendungsnutzer gehoert -- sonst kostet jeder Start ein chown ueber
    # alle Belege. Geprueft wird der Inhalt, nicht nur der Ordner selbst.
    if [ -n "$(find "$DATA_DIR" \( ! -user "$PUID" -o ! -group "$PGID" \) -print -quit)" ]; then
        echo "Datenordner $DATA_DIR gehört nicht ganz Nutzer $PUID:$PGID, passe an ..." >&2
        chown -R "$PUID:$PGID" "$DATA_DIR"
    fi
    if [ "$PUID" = "0" ]; then
        echo "WARNUNG: PUID=0 -- die Anwendung läuft als root." >&2
        exec "$@"
    fi
    exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups "$@"
fi

if [ ! -w "$DATA_DIR" ]; then
    echo "FEHLER: Der Datenordner $DATA_DIR ist für Nutzer $(id -u) nicht beschreibbar." >&2
    echo "Den Ordner auf dem Wirt diesem Nutzer geben (chown) oder PUID/PGID setzen." >&2
    exit 1
fi
exec "$@"
