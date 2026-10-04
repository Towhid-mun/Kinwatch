# Camera test

A separate, minimal module from `serial_chat` - just proves the USB
webcam plugged into the Pi is actually capturing real video. Not a
recording or display app; a single JPEG frame is enough evidence.

The webcam shows up as `/dev/video0` (`v4l2-ctl --list-devices` on the
Pi to confirm), and `ffmpeg` is already installed there - no build step,
no new dependency.

## Capture a snapshot

```bash
perch exec sh scripts/capture_snapshot.sh
```

Grabs one MJPEG-native frame (1280x720) straight from the camera's own
hardware encoder into `snapshot.jpg` in the project root on the target.

## View it on the Mac

```bash
perch pull snapshot.jpg
open .perch/artifacts/snapshot.jpg
```

`snapshot.jpg` is deliberately **not** in `.perch.toml`'s `[artifacts]`
auto-pull list - that would make it try to auto-pull on every plain
`perch build`/`perch run` too, which is unrelated to `serial_chat`'s own
workflow. Pull it explicitly instead, only when you actually want it.

Note: `snapshot.jpg` lives inside the mirrored workspace on the target,
so the next sync's mirror-delete step removes it there if a local copy
doesn't exist (it never does, since it's only ever generated on the
target) - re-run the capture script each time rather than expecting it
to persist between runs.
