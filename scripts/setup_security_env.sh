#!/bin/sh
# One-time setup for the security/ module: creates its Python venv and
# installs dependencies. .venv/ is a perch built-in exclude (never synced),
# so this must be re-run on the target directly - it can't be created on
# the Mac and pushed over (wrong architecture, same class of mistake as
# building serial_chat on the Mac into the wrong place).
#
# Run via: perch exec sh scripts/setup_security_env.sh
set -e

cd "$(dirname "$0")/../security"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# Triggers config.py's first-run bootstrap, writing security/.env with a
# fresh random SECRET_KEY and placeholder admin/SMTP fields.
.venv/bin/python -c "import config"

echo "done - edit security/.env before running (ADMIN_PASSWORD, SMTP_*)"
