# Home security system

A separate module from `serial_chat` and the camera test - continuously
watches the USB webcam, recognizes enrolled "safe" people, and emails a
snapshot when it sees someone it doesn't recognize. Three independent
pieces:

- **`security/monitor.py`** - the continuous camera loop (detection,
  recognition, logging, email alerts). Owns `/dev/video0` while running.
- **`security/app.py`** - the admin web panel: login, enroll safe people
  (upload or live capture), Camview (live video), Settings, and a
  logs/test page. Camview/capture open the camera directly (see
  **Camera contention** below); the rest of the app doesn't touch it.
- **`security/recognizer.py` / `db.py` / `emailer.py` / `config.py`** -
  shared logic both of the above use.

Kept intentionally lightweight for the Pi 4B's 1.8GB RAM: OpenCV's
built-in Haar cascade for face *detection* and LBPH for *recognition* -
both bundled with `opencv-contrib-python-headless`, no GPU, no large
model downloads at runtime. See **Future work** below for the
higher-accuracy alternative and why it wasn't the default.

The web panel's nav (hamburger menu, top left) is grouped into: **Safe
people** (add/capture), **Camera** (CamView), **Settings** (alert email,
detection tuning, camera), **System** (Logs, Reboot system). The
Dashboard (home page) also has a click-to-load "Live preview" - not
loaded automatically, since visiting the home page shouldn't silently
steal the camera from the monitor.

## Wi-Fi settings

`/settings/wifi` - view the current network, nearby networks (with
signal/security), and change networks. This Pi has **no Ethernet
fallback** - it reaches you only through Wi-Fi - so a naive "just apply
the new credentials" implementation risks stranding it, reachable only
with a monitor and keyboard plugged in directly. `netplan` (which would
otherwise have a built-in safe-apply-with-rollback command, `netplan
try`) isn't actually installed on this system despite config files
existing for it, so this doesn't use that.

Instead (`security/wifi.py`): submitting a new network creates a
*separate* NetworkManager connection profile and brings it up with
`nmcli`'s own `--wait`, which blocks until success or failure is known
(typically seconds, for something like a wrong password). **On any
failure, it automatically deletes the failed profile and reactivates
whatever was working before** - no manual recovery needed for the common
case (typo'd password, SSID out of range). Runs in a background thread,
not the request/response cycle, since the HTTP connection carrying that
very request may be the one about to change - the page just tells you to
wait ~30s and refresh.

**What this can't protect against:** if the new network's credentials
are *correct* but it's a genuinely different network that doesn't route
back to wherever you manage this from, there's no way to detect that
from the Pi's side - that needs physical access to recover, same as any
device that changes its own network config. The UI warns about this
before you submit.

Modifying commands run as root (`sudo -n nmcli ...`) rather than the
app's own user - NetworkManager's default polkit policy for a user
managing their own connections typically requires an active logind
session, which the systemd-managed web service doesn't have, so
unprivileged calls can fail there even though they'd work fine from an
interactive terminal. Relies on this machine's existing sudo access
rather than a newly-scoped rule - the arguments (SSID, password) are
inherently variable, so a tight sudoers command match isn't practical
here the way it is for `systemctl reboot`.

**Only the read-only parts (scanning, showing the current network) were
verified in development** - the actual change-and-rollback path needs a
live test against a real second network, and deliberately wasn't run
here: even with the rollback logic, a bug in that logic could strand the
one connection this whole project is managed through.

## Camera settings (multi-camera)

`/settings/camera` - configures cameras **everywhere they're opened**
(CamView, Capture, and the monitor - `security/camera.py` is the one
shared module all three call for both "which cameras are active" and
"open one of them", so there's a single source of truth rather than each
hardcoding its own device).

**Active cameras** - either a specific set, or "Use all detected
cameras" (re-resolved against actual hardware on every use, so a
reconnected/renumbered camera is picked up without touching this page
again). Whatever's active applies with full feature parity - each one
independently:
- gets its own tile in CamView (a grid, one live stream per camera) and
  Capture (each tile has its own "Capture from this camera" button)
- gets its own thread in the monitor (`security/monitor.py`'s
  `_watch_camera`), running the complete detect -> recognize -> log ->
  maybe-email cycle on its own schedule, independently of the others -
  one camera being slow or disconnected doesn't stall the rest
- appears in `security/security.db`'s detections with which camera saw
  it (a "Camera" column on `/logs`), and in the activity log with a
  `[/dev/videoN]` prefix on every line

Detected cameras are enumerated via `v4l2-ctl --list-devices`
(`security/camera_devices.py`), filtered down to actual capture-capable
devices. This Pi has one physical USB webcam, but `v4l2-ctl` also lists
several Broadcom/Pi hardware codec and ISP virtual `/dev/video*` nodes
(`bcm2835-codec-decode`, `bcm2835-isp`, `rpi-hevc-dec`, `bcm2835-codec`)
alongside it - those are excluded, along with the webcam's own
metadata-only second node, since none of them are anything you'd
actually want to select as a capture source.

