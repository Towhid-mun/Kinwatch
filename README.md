# Kinwatch

A lightweight home-security camera system for the Raspberry Pi 4. It
watches a USB webcam, recognizes enrolled "safe" people, and emails a
snapshot when it sees someone it doesn't recognize. It's managed from a
small web admin panel.

Designed for the Pi 4B's limited RAM: OpenCV Haar cascades for face
detection and LBPH for recognition. No GPU and no model downloads at
runtime.

## Features

- **Continuous monitoring**: face detection and recognition on the live camera feed
- **Email alerts** with a snapshot for unknown faces, with a cooldown
- **Admin web panel** (Flask): log in, enroll people by upload or live capture,
  watch the live view (CamView), and view detection and activity logs
- **Settings in the panel**: alert email, detection tuning, camera, and Wi-Fi
- **Runs as systemd services** that start on boot, with a narrowly scoped
  reboot/monitor control in the panel
- **`serial_chat`**: a small C tool for duplex chat between the Mac and the Pi
  over the USB-C gadget link

## Repository layout

```
.
├── security/              # Home-security application (Python)
│   ├── app.py             #   Flask admin web panel
│   ├── monitor.py         #   Continuous camera monitoring loop
│   ├── recognizer.py      #   Face detection / LBPH recognition
│   ├── camera.py, camera_devices.py
│   ├── db.py, emailer.py, activity_log.py, wifi.py
│   ├── config.py          #   Loads security/.env (secrets, generated on target)
│   ├── features.py        #   Build-time feature flags
│   ├── templates/, static/
│   └── requirements.txt
├── src/
│   └── serial_chat.c      # USB-serial chat tool (C)
├── scripts/               # Target-side setup / run / maintenance scripts
├── docs/                  # Technical docs and business analysis
├── Makefile               # Builds serial_chat
└── .perch.toml            # Remote build/run target configuration
```

## Development workflow

This project builds and runs **on the Pi, not locally**. Everything goes
through [`perch`](CLAUDE.md), which mirrors this workspace to the target
and runs commands there:

```bash
perch build                 # make (on the Pi)
perch run                   # make && ./serial_chat
perch exec <cmd>            # run any command on the Pi
perch pull <path>           # bring target-side output back
```

This workspace is the source of truth. The target's copy is derived and
gets overwritten on every sync.

## Quick start (security system)

```bash
# 1. One-time: create the venv, install dependencies, bootstrap security/.env
perch exec sh scripts/setup_security_env.sh

# 2. On the Pi, set ADMIN_PASSWORD and SMTP_* in security/.env

# 3. Install as boot-time services
perch exec sudo sh scripts/setup_reboot_permission.sh
perch exec sudo sh scripts/setup_autostart.sh

# Redeploy after code changes
perch exec sudo sh scripts/restart_security.sh
```

Then open `http://<pi-address>:8080`.

For foreground development runs, see `scripts/run_security_web.sh` and
`scripts/run_security_monitor.sh`.

## Documentation

| Doc | Contents |
| --- | --- |
| [docs/HOME-SECURITY.md](docs/HOME-SECURITY.md) | Security system architecture, setup, operation, camera contention, future work |
| [docs/PHASE-5-BUILD-AND-RUN.md](docs/PHASE-5-BUILD-AND-RUN.md) | `serial_chat` and USB gadget setup, building the Mac side |
| [docs/CAMERA-TEST.md](docs/CAMERA-TEST.md) | Single-frame webcam sanity check |
| [docs/business-analysis/](docs/business-analysis/README.md) | Current state, gaps, viability, roadmap, business plan |

## Security notes

- `security/.env` holds secrets. It's generated on the target, git-ignored,
  and excluded from the perch mirror.
- Face photos, detection snapshots, the SQLite database, and logs exist
  only on the target and are never committed.
