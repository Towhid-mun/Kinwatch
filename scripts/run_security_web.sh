#!/bin/sh
# Admin web panel - not interactive, no --tty needed:
# Run via: perch exec sh scripts/run_security_web.sh
# Then browse to http://<pi-address>:8080 from the Mac.
#
# Self-cleaning: stops any previous instance first (the systemd service
# if that's what's running, or a leftover manually-run one via its PID
# file) - you never need to manually hunt down and kill a stray process
# before starting a fresh one.
set -e
cd "$(dirname "$0")/../security"

if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet security-web.service 2>/dev/null; then
    echo "security-web.service (systemd) is running - stopping it first"
    sudo systemctl stop security-web.service
fi

PIDFILE=".web.pid"
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "stopping previous manually-run instance (pid $(cat "$PIDFILE"))"
    kill "$(cat "$PIDFILE")" 2>/dev/null || true
    sleep 1
fi

echo $$ > "$PIDFILE"
exec .venv/bin/python app.py
