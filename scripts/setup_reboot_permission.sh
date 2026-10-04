#!/bin/sh
# Grants the admin-panel's user passwordless sudo for exactly the
# systemctl commands the web panel needs to trigger itself - nothing
# broader:
#   - `systemctl reboot` - the System page's "Reboot system" control
#   - `systemctl stop/start security-monitor.service` - the CamView/
#     Capture pages' "Stop monitor & view cameras" / "Resume monitoring"
#     controls (security/app.py's /camera/pause-monitor,
#     /camera/resume-monitor), so freeing the camera to view it live
#     doesn't require SSHing in every time.
# All run with `sudo -n`, which fails immediately rather than hanging if
# this rule isn't installed, instead of prompting for a password that
# will never come on a non-interactive web request.
#
# Run via: perch exec sudo sh scripts/setup_reboot_permission.sh
set -e

SYSTEMCTL_BIN="$(command -v systemctl)"
RUN_USER="${SUDO_USER:-$(whoami)}"
RULE_FILE="/etc/sudoers.d/security-reboot"

{
    echo "$RUN_USER ALL=(root) NOPASSWD: $SYSTEMCTL_BIN reboot"
    echo "$RUN_USER ALL=(root) NOPASSWD: $SYSTEMCTL_BIN stop security-monitor.service"
    echo "$RUN_USER ALL=(root) NOPASSWD: $SYSTEMCTL_BIN start security-monitor.service"
} > "$RULE_FILE"
chmod 440 "$RULE_FILE"
visudo -c -f "$RULE_FILE"

echo "done - $RUN_USER can now run 'sudo $SYSTEMCTL_BIN reboot' and 'sudo $SYSTEMCTL_BIN stop/start security-monitor.service' without a password, and nothing else new"
