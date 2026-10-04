#!/bin/sh
# Continuous camera monitoring loop - foreground, needs the camera device(s)
# free (not in use by capture_snapshot.sh or CamView/Capture).
# Run via: perch run --tty sh scripts/run_security_monitor.sh
# (--tty just to see live log output nicely in your terminal; monitor.py
# itself doesn't read stdin, so plain `perch run` would also work)
#
# Self-cleaning: stops any previous instance first (the systemd service
# if that's what's running, or a leftover manually-run one via its PID
# file) - you never need to manually hunt down and kill a stray process
# before starting a fresh one.
set -e
cd "$(dirname "$0")/../security"

if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet security-monitor.service 2>/dev/null; then
    echo "security-monitor.service (systemd) is running - stopping it first"
    sudo systemctl stop security-monitor.service
fi

PIDFILE=".monitor.pid"
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "stopping previous manually-run instance (pid $(cat "$PIDFILE"))"
    kill "$(cat "$PIDFILE")" 2>/dev/null || true
    sleep 1
fi

echo $$ > "$PIDFILE"
exec .venv/bin/python monitor.py
