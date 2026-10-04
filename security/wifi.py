"""Wi-Fi management via NetworkManager (nmcli). This Pi's only network
path is wlan0 - no Ethernet fallback - so a bad SSID/password would
otherwise strand it, reachable only with a monitor and keyboard plugged
directly in. Every change is verified synchronously (nmcli's own --wait
blocks until success or failure is known, typically within seconds for a
wrong password) and automatically reverted to whatever was working
before on any failure - never applied and just hoped for.

Modifying commands run as root (`sudo -n`) rather than as the app's own
user - NetworkManager's default polkit policy for a user managing their
own Wi-Fi connections typically requires an active logind session, which
a systemd service (no login, no seat) doesn't have, so unprivileged
nmcli calls can fail there even though the same command works fine from
an interactive terminal. Root sidesteps that. This relies on the sudo
access already present on this machine - narrowly scoping to an exact
nmcli invocation isn't practical here since the arguments (SSID,
password) are inherently variable.
"""
import subprocess

CONNECT_TIMEOUT_SECONDS = 25


def current_connection():
    """Returns (interface, connection_name) for the active Wi-Fi link,
    or (None, None) if not connected via Wi-Fi. connection_name is what
    change_wifi() reverts to on failure."""
    out = subprocess.run(
        ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"],
        capture_output=True, text=True, timeout=10,
    ).stdout
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 4 and parts[1] == "wifi" and parts[2] == "connected":
            return parts[0], parts[3]
    return None, None


def scan_networks(interface):
    """Returns nearby networks as [{"ssid", "signal" (0-100), "security"}],
    deduplicated by SSID (strongest signal wins), strongest first."""
    subprocess.run(["nmcli", "device", "wifi", "rescan", "ifname", interface], capture_output=True, timeout=10)
    out = subprocess.run(
        ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list", "ifname", interface],
        capture_output=True, text=True, timeout=15,
    ).stdout
    best = {}
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) < 3 or not parts[0]:
            continue
        ssid, signal_raw, security = parts[0], parts[1], parts[2]
        try:
            signal = int(signal_raw)
        except ValueError:
            signal = 0
        if ssid not in best or signal > best[ssid]["signal"]:
            best[ssid] = {"ssid": ssid, "signal": signal, "security": security or "open"}
    return sorted(best.values(), key=lambda n: -n["signal"])


def change_wifi(ssid, password, interface="wlan0"):
    """Connects to a new network, verifying it actually works before
    committing - reverts to whatever was active before on any failure.
    Returns (ok, message). Blocks for up to ~2x CONNECT_TIMEOUT_SECONDS
    (the failed attempt, then the revert) - call from a background
    thread, not the request thread, since the connection carrying that
    HTTP request may itself be the one about to change.
    """
    _, previous = current_connection()

    new_profile = f"security-wifi-{ssid}"
    subprocess.run(["sudo", "-n", "nmcli", "connection", "delete", new_profile], capture_output=True)  # clear any stale attempt with this name

    create = subprocess.run(
        [
            "sudo", "-n", "nmcli", "connection", "add", "type", "wifi", "ifname", interface,
            "con-name", new_profile, "ssid", ssid,
            "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", password,
        ],
        capture_output=True, text=True, timeout=10,
    )
    if create.returncode != 0:
        return False, f"could not create connection profile: {create.stderr.strip()}"

    up = subprocess.run(
        ["sudo", "-n", "nmcli", "connection", "up", new_profile, "--wait", str(CONNECT_TIMEOUT_SECONDS)],
        capture_output=True, text=True, timeout=CONNECT_TIMEOUT_SECONDS + 10,
    )
    if up.returncode == 0:
        return True, f"connected to {ssid!r}"

    # Failed - drop the bad profile and get back on the known-good network.
    subprocess.run(["sudo", "-n", "nmcli", "connection", "down", new_profile], capture_output=True, timeout=10)
    subprocess.run(["sudo", "-n", "nmcli", "connection", "delete", new_profile], capture_output=True, timeout=10)

    reverted = "no previous connection recorded to revert to"
    if previous:
        revert = subprocess.run(
            ["sudo", "-n", "nmcli", "connection", "up", previous, "--wait", str(CONNECT_TIMEOUT_SECONDS)],
            capture_output=True, text=True, timeout=CONNECT_TIMEOUT_SECONDS + 10,
        )
        reverted = f"reverted to {previous!r}" if revert.returncode == 0 else f"FAILED to revert to {previous!r} too: {revert.stderr.strip()}"

    failure_detail = up.stderr.strip() or up.stdout.strip()
    return False, f"could not connect to {ssid!r}: {failure_detail} - {reverted}"
