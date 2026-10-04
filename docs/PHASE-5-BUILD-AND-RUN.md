# Build and run

`serial_chat` is a duplex USB-serial chat tool. The same source
(`src/serial_chat.c`) builds on both ends of the Mac↔Pi USB gadget cable:

- **Pi side** — talks to `/dev/ttyGS0`, built and run remotely via `perch`
  (per this project's `CLAUDE.md`: never build or run locally except where
  noted below).
- **Mac side** — talks to `/dev/cu.usbmodemXXXX`, built and run **locally**
  with `clang`. This is the one deliberate exception to the "never build
  locally" rule: it's the other end of the physical cable, so it has to run
  on the Mac itself.

## One-time setup: USB gadget mode on the Pi

Switches the Pi's USB-C port into peripheral (gadget) mode so the Mac sees
it as a serial device.

```bash
perch exec sudo sh scripts/setup_usb_gadget.sh
```

This edits `/boot/firmware/config.txt` and `/etc/modules`, then **reboots
the Pi**. Wait for it to come back up.

**The Pi 4B has only one USB-C port total** — it does double duty for
power *and* gadget data, there's no separate OTG port. So before
connecting to the Mac, power the Pi another way to free that port:

- **Recommended:** power the Pi from the GPIO header instead (physical
  pin 4 = 5V, pin 6 = GND) from a separate regulated 5V/3A supply, or a
  PoE HAT. Then plug a USB-C cable from the Mac into the now-free port.
