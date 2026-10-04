"""Admin web panel: login, enroll "safe" people (upload or live capture),
camview, settings, and a test/logs page showing recent detections.

Camview/capture DO open the camera directly (for real continuous video,
not a slideshow) - see docs/HOME-SECURITY.md's "camera contention"
section: this conflicts with monitor.py, which also needs exclusive
access to the same device. Stop the monitor first if you want to view
live video or capture an enrollment photo.

Run via: perch exec (no --tty needed, it's not interactive)
sh scripts/run_security_web.sh
"""
import base64
import functools
import hmac
import os
import subprocess
import threading

import cv2
from flask import Flask, Response, jsonify, redirect, render_template, request, send_from_directory, session, url_for

import activity_log
import camera
import camera_devices
import config
import db
import features
import wifi

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.jinja_env.globals["features"] = features  # templates gate nav items/controls on these directly
log = activity_log.get_logger("app")

db.init_db()


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@app.route("/")
def index():
    return redirect(url_for("dashboard") if session.get("admin") else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if hmac.compare_digest(username, config.ADMIN_USERNAME) and hmac.compare_digest(
            password, config.ADMIN_PASSWORD
        ):
            session["admin"] = True
            log.info(f"admin login succeeded ({request.remote_addr})")
            return redirect(request.args.get("next") or url_for("dashboard"))
        error = "Invalid username or password"
        log.warning(f"admin login FAILED for username {username!r} ({request.remote_addr})")
    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", people=db.list_known_people(), devices=camera.selected_devices())


@app.route("/people/add", methods=["POST"])
@login_required
def add_person():
    name = request.form.get("name", "").strip()
    photo = request.files.get("photo")
    if name and photo and photo.filename:
        safe_name = "".join(c for c in name if c.isalnum() or c in "-_") or "person"
        ext = os.path.splitext(photo.filename)[1] or ".jpg"
        dest = os.path.join(config.KNOWN_FACES_DIR, f"{safe_name}_{db.now_iso()}{ext}".replace(":", "-"))
        photo.save(dest)
        db.add_known_person(name, dest)
        log.info(f"enrolled safe person {name!r} (uploaded photo) - restart the monitor to pick this up")
    return redirect(url_for("dashboard"))


@app.route("/people/<int:person_id>/delete", methods=["POST"])
@login_required
def delete_person(person_id):
    db.delete_known_person(person_id)
    log.info(f"removed safe person id={person_id}")
    return redirect(url_for("dashboard"))


@app.route("/settings")
@login_required
def settings():
    return redirect(url_for("alert_email_settings"))  # old combined page - keep old links/bookmarks working


@app.route("/settings/alert-email", methods=["GET", "POST"])
@login_required
def alert_email_settings():
    if request.method == "POST":
        db.set_setting("alert_email", request.form.get("alert_email", "").strip())
        # Checkboxes are absent from form data entirely when unchecked -
        # presence, not value, is what "checked" means here.
        db.set_setting("email_alerts_enabled", "1" if "email_alerts_enabled" in request.form else "0")
        log.info("alert email settings updated")
        return redirect(url_for("alert_email_settings"))
    return render_template(
        "alert_email_settings.html",
        alert_email=db.get_setting("alert_email", ""),
        email_alerts_enabled=db.get_setting("email_alerts_enabled", "1") == "1",
    )


@app.route("/settings/detection-tuning", methods=["GET", "POST"])
@login_required
def detection_tuning_settings():
    if request.method == "POST":
        for key, cast in (
            ("capture_interval_seconds", int),
            ("lbph_confidence_threshold", float),
            ("alert_cooldown_seconds", int),
        ):
            raw = request.form.get(key, "").strip()
            if raw:
                try:
                    cast(raw)  # validate before storing - a bad value would otherwise wedge monitor.py's next cycle
                except ValueError:
                    continue
                db.set_setting(key, raw)
        log.info("detection tuning settings updated")
        return redirect(url_for("detection_tuning_settings"))
    return render_template(
        "detection_tuning_settings.html",
        capture_interval_seconds=db.get_setting("capture_interval_seconds", config.CAPTURE_INTERVAL_SECONDS),
        lbph_confidence_threshold=db.get_setting("lbph_confidence_threshold", config.LBPH_CONFIDENCE_THRESHOLD),
        alert_cooldown_seconds=db.get_setting("alert_cooldown_seconds", config.ALERT_COOLDOWN_SECONDS),
    )


@app.route("/settings/camera", methods=["GET", "POST"])
@login_required
def camera_settings():
    if request.method == "POST":
        if request.form.get("use_all_cameras"):
            db.set_setting("camera_devices", "all")
        else:
            selected = request.form.getlist("camera_device")
            db.set_setting("camera_devices", ",".join(selected))
        pixel_format = request.form.get("camera_pixel_format", "").strip()
        db.set_setting("camera_pixel_format", pixel_format)  # "" is valid - means "let V4L2 pick"
        resolution = request.form.get("camera_resolution", "").strip()
        db.set_setting("camera_resolution", resolution)
        log.info(
            f"camera settings updated: devices={db.get_setting('camera_devices')!r} "
            f"format={pixel_format!r} resolution={resolution!r} - restart the monitor to pick this up"
        )
        return redirect(url_for("camera_settings"))

    detected = camera_devices.list_cameras()
    raw = db.get_setting("camera_devices", "")
    use_all = raw == "all"
    return render_template(
        "camera_settings.html",
        detected_cameras=detected,
        use_all_cameras=use_all,
        selected_paths=[] if use_all else [p for p in raw.split(",") if p],
        camera_pixel_format=db.get_setting("camera_pixel_format", ""),
        camera_resolution=db.get_setting("camera_resolution", ""),
        pixel_format_choices=camera_devices.PIXEL_FORMATS,
        resolution_choices=camera_devices.RESOLUTIONS,
    )


def _gen_frames(cap, device):
    log.info(f"camera stream started ({device})")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            ok, buf = cv2.imencode(".jpg", frame)
            if not ok:
                continue
            yield (
                b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
            )
    finally:
        cap.release()
        log.info(f"camera stream ended ({device})")


@app.route("/stream.mjpg")
@login_required
def stream_mjpg():
    active = camera.selected_devices()
    device = request.args.get("device") or (active[0] if active else config.CAMERA_DEVICE)
    if device not in active:
        return jsonify(error=f"{device!r} is not one of the active cameras (/settings/camera)"), 404

    # Opened here, not inside the generator, specifically so a failure
    # can return a real error status (503) instead of a misleading 200
    # with an empty streaming body - a generator can't change the status
    # code after Flask's already started sending the response.
    cap = camera.open_camera(device)
    if not cap.isOpened():
        cap.release()
        log.error(f"could not open {device} for streaming - in use by monitor.py?")
        return jsonify(error=f"could not open {device} - likely in use by the monitor"), 503

    return Response(_gen_frames(cap, device), mimetype="multipart/x-mixed-replace; boundary=frame")


def _monitor_active():
    try:
        out = subprocess.run(
            ["systemctl", "is-active", "security-monitor.service"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        return out == "active"
    except (FileNotFoundError, subprocess.SubprocessError):
        return False  # not installed (scripts/setup_autostart.sh not run) - nothing to pause


@app.route("/camera/monitor-status")
@login_required
def camera_monitor_status():
    return jsonify(active=_monitor_active())


@app.route("/camera/pause-monitor", methods=["POST"])
@login_required
def camera_pause_monitor():
    log.info(f"monitor paused from CamView/Capture by {request.remote_addr}")
    try:
        subprocess.run(
            ["sudo", "-n", "systemctl", "stop", "security-monitor.service"],
            check=True, capture_output=True, text=True, timeout=10,
        )
    except subprocess.CalledProcessError as exc:
        log.error(f"failed to stop monitor: {exc.stderr.strip()}")
        return jsonify(error=f"could not stop the monitor - has scripts/setup_reboot_permission.sh been run? ({exc.stderr.strip()})"), 500
    except Exception as exc:  # noqa: BLE001
        log.error(f"failed to stop monitor: {exc}")
        return jsonify(error=str(exc)), 500
    return jsonify(ok=True)


@app.route("/camera/resume-monitor", methods=["POST"])
@login_required
def camera_resume_monitor():
    log.info(f"monitor resumed from CamView/Capture by {request.remote_addr}")
    try:
        subprocess.run(
            ["sudo", "-n", "systemctl", "start", "security-monitor.service"],
            check=True, capture_output=True, text=True, timeout=10,
        )
    except subprocess.CalledProcessError as exc:
        log.error(f"failed to start monitor: {exc.stderr.strip()}")
        return jsonify(error=exc.stderr.strip()), 500
    except Exception as exc:  # noqa: BLE001
        log.error(f"failed to start monitor: {exc}")
        return jsonify(error=str(exc)), 500
    return jsonify(ok=True)


@app.route("/camview")
@login_required
def camview():
    return render_template("camview.html", devices=camera.selected_devices())


@app.route("/capture")
@login_required
def capture():
    return render_template("capture.html", devices=camera.selected_devices())


@app.route("/people/add_capture", methods=["POST"])
@login_required
def add_person_capture():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    image_data_url = data.get("image_data_url") or ""
    if not name or not image_data_url.startswith("data:image"):
        return jsonify(error="name and a captured image are both required"), 400

    _, _, b64data = image_data_url.partition(",")
    try:
        raw = base64.b64decode(b64data)
    except (ValueError, base64.binascii.Error):
        return jsonify(error="invalid image data"), 400

    safe_name = "".join(c for c in name if c.isalnum() or c in "-_") or "person"
    dest = os.path.join(config.KNOWN_FACES_DIR, f"{safe_name}_{db.now_iso()}.jpg".replace(":", "-"))
    with open(dest, "wb") as f:
        f.write(raw)
    db.add_known_person(name, dest)
    log.info(f"enrolled safe person {name!r} (captured from live camera) - restart the monitor to pick this up")
    return jsonify(ok=True)


@app.route("/logs")
@login_required
def logs():
    return render_template(
        "logs.html",
        detections=db.recent_detections(),
        activity_lines=activity_log.tail(200),
    )


@app.route("/logs/clear", methods=["POST"])
@login_required
def clear_logs():
    image_paths = db.clear_detections()
    removed = 0
    for path in image_paths:
        try:
            os.remove(path)
            removed += 1
        except OSError:
            pass  # already gone or otherwise unremovable - the DB row is what mattered
    log.info(f"cleared {len(image_paths)} detection record(s), removed {removed} snapshot file(s)")
    return redirect(url_for("logs"))


@app.route("/system")
@login_required
def system():
    autostart_status = _systemd_status()
    return render_template("system.html", autostart_status=autostart_status)


def _systemd_status():
    """Best-effort - returns None if the units aren't installed yet
    (scripts/setup_autostart.sh hasn't been run) rather than erroring."""
    try:
        out = subprocess.run(
            ["systemctl", "is-active", "security-monitor.service", "security-web.service"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip().splitlines()
        return {"monitor": out[0] if len(out) > 0 else "unknown", "web": out[1] if len(out) > 1 else "unknown"}
    except (FileNotFoundError, subprocess.SubprocessError):
        return None


@app.route("/system/reboot", methods=["POST"])
@login_required
def system_reboot():
    if not features.ENABLE_REBOOT_CONTROL:
        return jsonify(error="reboot control is disabled (security/features.py)"), 403
    log.warning(f"REBOOT triggered via admin panel by {request.remote_addr}")
    try:
        # -n: fail immediately rather than hang waiting for a password
        # that will never come on a non-interactive web request, if
        # scripts/setup_reboot_permission.sh hasn't granted this yet.
        subprocess.run(["sudo", "-n", "systemctl", "reboot"], check=True, capture_output=True, text=True, timeout=10)
    except subprocess.CalledProcessError as exc:
        log.error(f"reboot command failed: {exc.stderr.strip()}")
        return jsonify(error=f"reboot failed - has scripts/setup_reboot_permission.sh been run? ({exc.stderr.strip()})"), 500
    except Exception as exc:  # noqa: BLE001 - report, don't crash the app over this
        log.error(f"failed to trigger reboot: {exc}")
        return jsonify(error=str(exc)), 500
    return jsonify(ok=True)


_wifi_change_lock = threading.Lock()
_wifi_change_in_progress = False


@app.route("/settings/wifi", methods=["GET", "POST"])
@login_required
def wifi_settings():
    global _wifi_change_in_progress

    if request.method == "POST":
        ssid = request.form.get("ssid", "").strip()
        password = request.form.get("password", "")
        if not ssid:
            return redirect(url_for("wifi_settings"))

        with _wifi_change_lock:
            if _wifi_change_in_progress:
                return redirect(url_for("wifi_settings", pending="1"))
            _wifi_change_in_progress = True

        log.warning(f"Wi-Fi change to {ssid!r} triggered by {request.remote_addr} - applying in background, auto-reverts on failure")

        def _apply():
            global _wifi_change_in_progress
            try:
                ok, message = wifi.change_wifi(ssid, password)
                (log.info if ok else log.error)(f"Wi-Fi change: {message}")
            finally:
                _wifi_change_in_progress = False

        threading.Thread(target=_apply, daemon=True, name="wifi-change").start()
        # Returns immediately - this request's own connection may be the
        # one about to change, so it can't wait around for the result.
        return redirect(url_for("wifi_settings", pending="1"))

    interface, current_name = wifi.current_connection()
    try:
        networks = wifi.scan_networks(interface or "wlan0")
    except subprocess.SubprocessError:
        networks = []
    return render_template(
        "wifi_settings.html",
        current_name=current_name,
        networks=networks,
        pending=request.args.get("pending") == "1",
        change_in_progress=_wifi_change_in_progress,
    )


@app.route("/media/known/<path:filename>")
@login_required
def media_known(filename):
    return send_from_directory(config.KNOWN_FACES_DIR, filename)


@app.route("/media/detections/<path:filename>")
@login_required
def media_detections(filename):
    return send_from_directory(config.DETECTIONS_DIR, filename)


if __name__ == "__main__":
    if config.ADMIN_PASSWORD == "CHANGE_ME":
        log.warning(
            "security/.env still has the default ADMIN_PASSWORD - "
            "edit it before exposing this on your network."
        )
    # threaded=True matters here, not just a nice-to-have: an open
    # /stream.mjpg connection holds its request thread for as long as the
    # camera stays open (potentially the whole browsing session). Without
    # this, the single-threaded dev server would block every other page
    # (login, dashboard, logs...) for anyone while camview/capture is open.
    app.run(host="0.0.0.0", port=8080, threaded=True)
