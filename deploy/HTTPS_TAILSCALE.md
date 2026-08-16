# Private HTTPS for E.V. via Tailscale Serve

Puts E.V.'s web interface at `https://<machine>.<your-tailnet>.ts.net`, with a
valid TLS certificate, **no domain, no cost, and no open ports on Oracle**.

**Serve** mode (private): E.V. only answers **your own devices** logged into your
Tailscale (phone + PC). It never reaches the public internet — this is the most
secure option. (The public mode would be `funnel`; here we use `serve` on purpose.)

This unlocks what requires a "secure context": microphone/voice on the web, real
Picture-in-Picture, browser notifications, and — later — Google/GitHub login.

## Prerequisites (on your side)

1. A free **Tailscale** account (log in with Google/GitHub/email) — https://tailscale.com
2. The **Tailscale** app installed on every device of yours that will open E.V.
   (iOS/Android phone + laptop). In private mode, the device must be on your
   tailnet to reach the `.ts.net` URL.
3. SSH access to the VM (the same one you already use for deploys).

---

## Step 1 — install and connect Tailscale on the VM

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

`tailscale up` prints a URL — open it in your browser, log in, and authorize this
machine.

Confirm the machine name and your tailnet name (they make up the URL):

```bash
tailscale status
```

## Step 2 — enable HTTPS on the tailnet (once, in the web panel)

In the admin console (https://login.tailscale.com/admin/dns):
- Enable **MagicDNS**.
- Enable **HTTPS Certificates** (required for the `*.ts.net` certificate).

## Step 3 — serve E.V. (private)

```bash
# Current form (recent Tailscale): publishes https -> localhost:8000, in the background
sudo tailscale serve --bg 8000

# If the command above complains about the syntax, check your version's options:
tailscale serve --help
# Alternative on slightly older versions:
#   sudo tailscale serve https / http://127.0.0.1:8000

# See what's published and the exact URL:
tailscale serve status
```

The final URL is `https://<machine-name>.<your-tailnet>.ts.net` (shown by
`tailscale serve status` / `tailscale status`).

## Step 4 — install Tailscale on your devices

- **Phone**: Tailscale app (iOS/Android) → log in with the SAME account → turn on.
- **PC**: Tailscale desktop app → log in → turn on.

With Tailscale on the device, open the `.ts.net` URL in the browser. Since it's now
real HTTPS, microphone/voice, PiP and notifications start working.

## Step 5 — close the public HTTP (recommended)

Today E.V. web listens on `0.0.0.0:8000`, so `http://IP:8000` is exposed in
cleartext (the token travels without TLS). Once Serve is working, force the app to
listen locally only — Tailscale still reaches it via `localhost`:

```bash
cd ~/ev
grep -q '^EV_WEB_HOST=' .env && sed -i 's/^EV_WEB_HOST=.*/EV_WEB_HOST=127.0.0.1/' .env || echo 'EV_WEB_HOST=127.0.0.1' >> .env
sudo systemctl restart ev-web
```

From then on only the `.ts.net` URL (from your devices) answers; `http://IP:8000`
stops opening from outside.

## Quick diagnostics

- `tailscale serve status` — what is being served and the URL.
- `sudo tailscale status` — tailnet machines and connectivity.
- `curl -I http://localhost:8000` on the VM — confirms the app is up locally.
- `journalctl -u tailscaled -f` — Tailscale logs.
</content>
</invoke>
