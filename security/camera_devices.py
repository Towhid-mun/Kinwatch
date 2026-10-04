"""Enumerates actual capture-capable cameras on the Pi via `v4l2-ctl
--list-devices`, filtering out the Broadcom/Raspberry Pi hardware codec
and ISP virtual /dev/video* nodes (bcm2835-codec-decode, bcm2835-isp,
rpi-hevc-dec, bcm2835-codec) that v4l2-ctl lists right alongside real
cameras but that aren't anything an admin would want to pick as a
capture source - confirmed by inspecting this Pi's own `v4l2-ctl
--list-devices` output during development (one real USB webcam, several
of these).
"""
import re
import subprocess

_NON_CAMERA_GROUPS = {"bcm2835-codec-decode", "bcm2835-isp", "rpi-hevc-dec", "bcm2835-codec"}

# Offered on the Camera settings page - not necessarily all supported by
# every device, but common enough across UVC webcams that listing them
# statically (rather than querying and re-querying per selected camera)
# keeps the form simple. An unsupported choice just falls back to
# whatever V4L2/OpenCV pick instead, logged if the camera fails to open.
PIXEL_FORMATS = ["MJPG", "YUYV"]
RESOLUTIONS = ["640x480", "800x600", "1280x720", "1920x1080"]


def list_cameras():
    """Returns [{"path": "/dev/video0", "name": "Wed Camera"}, ...] for
    every real capture-capable camera found, [] if v4l2-ctl isn't
    available or nothing qualifies."""
    try:
        out = subprocess.run(
            ["v4l2-ctl", "--list-devices"], capture_output=True, text=True, timeout=5
        ).stdout
    except (FileNotFoundError, subprocess.SubprocessError):
        return []

    cameras = []
    current_name = None
    for line in out.splitlines():
        if line and not line.startswith((" ", "\t")):
            # e.g. "Wed Camera: Wed Camera (usb-0000:01:00.0-1.1):" -> "Wed Camera"
            # (v4l2-ctl repeats the device's own name before the parens for
            # some USB cameras - collapse "X: X" to just "X" when it does)
            current_name = re.sub(r"\s*\([^)]*\)\s*:?\s*$", "", line).strip()
            parts = current_name.split(": ")
            if len(parts) == 2 and parts[0] == parts[1]:
                current_name = parts[0]
        elif line.strip().startswith("/dev/video"):
            path = line.strip()
            group_key = (current_name or "").split(":")[0].strip()
            if group_key in _NON_CAMERA_GROUPS:
                continue
            if not _is_real_capture_device(path):
                continue
            cameras.append({"path": path, "name": current_name or path})
    return cameras


def _is_real_capture_device(path):
    """A metadata-only node (common for UVC webcams' second /dev/videoN)
    or a codec passthrough won't list MJPG/YUYV - treat those as not a
    selectable camera."""
    try:
        out = subprocess.run(
            ["v4l2-ctl", "-d", path, "--list-formats"], capture_output=True, text=True, timeout=5
        ).stdout
    except (FileNotFoundError, subprocess.SubprocessError):
        return False
    return bool(re.search(r"'(MJPG|YUYV|H264)'", out))
