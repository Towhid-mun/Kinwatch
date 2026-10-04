#!/bin/sh
# One command to redeploy both services after a code change, instead of
# manually stopping then starting each one. Requires
# scripts/setup_autostart.sh to have been run at least once (the units
# must exist to restart them).
#
# Run via: perch exec sudo sh scripts/restart_security.sh
set -e

systemctl restart security-monitor.service security-web.service
sleep 1
systemctl --no-pager status security-monitor.service security-web.service | grep -E "●|Active"
