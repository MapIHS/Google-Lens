#!/bin/sh
set -eu

: "${VNC_PASSWORD:?VNC_PASSWORD is required}"
x11vnc -storepasswd "$VNC_PASSWORD" /tmp/vnc-pass >/dev/null
chmod 600 /tmp/vnc-pass

export DISPLAY=:99
Xvfb "$DISPLAY" -screen 0 1366x900x24 -nolisten tcp -ac &
sleep 1
x11vnc -display "$DISPLAY" -rfbport 5900 -rfbauth /tmp/vnc-pass \
    -localhost -forever -shared -quiet &
websockify --web=/usr/share/novnc 6080 127.0.0.1:5900 &

exec uvicorn worker:app --host 0.0.0.0 --port 8787 --workers 1
