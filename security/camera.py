"""Opens cameras according to the admin's Camera settings - shared by
app.py's /stream.mjpg (CamView and Capture) and monitor.py, so all three
actually use what's configured rather than each hardcoding its own.

Multi-camera: the admin picks specific cameras, or "all" - selected_devices()
resolves that to concrete paths, re-checking actual detected hardware each
call for "all" so a reconnected/renumbered camera is picked up without
needing to reselect it. Pixel format and resolution are shared across every
active camera (not configured per-camera) - kept simple deliberately.
"""
import cv2

import camera_devices
import config
import db


def selected_devices():
    """Returns the list of device paths that should be active everywhere
    (CamView, Capture, the monitor). Falls back to config.CAMERA_DEVICE,
    identical to single-camera behavior, if nothing's been configured yet."""
    raw = db.get_setting("camera_devices", "")
    if raw == "all":
        paths = [cam["path"] for cam in camera_devices.list_cameras()]
        return paths or [config.CAMERA_DEVICE]
    if raw:
        paths = [p.strip() for p in raw.split(",") if p.strip()]
        if paths:
            return paths
    return [config.CAMERA_DEVICE]


def open_camera(device):
    pixel_format = db.get_setting("camera_pixel_format", "")
    resolution = db.get_setting("camera_resolution", "")

    cap = cv2.VideoCapture(device)
    if pixel_format:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*pixel_format))
    if resolution and "x" in resolution:
        width, _, height = resolution.partition("x")
        try:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(width))
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(height))
        except ValueError:
            pass  # a bad stored value shouldn't crash camera open - just skip it
    return cap
