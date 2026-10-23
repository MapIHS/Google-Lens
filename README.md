## Installation

1. Copy the current Hararest `.browser_profile` directory into this project's `profile/` directory. This profile stays on the VPS and is excluded from Git and the container image.
2. Give the profile to container UID 10001: `sudo chown -R 10001:10001 profile`.
3. Copy `.env.example` to `.env` and set the worker token. Set the Tunnel token only when using the bundled `cloudflared` service.
4. Start the worker with `docker compose up -d --build google-lens-worker`. The worker's VNC page is available at `http://100.90.124.33:6080` on the VPS Tailscale address so Google verification can be completed in the same browser profile.
5. For a `cloudflared` service running on the VPS host, configure its published application route to `http://localhost:8787`. For the bundled Compose `cloudflared` service, route to `http://google-lens-worker:8787`.
6. Protect the public hostname with a Cloudflare Access application and a Service Auth policy. Set Hararest's `GOOGLE_LENS_WORKER_URL` to that hostname, `GOOGLE_LENS_WORKER_TOKEN` to the same worker token, and `CLOUDFLARE_ACCESS_CLIENT_ID` / `CLOUDFLARE_ACCESS_CLIENT_SECRET` to the Access service token.

## Environment

| Variable | Description |
| --- | --- |
| `GOOGLE_LENS_WORKER_TOKEN` | Bearer token required by the HTTP endpoint. |
| `GOOGLE_LENS_PROFILE_HOST_PATH` | Persistent host directory for the Chromium profile. |
| `GOOGLE_LENS_VNC_PASSWORD` | Password for the worker's VNC browser session. |
| `CLOUDFLARE_TUNNEL_TOKEN` | Token for the named Cloudflare Tunnel. |
