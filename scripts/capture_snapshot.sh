#!/bin/sh
# Grabs one JPEG frame from the USB webcam at /dev/video0, to prove the
# camera is actually capturing real video (not full recording/display -
# that's out of scope here, this is just a functional check).
#
# Run via: perch exec sh scripts/capture_snapshot.sh
# Then pull it to the Mac: perch pull snapshot.jpg
# (not in [artifacts] in .perch.toml - kept separate from the serial_chat
# build/run flow, pull it explicitly when you want it)
set -e

ffmpeg -y -f v4l2 -input_format mjpeg -video_size 1280x720 \
    -i /dev/video0 -frames:v 1 -update 1 -q:v 2 snapshot.jpg

echo "wrote snapshot.jpg"
