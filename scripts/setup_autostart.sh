#!/bin/sh
# Installs systemd units for the monitor and web panel, so both start
# automatically on boot (including after the admin panel's "Reboot
# system" control) - see security/features.py's AUTO_START_ON_BOOT,
# which this script reads to decide whether to enable them or install
# them disabled.
#
# Run via: perch exec sudo sh scripts/setup_autostart.sh
#
# Once enabled, the monitor holds the camera continuously - Camview and
# Capture will fail to open it until you temporarily stop the monitor:
#   sudo systemctl stop security-monitor
#   ...use Camview/Capture...
#   sudo systemctl start security-monitor
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SECURITY_DIR="$PROJECT_DIR/security"
RUN_USER="${SUDO_USER:-$(whoami)}"

AUTOSTART=$(cd "$SECURITY_DIR" && "$SECURITY_DIR/.venv/bin/python" -c "import features; print('yes' if features.AUTO_START_ON_BOOT else 'no')")

write_unit() {
    name="$1"
    exec_cmd="$2"
    description="$3"
    cat > "/etc/systemd/system/$name" <<EOF
[Unit]
Description=$description
After=network.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$SECURITY_DIR
ExecStart=$exec_cmd
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
}

write_unit security-monitor.service \
    "$SECURITY_DIR/.venv/bin/python $SECURITY_DIR/monitor.py" \
    "Home security camera monitor (face detection/recognition)"

write_unit security-web.service \
    "$SECURITY_DIR/.venv/bin/python $SECURITY_DIR/app.py" \
    "Home security admin web panel"

systemctl daemon-reload

if [ "$AUTOSTART" = "yes" ]; then
    systemctl enable --now security-monitor.service security-web.service
    echo "installed and enabled - both start automatically on boot, and are running now"
else
    systemctl disable security-monitor.service security-web.service 2>/dev/null || true
    echo "installed but NOT enabled (features.AUTO_START_ON_BOOT is False in security/features.py)"
    echo "start manually with: sudo systemctl start security-monitor security-web"
fi
