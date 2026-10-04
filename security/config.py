"""Loads security/.env (KEY=value, one per line) - not python-dotenv, this
project keeps dependencies minimal and a full .env parser is overkill for
half a dozen settings. .env itself is excluded from the perch mirror
(.perch.toml) - it holds secrets and is local to the target.
"""
import os
import secrets

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(HERE, ".env")


def _load_env(path):
    values = {}
    if not os.path.exists(path):
        return values
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def _write_env(path, values):
    with open(path, "w") as f:
        for key, value in values.items():
            f.write(f"{key}={value}\n")


def _bootstrap_if_missing(path):
    """First run: create a .env with a fresh random SECRET_KEY and
    placeholder admin/SMTP fields the operator must fill in themselves -
    never generate a guessable admin password."""
    if os.path.exists(path):
        return
    _write_env(
        path,
        {
            "SECRET_KEY": secrets.token_hex(32),
            "ADMIN_USERNAME": "admin",
            "ADMIN_PASSWORD": "CHANGE_ME",
            "SMTP_HOST": "smtp.gmail.com",
            "SMTP_PORT": "587",
            "EMAIL_ADDRESS": "",
            "EMAIL_APP_PASSWORD": "",
            "PUSHOVER_USER": "",
            "PUSHOVER_TOKEN": "",
            "ALERT_COOLDOWN_SECONDS": "300",
            "CAPTURE_INTERVAL_SECONDS": "5",
            "LBPH_CONFIDENCE_THRESHOLD": "70",
        },
    )


_bootstrap_if_missing(ENV_PATH)
_env = _load_env(ENV_PATH)

SECRET_KEY = _env.get("SECRET_KEY", "")
ADMIN_USERNAME = _env.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = _env.get("ADMIN_PASSWORD", "CHANGE_ME")

# Gmail by default. EMAIL_ADDRESS is both the SMTP login and the From
# address; EMAIL_APP_PASSWORD must be a Google App Password (not the
# account password). Google displays it in groups of 4 ("abcd efgh ijkl
# mnop") - spaces are stripped so it can be pasted as shown. The old
# SMTP_USERNAME/SMTP_PASSWORD names are still read as a fallback so an
# existing .env keeps working.
SMTP_HOST = _env.get("SMTP_HOST", "") or "smtp.gmail.com"
SMTP_PORT = int(_env.get("SMTP_PORT", "") or "587")
EMAIL_ADDRESS = _env.get("EMAIL_ADDRESS") or _env.get("SMTP_USERNAME", "")
EMAIL_APP_PASSWORD = (_env.get("EMAIL_APP_PASSWORD") or _env.get("SMTP_PASSWORD", "")).replace(" ", "")

# Pushover (pushover.net): PUSHOVER_USER is your user key (Pushover
# dashboard), PUSHOVER_TOKEN is the API token of an application you
# create for this system.
PUSHOVER_USER = _env.get("PUSHOVER_USER", "").strip()
PUSHOVER_TOKEN = _env.get("PUSHOVER_TOKEN", "").strip()

ALERT_COOLDOWN_SECONDS = int(_env.get("ALERT_COOLDOWN_SECONDS", "300"))
CAPTURE_INTERVAL_SECONDS = int(_env.get("CAPTURE_INTERVAL_SECONDS", "5"))
LBPH_CONFIDENCE_THRESHOLD = float(_env.get("LBPH_CONFIDENCE_THRESHOLD", "70"))

DB_PATH = os.path.join(HERE, "security.db")
KNOWN_FACES_DIR = os.path.join(HERE, "known_faces")
DETECTIONS_DIR = os.path.join(HERE, "detections")
ACTIVITY_LOG_PATH = os.path.join(HERE, "activity.log")
CAMERA_DEVICE = "/dev/video0"

os.makedirs(KNOWN_FACES_DIR, exist_ok=True)
os.makedirs(DETECTIONS_DIR, exist_ok=True)
