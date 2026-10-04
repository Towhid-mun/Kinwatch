#!/bin/sh
# One-time setup: switch the Pi4's USB-C controller (dwc2) into peripheral
# mode and load the g_serial gadget driver, so the Mac sees the Pi as a
# USB serial device (CDC-ACM) over the same USB-C cable.
#
# Run once via: perch exec sudo sh scripts/setup_usb_gadget.sh
# Requires a reboot to take effect (the script reboots at the end).
set -e

CONFIG=/boot/firmware/config.txt
MODULES=/etc/modules

if ! grep -qxF 'dtoverlay=dwc2,dr_mode=peripheral' "$CONFIG"; then
    cp "$CONFIG" "$CONFIG.bak.$(date +%s)"
    printf '\n# USB gadget mode for Mac<->Pi communication\ndtoverlay=dwc2,dr_mode=peripheral\n' >> "$CONFIG"
    echo "added dwc2 peripheral overlay to $CONFIG"
else
    echo "dwc2 peripheral overlay already present in $CONFIG"
fi

cp "$MODULES" "$MODULES.bak.$(date +%s)" 2>/dev/null || true
for mod in dwc2 g_serial; do
    if ! grep -qxF "$mod" "$MODULES"; then
        echo "$mod" >> "$MODULES"
        echo "added $mod to $MODULES"
    else
        echo "$mod already in $MODULES"
    fi
done

echo "rebooting to apply changes..."
reboot