**Pixel format / image type** (MJPG/YUYV/Auto) and **resolution/ratio**
apply to every active camera - not configured per-camera, kept simple
deliberately.

Nothing selected yet falls back to `config.CAMERA_DEVICE`, identical to
single-camera behavior from before this page existed. CamView and
Capture pick up a saved change on the very next stream; **the monitor
only picks it up on its next restart** (opens its cameras once at
startup, same as the enrolled-people list).

**Only tested with one physical camera** (that's all this Pi has) - the
multi-camera path (multiple simultaneous `_watch_camera` threads, the
`camera` column, multiple simultaneous CamView tiles) is implemented and
exercised through the single-camera case, but not verified end-to-end
with two or more cameras actually plugged in at once.

## Developer feature toggles

`security/features.py` - build-time switches, distinct from `.env`
(target-only secrets) and `/settings` (end-user runtime preferences
stored in the DB, editable from the browser). Edit and redeploy
(`perch build`/`perch exec`) to change:

- `ENABLE_ACTIVITY_LOG` - master switch for `security/activity.log` and
  the Logs page's Activity log section. Both processes still print to
  stderr either way; this only controls persistence/web visibility.
- `ENABLE_EMAIL_ALERTS` - hard kill switch for the email feature,
  overriding the admin's `/settings` checkbox and `alert_email` - use to
  ship a build where email is off no matter what an admin configures.
- `AUTO_START_ON_BOOT` - whether `scripts/setup_autostart.sh` *enables*
  (vs. merely installs) the systemd units, see below.
- `ENABLE_REBOOT_CONTROL` - whether the admin panel exposes "Reboot
  system" at all (hidden client-side AND refused server-side when off).

## One-time setup

```bash
perch exec sh scripts/setup_security_env.sh
```

Creates `security/.venv` (excluded from the perch mirror - built-in
`.venv/` exclude) and installs `flask` + `opencv-contrib-python-headless`
from prebuilt piwheels (no slow from-source compile on this platform).
Also bootstraps `security/.env` with a random `SECRET_KEY` and
placeholder admin/SMTP fields.

**Edit `security/.env` on the Pi before using this for real:**
```bash
ssh pi
cd perch/my-project/security
nano .env
```
At minimum set `ADMIN_PASSWORD` (still the placeholder `CHANGE_ME` until
you do), and `SMTP_USERNAME`/`SMTP_PASSWORD` to actually send alert
emails. `.env` is excluded from the mirror on purpose - it's target-only,
never touches the Mac.

**Using Gmail: `SMTP_PASSWORD` must be an App Password, not your real
account password.** Using the real password fails SMTP auth with `535
... Username and Password not accepted` (logged to the activity log,
see below) - this is Gmail rejecting it, not a bug here. Enable
2-Step Verification (`myaccount.google.com/security`), then generate an
App Password at `myaccount.google.com/apppasswords` and use that
16-character value instead.

## Running it

### Production: auto-start on boot (recommended)

```bash
perch exec sudo sh scripts/setup_reboot_permission.sh   # one-time: narrow sudo grant for the Reboot control
perch exec sudo sh scripts/setup_autostart.sh            # installs + enables both systemd units
```

Installs `security-monitor.service` and `security-web.service`
(`/etc/systemd/system/`), running as your own user (not root), and - per
`features.py`'s `AUTO_START_ON_BOOT` (default on) - enables them, so both
start automatically on boot, including after the admin panel's **Reboot
system** control. Check status any time:
```bash
ssh pi sudo systemctl status security-monitor security-web
```
or on the web panel's **System** page (green/red status dot for each).
Logs go to the normal place either way: `journalctl -u security-monitor`
for stdout/stderr, `security/activity.log`/`/logs` for the structured
activity log.

**Reboot system** (web panel, System page) reboots the Pi itself via
`sudo systemctl reboot` - needs `setup_reboot_permission.sh` run first
(a narrowly-scoped passwordless-sudo rule for exactly that command, set
up via a `/etc/sudoers.d/` drop-in - nothing broader). Drops your SSH
session and this page too, for about a minute.

### Development: run in the foreground manually

Useful for iterating without redeploying systemd units each time.
**Self-cleaning** - `run_security_web.sh`/`run_security_monitor.sh`
automatically stop whatever ran before (the systemd-managed instance if
that's active, or a leftover manually-run one via a PID file,
`security/.web.pid`/`.monitor.pid`) before starting fresh. You should
never need to manually SSH in and hunt down/kill a stray process again -
just rerun the script.

The one thing this *doesn't* cover: perch's own run lock refuses a
*second, still-connected* `perch exec` session for this project outright
(`perch: run lock is held...`) - that's a different, perch-level guard
against two overlapping invocations, not the app conflicting with
itself. `perch exec --replace ...` takes over it if you hit that.

Redeploying the systemd-managed (production) instance after a code
change is one command, not manual stop-then-start:
```bash
perch exec sudo sh scripts/restart_security.sh
```

**Admin web panel** (not interactive, no `--tty` needed):
```bash
perch exec sh scripts/run_security_web.sh
```
Then browse to `http://10.0.0.131:8080` (the Pi's LAN address) from the
Mac. Log in, enroll safe people (name + one clear front-facing photo
each, via upload on Dashboard or live capture on `/capture`), and set
the alert email under `/settings`. Check `/logs` for the test page -
every detection (known or unknown) with its snapshot, plus a raw
activity log (see **Activity log** below) - both sections refresh every
10s.

**Monitor** (`perch run` won't work here - this project's `commands.run`
in `.perch.toml` is still `serial_chat`'s, so use `perch exec`):
```bash
perch exec sh scripts/run_security_monitor.sh
```
Trains on whatever's enrolled at startup, then checks the camera every
`capture_interval_seconds` (`/settings`, default 5s). **Restart it after
enrolling a new person** - the enrolled-people list only loads at
startup, it doesn't hot-reload (see future work). The three tunables on
`/settings` (capture interval, LBPH threshold, alert cooldown) *are*
re-read from the database every cycle, so changing those takes effect on
the monitor's next iteration with no restart needed. `capture_snapshot.sh`
from the camera-test module will conflict with it for the camera device
if run at the same time.

## Camview and capture

- `/camview` - continuous live video (`<img>` streaming an MJPEG feed),
  just to confirm the camera's actually working and see what it sees.
- `/capture` - the same live feed plus a "Capture frame" button: grabs
  the currently-displayed frame client-side (via `<canvas>`), then a
  name field saves it as a new safe person - an alternative to uploading
  a file from Dashboard.

**Camera contention:** both of these open cameras directly, for real
continuous video rather than a slideshow - and so does the monitor. Only
one process can hold a given device at a time - this is **per camera
device**, so with multiple cameras active, one being watched by the
monitor doesn't block viewing a *different* one in CamView/Capture, only
that same one.

Both pages have a **"Stop monitor & view cameras" button** right on the
page (a status badge shows whether the monitor's currently running) - no
SSH session needed. Clicking it calls `/camera/pause-monitor`
(`sudo systemctl stop security-monitor.service`, narrowly-scoped
passwordless sudo from `scripts/setup_reboot_permission.sh` - it also
grants the monitor start/stop commands now, not just reboot), then loads
the streams once the camera's actually free. A **"Resume monitoring"**
button appears in its place - the page also warns via a
browser-native confirmation if you try to navigate away while you're the
one who paused it, so it's harder to forget monitoring is off. A failed
stream still shows a broken image for that tile and returns a real `503`
(not a misleading `200`) with a JSON error - other tiles for other
cameras are unaffected. See future work for a shared-camera-broker
design that would remove the restriction (and this workaround)
entirely.

The "Clear" button above the detections table on `/logs` deletes every
detection row and its saved snapshot file (asks for confirmation first -
this can't be undone). It only clears detections, not the activity log
below it - different data, kept separate.

## Activity log

`security/activity.log` (excluded from the perch mirror - target-only,
same as the other generated data) - a shared runtime log both `monitor.py`
and `app.py` append to via `activity_log.py`, visible on `/logs` below
the detections table. Covers what print-statement debugging doesn't:

- Monitor: trained-on-N-people at startup, camera open/fail, **every
  face match or miss with its LBPH confidence score and the threshold it
  was compared against** (so a near-miss like "confidence 74.6,
  threshold 70.0" tells you the threshold might need loosening, not that
  recognition is broken), and every alert email sent/skipped
  (cooldown/no-address-configured)/failed with the reason.
- App: admin login success/failure, safe-person enrolled/removed,
  settings updated, camera stream started/ended/failed to open.

Still prints to stderr too (visible in the `perch exec`/`perch run --tty`
terminal), so nothing about watching it live changed - the file (and the
web page) just make it available after the fact and from the browser as
well. Per-cycle "no face in this frame" is logged at DEBUG level, which
the default INFO level filters out (would otherwise flood the log every
capture interval); raise `activity_log.get_logger`'s level if you want
that noise too.


## How detection works

1. Every cycle, grab one frame, convert to grayscale, run the Haar
   cascade (`security/haarcascade_frontalface_default.xml` - bundled in
   this repo, not loaded from the pip package, since the piwheels build
   of opencv-contrib-python-headless for this platform ships an *empty*
   `cv2/data/`, unlike most other platforms).
2. For each face found, LBPH compares it against the enrolled people
   (trained once at monitor startup). Below the LBPH confidence
   threshold (`/settings`, default 70, lower = stricter) it's a match;
   otherwise unknown. With nobody enrolled yet, everything is unknown by
   design.
3. Every detection (known or unknown) is logged to `security/security.db`
   with a saved snapshot in `security/detections/`, visible on `/logs`.
4. An **unknown** detection also emails the configured alert address, if
   `/settings`' "Send an email when an unrecognized person is detected"
   checkbox is on (default: on) - with the snapshot attached, subject to
   the alert cooldown (`/settings`, default 300s) so a lingering intruder
   doesn't flood your inbox. It's still logged every cycle regardless of
   the checkbox or the cooldown, just
   not re-emailed.
5. A **known** match is logged only - no action yet. You said you'll
   design that behavior later; the log has the person's name on each row
   so it's there when you're ready to build on it.

## Data locations (all target-only, all excluded from the perch mirror)

- `security/.env` - secrets (admin password, SMTP credentials, secret key)
- `security/security.db` - SQLite: enrolled people, alert email, detection log
- `security/known_faces/` - enrolled people's photos
- `security/detections/` - saved snapshot per detection event
- `security/activity.log` - the runtime activity log (see above)
- `security/.venv/` - the Python virtualenv

None of this ever exists on the Mac - each is generated the first time
you use the corresponding feature, directly on the Pi.

## Future work

Deferred on purpose to get a working baseline first - none of this is
started:

- **Known-person action.** Right now a recognized "safe" person is only
  logged. What should happen instead (unlock something, silence
  monitoring, a different notification) is intentionally undesigned.
- **Hot-reload known faces.** The three numeric settings already
  hot-reload every monitor cycle, but the enrolled-people list itself
  still only loads at startup - adding someone via the web panel doesn't
  retrain the *running* monitor. A simple fix: poll the `known_people`
  table's row count/timestamp each loop and retrain when it changes.
- **Shared camera broker**, so Camview/Capture and the monitor can watch
  the *same* camera at the same time instead of fighting over it. Would
  need a small process per camera that owns the device and republishes
  frames (shared memory, a local socket, or a file the others poll)
  rather than each piece opening `cv2.VideoCapture` itself - real
  complexity, deliberately not built for the first version.
- **Multi-viewer Camview.** Right now `/stream.mjpg` opens a fresh
  `cv2.VideoCapture` per connection - a second simultaneous viewer of the
  *same* camera will fail to open the (typically exclusive-access)
  device. Fine for a single admin; the shared-camera-broker above would
  also fix this.
- **Multi-camera hardware testing.** The multi-camera path (concurrent
  `_watch_camera` threads, per-camera detection logs) is implemented and
  exercised through the single-camera case on this Pi (its only physical
  camera), but not verified end-to-end with two or more actually plugged
  in - worth a real test once a second camera's available.
- **Per-camera pixel format/resolution.** Currently one format and one
  resolution applies to every active camera; a genuinely mixed setup
  (e.g. a high-res indoor camera and a lower-res doorway camera) would
  need these to become per-camera settings instead of global ones.
- **Higher-accuracy recognition.** LBPH is lightweight but noticeably
  less accurate than embedding-based recognition (`face_recognition`/
  dlib). Wasn't the default because dlib often has to compile from
  source on this Pi (Debian 13/trixie is very new; piwheels may not have
  a prebuilt wheel yet), risking a 1+ hour build and possible OOM on
  1.8GB RAM. Worth revisiting once piwheels catches up, or by
  cross-compiling dlib separately.
- **DNN-based face detection.** Haar cascades are fast and dependency-free
  but more sensitive to angle/lighting than a modern DNN face detector
  (e.g. OpenCV's res10 SSD model) - both captures during initial testing
  missed a face that was angled/downward-facing to the camera. Worth
  trying if false negatives are a problem in practice.
- **Multiple photos per enrolled person.** Currently one photo per safe
  person; several angles/lighting conditions would improve LBPH accuracy.
- **Transactional email API** (SendGrid/Mailgun/etc.) as an alternative
  to SMTP + app password, for more reliable delivery.
- **Production WSGI server.** `app.py` currently runs Flask's own dev
  server (`app.run(...)`) - fine on a trusted LAN for now, but it warns
  on startup that it isn't meant for that; swap in something like
  `gunicorn` before exposing this more broadly.
- **HTTPS / stronger auth.** Single admin account, plaintext password
  comparison (constant-time, but not hashed) in `.env`, plain HTTP - all
  reasonable for a personal LAN-only tool today, not for anything more
  exposed.
