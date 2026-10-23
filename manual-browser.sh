#!/bin/sh
set -eu

: "${VNC_PASSWORD:?VNC_PASSWORD is required}"
mkdir -p /tmp/manual-browser
x11vnc -storepasswd "$VNC_PASSWORD" /tmp/manual-browser/vnc-pass >/dev/null
chmod 600 /tmp/manual-browser/vnc-pass
# The worker is stopped before this service starts. Remove Chromium's stale
# singleton links left behind if its previous container was closed abruptly.
rm -f "$GOOGLE_LENS_PROFILE_DIR"/SingletonCookie \
    "$GOOGLE_LENS_PROFILE_DIR"/SingletonLock \
    "$GOOGLE_LENS_PROFILE_DIR"/SingletonSocket

export DISPLAY=:99
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99
Xvfb "$DISPLAY" -screen 0 1366x900x24 -nolisten tcp -ac &
XVFB_PID=$!
cleanup() {
    kill "$BROWSER_PID" 2>/dev/null || true
    wait "$BROWSER_PID" 2>/dev/null || true
    rm -f "$GOOGLE_LENS_PROFILE_DIR"/.manual-browser-active \
        "$GOOGLE_LENS_PROFILE_DIR"/SingletonCookie \
        "$GOOGLE_LENS_PROFILE_DIR"/SingletonLock \
        "$GOOGLE_LENS_PROFILE_DIR"/SingletonSocket
    kill "$NOVNC_PID" "$VNC_PID" "$XVFB_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

sleep 1
x11vnc -display "$DISPLAY" -rfbport 5900 -rfbauth /tmp/manual-browser/vnc-pass -localhost -forever -shared -quiet &
VNC_PID=$!
websockify --web=/usr/share/novnc 6080 127.0.0.1:5900 &
NOVNC_PID=$!
sleep 2
: > "$GOOGLE_LENS_PROFILE_DIR/.manual-browser-active"

/usr/bin/chromium \
    --no-sandbox \
    --disable-dev-shm-usage \
    --user-data-dir="$GOOGLE_LENS_PROFILE_DIR" \
    --no-first-run \
    --no-default-browser-check \
    --new-window https://lens.google.com/ &
BROWSER_PID=$!
wait "$BROWSER_PID" || true
echo "Chromium closed; the profile has been saved and noVNC remains available."
while :; do sleep 3600; done
