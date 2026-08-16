# HTTPS for E.V. via Cloudflare Tunnel

Puts E.V.'s web interface at `https://ev.YOURDOMAIN.com` **without opening any port
on Oracle**. `cloudflared` makes an outbound connection to Cloudflare, which
terminates the TLS and forwards to the local `uvicorn` at `http://localhost:8000`.

This unlocks what requires a "secure context": microphone/voice on the web, real
Picture-in-Picture, browser notifications, and — later — Google/GitHub login.

## Prerequisites (on your side)

1. A **Cloudflare** account (free).
2. A **domain added to Cloudflare** (the domain's nameservers pointing to
   Cloudflare). Cloudflare does **not** give away a free domain — use one you
   already own or register a cheap one. The subdomain (e.g. `ev.`) we create; it
   doesn't need to exist yet.
3. SSH access to the VM (the same one you already use for deploys).

> Without a domain on Cloudflare you can only use the ephemeral `trycloudflare.com`
> tunnels, which generate a random URL on every run — bad for a fixed assistant.
> That's why a domain is required for a stable address.

---

## Step 0 — install cloudflared on the VM

```bash
cd ~/ev && git pull
bash deploy/cloudflared/install.sh
cloudflared --version   # confirm it installed
```

Now pick **one** of the flows below. **Flow A (dashboard)** is the simplest.

---

## Flow A — via the Cloudflare dashboard (recommended)

1. Cloudflare dashboard → **Zero Trust** → **Networks** → **Tunnels** → **Create a tunnel**.
2. Type **Cloudflared**. Give it a name (e.g. `ev`) and **Save**.
3. The screen shows an install command with a long token. On the **Debian/Red Hat**
   tab it suggests installing the package; since we already installed the binary, run
   **only the service part** on the VM (replace `YOUR_TOKEN` with the token shown):

   ```bash
   sudo cloudflared service install YOUR_TOKEN
   sudo systemctl enable --now cloudflared
   systemctl status cloudflared --no-pager
   ```

4. Still in the dashboard, **Public Hostname** tab → **Add a public hostname**:
   - **Subdomain**: `ev`
   - **Domain**: your domain
   - **Type**: `HTTP`
   - **URL**: `localhost:8000`
   - **Save**.

5. Open `https://ev.YOURDOMAIN.com` — it should load E.V. with a valid padlock.

---

## Flow B — via the command line (alternative)

```bash
# 1. Authenticate (opens a URL; open it in your browser and authorize your domain)
cloudflared tunnel login

# 2. Create the tunnel (records a <TUNNEL_ID> and a <TUNNEL_ID>.json file)
cloudflared tunnel create ev

# 3. Move credentials and config to /etc/cloudflared
sudo mkdir -p /etc/cloudflared
sudo cp ~/.cloudflared/*.json /etc/cloudflared/
sudo cp deploy/cloudflared/config.yml.example /etc/cloudflared/config.yml
sudo nano /etc/cloudflared/config.yml   # put in the real TUNNEL_ID and hostname

# 4. Create the DNS record (CNAME) pointing the hostname at the tunnel
cloudflared tunnel route dns ev ev.YOURDOMAIN.com

# 5. Bring it up as a service
sudo cloudflared service install
sudo systemctl enable --now cloudflared
systemctl status cloudflared --no-pager
```

---

## Final step — close the public HTTP (recommended)

Today E.V. web listens on `0.0.0.0:8000`, so `http://IP:8000` is exposed in
cleartext (the token travels without TLS). Once the tunnel is working, force the
app to listen locally only — the tunnel still reaches it via `localhost`:

```bash
cd ~/ev
grep -q '^EV_WEB_HOST=' .env && sed -i 's/^EV_WEB_HOST=.*/EV_WEB_HOST=127.0.0.1/' .env || echo 'EV_WEB_HOST=127.0.0.1' >> .env
sudo systemctl restart ev-web
```

From then on only `https://ev.YOURDOMAIN.com` answers; `http://IP:8000` stops
opening from outside (which is the right thing).

## Quick diagnostics

- `journalctl -u cloudflared -f` — tunnel logs.
- `curl -I http://localhost:8000` on the VM — confirms the app is up locally.
- In the dashboard, the tunnel should show as **HEALTHY**.
</content>