- **Quick test:** unplug the wall adapter and plug the Mac↔Pi cable into
  that same port instead — the Pi will boot bus-powered by the Mac. Watch
  for undervoltage (`ssh pi vcgencmd get_throttled`; non-zero means the
  Mac isn't supplying enough current) if you leave it running this way.

Plug the cable **directly into a USB-C port on the Mac**, not through a
hub/dock — and make sure it's a cable with data lines, not a charge-only
one (a common failure with bundled/promotional USB-A↔USB-C cables).

## Pi side (target) — via `perch`

Run from the `my-project` directory in a plain local window — not VS Code
Remote-SSH (see the warning at the top of `.vscode/tasks.json`; if the
window is attached to the target, `perch` would try to SSH from the target
to itself).

1. Sanity-check connectivity/toolchain:
   ```bash
   perch doctor
   ```
2. Build (syncs the workspace, then runs `make` on the target):
   ```bash
   perch build
   ```
3. Run (fresh sync, then `make && ./serial_chat`, listening on
   `/dev/ttyGS0` by default) — **`--tty` is required**: `serial_chat` is
   interactive (reads your typed lines from stdin), and perch's default
   pipe mode runs the remote command with stdin closed (`DEVNULL`) since
   it's built for non-interactive build/test commands. Without `--tty`,
   `serial_chat` starts fine and receives from the Mac, but anything you
   type on the Pi side goes nowhere — it never reaches the process:
   ```bash
   perch run --tty
   ```

Or from VS Code: **Terminal → Run Task →** `perch: build` / `perch: run` /
`perch: doctor`.

## Mac side (host) — local build

1. Find the Pi's gadget serial device once it's plugged in and `g_serial`
   is loaded:
   ```bash
   ls /dev/cu.usbmodem*
   ```
2. Build locally with clang, **into `.perch/`** — it's already excluded
   from the perch sync (see `.perch.toml`'s built-in exclude list), so the
   Mac binary can never collide with the Pi's build of the same file:
   ```bash
   clang -Wall -Wextra -O2 -o .perch/serial_chat src/serial_chat.c
   ```
3. Run, pointing at the device found in step 1:
   ```bash
   ./.perch/serial_chat /dev/cu.usbmodemXXXX
   ```

## Using it

With `perch run --tty` going on the Pi and `./.perch/serial_chat
/dev/cu.usbmodemXXXX` running on the Mac, each side is a duplex chat:
type a line and press Enter in either terminal, it appears in the other.
Type `quit` and press Enter (or Ctrl+D) on either side to exit that side.

## Troubleshooting

**`ls /dev/cu.usbmodem*` finds nothing:**
No cable is actually carrying data between the two machines yet. Check,
in order: (1) is the Pi's USB-C port actually free and connected to the
Mac, not still holding the wall adapter (see the one-time setup section
above — there's only one port); (2) is the cable plugged straight into
the Mac, not through a hub/dock; (3) is the cable data-capable, not
charge-only (try a cable you know syncs a phone, not just charges it).
`system_profiler SPUSBDataType` and `ioreg -p IOUSB -l -w0` on the Mac
will show nothing at all for the Pi if the link isn't up — same
symptom for cable, hub, or missing-power-swap causes, so check the
physical setup end to end rather than assuming a software problem. On
the Pi, confirm the gadget stack is actually bound:
```bash
ssh pi 'lsmod | grep -iE "dwc2|g_serial"; ls -l /dev/ttyGS0'
```

**`./serial_chat` (or the Pi's copy) fails with `Exec format error`:**
A Mac-built Mach-O binary got synced into the Pi's copy of the workspace
and `make` considered it up to date (its mtime is newer than
`src/serial_chat.c`), so the Pi never rebuilt it and then tried to
execute a macOS binary. This happens if the Mac build ever writes its
output as `my-project/serial_chat` instead of `.perch/serial_chat` —
which is exactly why step 2 above builds into `.perch/`. To recover:
```bash
rm serial_chat          # if it exists in the workspace root
perch build             # deletion syncs to the Pi, forces a real rebuild
```

**Only one direction works (Pi→Mac fine, but typing on the Mac never
reaches the Pi):**
Two stacked macOS-specific USB-CDC-ACM quirks, both already fixed in
`open_serial()` in `src/serial_chat.c` — if you're seeing this on a
current checkout, it likely means you're running a stale Mac-side build:

1. `cfmakeraw()` doesn't clear hardware flow control. If `CRTSCTS` is
   set, macOS can hold back writes waiting for a CTS signal a virtual
   gadget-serial link never asserts, while reads are unaffected — fixed
   by explicitly clearing `CRTSCTS` and setting `CLOCAL`.
2. Even with flow control off, a write issued *immediately* after
   opening/reconfiguring the port gets silently dropped — macOS's driver
   needs a brief moment to apply the termios change (baud rate
   especially) over a USB control transfer before the bulk OUT endpoint
   reliably accepts data. Fixed with a short settle delay
   (`usleep(2000000)`) at the end of `open_serial()`, before the main
   loop starts accepting input.

If you still see one-way behavior after rebuilding both sides, rule out
a stale binary first (`file .perch/serial_chat` should show a recent
mtime; `perch build` on the Pi side syncs and rebuilds fresh every time).

**Typing on the Pi side does nothing — including `quit` — but the Pi
still receives fine from the Mac:**
You ran `perch run` without `--tty`. perch's default pipe mode connects
the remote process's stdin to `/dev/null` (it's designed for
non-interactive build/test output, not an interactive program) — your
keystrokes never leave your local terminal, they don't even reach
`serial_chat`. This is not a bug in `serial_chat.c`. Use:
```bash
perch run --tty
```
(the VS Code `perch: run` task already passes `--tty` for this reason).

**`quit` didn't exit the Pi side, even with `--tty`:**
Fixed — `handle_stdin()` used to require an exact `"quit"`/`"quit\n"` byte
match, but a remote pty over `perch run --tty` doesn't always deliver the
same line ending a local terminal would (`\r` vs `\n`). It now trims
trailing `\r`/`\n` before comparing. Rebuild both sides if you're still
on an older binary.

**Using VS Code's integrated terminal (Terminal → Run Task → `perch: run`)
and NOTHING you type registers, on either side:**
Almost always a focus issue, not a bug: the task panel can open/reveal
without actually taking keyboard focus, so keystrokes go to whichever
editor tab is focused instead. Click directly inside the terminal panel
before typing, or rely on the task's `"focus": true` (already set in
`.vscode/tasks.json` for `perch: run`) to grab it automatically. This is
a different failure mode than the `--tty` issue above — no error, no
missing banner, the program is running fine, your keystrokes just never
reach it.

**Testing `--tty` with `perch exec` directly:**
`perch exec --tty <cmd>` takes the command as trailing arguments, not
after a `--` separator — `perch exec --tty -- cat` fails immediately
with `sh: 1: --: not found`, which looks identical to "not taking input"
since the process just exits right away. Use `perch exec --tty cat`.
