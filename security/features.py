"""Developer-facing feature toggles. Edit and redeploy (perch build/exec)
to take effect - distinct from:
  - security/.env       target-only secrets (admin password, email/Pushover creds)
  - the /settings page   end-user runtime preferences (alert email,
                          detection tuning), stored in security.db,
                          editable from the browser without a redeploy

These are build-time/deployment-time switches, not something an end user
flips day to day.
"""

# Master switch for security/activity.log and the Logs page's Activity
# log section. False disables the file (and that section shows as
# disabled) but both processes still print to stderr either way - this
# only controls persistence/web visibility, not live terminal output.
ENABLE_ACTIVITY_LOG = True

# Hard kill switch for the email-alert feature. False disables it
# completely regardless of the admin's /settings checkbox or configured
# alert_email - use this to ship a build where email is off no matter
# what an admin later configures through the web UI.
ENABLE_EMAIL_ALERTS = True

# Same as ENABLE_EMAIL_ALERTS, for Pushover push notifications.
ENABLE_PUSHOVER_ALERTS = True

# Whether scripts/setup_autostart.sh ENABLES (vs. merely installs) the
# security-monitor/security-web systemd units, i.e. whether they start
# automatically on boot - including after the admin panel's "Reboot
# system" control. False installs the units disabled, for a dev checkout
# you don't want auto-fighting a manually-run monitor.py over the camera.
AUTO_START_ON_BOOT = True

# Whether the admin panel exposes the "Reboot system" control at all.
# False hides the button and refuses the route server-side, not just
# client-side.
ENABLE_REBOOT_CONTROL = True
