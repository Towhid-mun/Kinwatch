"""Continuous monitoring loop: watches every active camera (see Camera
settings, /settings/camera - "all" or a specific selection), logs every
face each one sees, and emails the configured alert address when any of
them sees an unrecognized one. Run via: perch exec (see
scripts/run_security_monitor.sh) or, for real auto-start-on-boot,
scripts/setup_autostart.sh.

One independent thread per active camera (_watch_camera) - each opens its
own device, trains its own Recognizer instance (LBPH model objects aren't
shared across threads, to sidestep any concurrency question about
concurrent predict() calls on one), and runs the same detect -> recognize
-> log -> maybe-email cycle a single-camera setup always has. The shared
Haar cascade (recognizer._cascade) IS used concurrently across threads -
detectMultiScale() is read-only/stateless per call, which OpenCV cascade
classifiers are commonly relied on to support.

Every meaningful event goes through activity_log, prefixed with the
camera's device path so a multi-camera activity log stays readable -
visible live in this terminal AND on the web panel's Logs page
(security/activity.log, shared with app.py).
"""
import os
import sys
import threading
import time

import cv2

import activity_log
import camera
import config
import db
import emailer
import features
import recognizer

log = activity_log.get_logger("monitor")

_last_alert_at = {}
_last_alert_lock = threading.Lock()


def _maybe_email(image_path, ts, cooldown_seconds, device):
    if not features.ENABLE_EMAIL_ALERTS:
        log.info(f"[{device}] unknown person detected but email alerts are disabled in security/features.py - logged, not emailed")
        return False
    if db.get_setting("email_alerts_enabled", "1") != "1":
        log.info(f"[{device}] unknown person detected but email alerts are disabled on /settings - logged, not emailed")
        return False
    alert_email = db.get_setting("alert_email")
    if not alert_email:
        log.warning(f"[{device}] unknown person detected but no alert_email configured yet - skipping email (set it on /settings)")
        return False

    now = time.time()
    with _last_alert_lock:  # cooldown is per-camera, but the dict itself is shared across threads
        remaining = cooldown_seconds - (now - _last_alert_at.get(device, 0.0))
        if remaining > 0:
            log.info(f"[{device}] unknown person detected but alert cooldown active ({remaining:.0f}s left) - logged, not emailed")
            return False
        _last_alert_at[device] = now

    try:
        emailer.send_unknown_person_alert(alert_email, image_path, ts)
    except Exception as exc:  # noqa: BLE001 - report and keep monitoring, one bad send shouldn't kill this camera's loop
        log.error(f"[{device}] failed to send alert email to {alert_email}: {exc}")
        return False
    log.info(f"[{device}] alert email sent to {alert_email}")
    return True


def _watch_camera(device, rec):
    """Runs forever (until the process exits) watching one camera. Any
    uncaught exception here only takes down this camera's thread, not the
    others - logged loudly either way."""
    cap = camera.open_camera(device)
    if not cap.isOpened():
        log.error(f"[{device}] could not open camera - in use by the web app's Camview/Capture, or disconnected?")
        return

    log.info(f"[{device}] watching, checking every {config.CAPTURE_INTERVAL_SECONDS}s")

    try:
        while True:
            # Re-read each cycle so changes made on the settings pages
            # take effect on the next cycle, no restart needed.
            interval = float(db.get_setting("capture_interval_seconds", config.CAPTURE_INTERVAL_SECONDS))
            threshold = float(db.get_setting("lbph_confidence_threshold", config.LBPH_CONFIDENCE_THRESHOLD))
            cooldown = float(db.get_setting("alert_cooldown_seconds", config.ALERT_COOLDOWN_SECONDS))

            ok, frame = cap.read()
            if not ok:
                log.warning(f"[{device}] frame read failed, retrying")
                time.sleep(interval)
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            boxes = recognizer.detect_faces(gray)
            if len(boxes) == 0:
                log.debug(f"[{device}] no faces in this frame")

            for box in boxes:
                status, name, confidence = rec.identify(gray, box, threshold=threshold)
                ts = db.now_iso()
                camera_label = device.strip("/").replace("/", "-")
                fname = f"{ts.replace(':', '-')}_{camera_label}_{status}.jpg"
                image_path = os.path.join(config.DETECTIONS_DIR, fname)
                x, y, w, h = box
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
                cv2.imwrite(image_path, frame)

                if status == "known":
                    log.info(f"[{device}] recognized {name} (confidence {confidence:.1f}, threshold {threshold:.1f}) -> {fname}")
                else:
                    conf_note = f"confidence {confidence:.1f}, threshold {threshold:.1f}" if confidence is not None else "no one enrolled yet"
                    log.info(f"[{device}] unrecognized face detected ({conf_note}) -> {fname}")

                emailed = False
                if status == "unknown":
                    emailed = _maybe_email(image_path, ts, cooldown, device)

                db.log_detection(status, name, image_path, emailed, camera=device)

            time.sleep(interval)
    except Exception:
        log.exception(f"[{device}] camera thread crashed")
    finally:
        cap.release()
        log.info(f"[{device}] stopped watching")


def run():
    db.init_db()

    devices = camera.selected_devices()
    log.info(f"active cameras: {', '.join(devices)}")

    known_people = db.list_known_people()
    log.info(f"training on {len(known_people)} known people: {', '.join(p['name'] for p in known_people) or '(none)'}")

    threads = []
    for device in devices:
        rec = recognizer.Recognizer()
        rec.reload(known_people)  # own instance per thread - see module docstring
        t = threading.Thread(target=_watch_camera, args=(device, rec), name=f"cam-{device}", daemon=True)
        t.start()
        threads.append(t)

    try:
        while True:
            time.sleep(1)
            if not any(t.is_alive() for t in threads):
                log.error("every camera thread has stopped - nothing left to watch, exiting")
                return 1
    except KeyboardInterrupt:
        log.info("stopped (Ctrl+C)")
    return 0


if __name__ == "__main__":
    sys.exit(run())
