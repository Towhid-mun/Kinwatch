"""Pushover push notifications (https://pushover.net/api). Standard
library only (urllib + a hand-built multipart body for the snapshot
attachment) - this project keeps dependencies minimal.
"""
import json
import os
import uuid
import urllib.error
import urllib.request

import config

API_URL = "https://api.pushover.net/1/messages.json"
TIMEOUT_SECONDS = 20
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024  # Pushover's limit


def _multipart(fields, file_field=None):
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    if file_field:
        name, filename, data, mime = file_field
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n".encode() + data + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _send(title, message, image_path=None, priority=0):
    if not config.PUSHOVER_USER or not config.PUSHOVER_TOKEN:
        raise RuntimeError(
            "PUSHOVER_USER/PUSHOVER_TOKEN not set in security/.env - "
            "can't send Pushover notification"
        )
    fields = {
        "token": config.PUSHOVER_TOKEN,
        "user": config.PUSHOVER_USER,
        "title": title,
        "message": message,
        "priority": str(priority),
    }
    file_field = None
    if image_path:
        if os.path.getsize(image_path) > MAX_ATTACHMENT_BYTES:
            raise RuntimeError(f"{os.path.basename(image_path)} is over Pushover's 5 MB attachment limit")
        with open(image_path, "rb") as f:
            file_field = ("attachment", "snapshot.jpg", f.read(), "image/jpeg")
    body, content_type = _multipart(fields, file_field)
    req = urllib.request.Request(API_URL, data=body, headers={"Content-Type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            result = json.load(resp)
    except urllib.error.HTTPError as exc:
        # 4xx carries a JSON body with Pushover's own explanation
        # (e.g. "application token is invalid", "user key is invalid").
        try:
            errors = json.load(exc).get("errors") or [exc.reason]
        except ValueError:
            errors = [exc.reason]
        raise RuntimeError(f"Pushover rejected the request ({exc.code}): {'; '.join(errors)}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"could not reach api.pushover.net - {exc}") from exc
    if result.get("status") != 1:
        raise RuntimeError(f"Pushover error: {'; '.join(result.get('errors', ['unknown']))}")


def send_unknown_person_alert(image_path, ts):
    _send(
        "Home security: unknown person detected",
        f"An unrecognized person was detected at {ts}.",
        image_path=image_path,
        priority=1,  # high priority: bypasses the user's quiet hours
    )


def latest_snapshot():
    """Newest detection snapshot on disk, or None if there are none yet."""
    try:
        names = [n for n in os.listdir(config.DETECTIONS_DIR) if n.lower().endswith(".jpg")]
    except FileNotFoundError:
        return None
    if not names:
        return None
    return max((os.path.join(config.DETECTIONS_DIR, n) for n in names), key=os.path.getmtime)


def send_test_notification(ts):
    """Attaches the most recent detection snapshot, if any, so the test
    also proves image delivery. Returns the attached file's path or None."""
    image_path = latest_snapshot()
    note = (
        f"Attached: latest detection snapshot ({os.path.basename(image_path)})."
        if image_path else "No detection snapshots yet, so no image is attached."
    )
    _send(
        "Home security: test notification",
        f"This is a test notification from your Kinwatch home security system, sent at {ts}. "
        f"If you received it, Pushover alerts are configured correctly.\n\n{note}",
        image_path=image_path,
    )
    return image_path
