# Remote access via Cloudflare Tunnel

Reach your JobApply dashboard (and the ntfy approval links) from outside
your home network, with no port-forwarding and no public IP exposure.
`cloudflared` makes an outbound-only connection from your machine to
Cloudflare's edge; nothing needs to be opened on your router/firewall.

## Prerequisites

- A domain already added to your Cloudflare account (Cloudflare is that
  domain's DNS provider).
- JobApply already running locally, e.g. `python -m jobapply.cli serve`
  on port 8000.

## 1. Install cloudflared

- **Debian/Ubuntu**:
  ```bash
  curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
  sudo dpkg -i cloudflared.deb
  ```
- **macOS**: `brew install cloudflare/cloudflare/cloudflared`
- **Other platforms**: see [Cloudflare's install docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).

## 2. Authenticate and create a tunnel

```bash
cloudflared tunnel login          # opens a browser, pick your domain
cloudflared tunnel create jobapply
```

Note the tunnel ID it prints - it also writes a credentials file to
`~/.cloudflared/<tunnel-id>.json`.

## 3. Route a subdomain to the tunnel

```bash
cloudflared tunnel route dns jobapply jobapply.yourdomain.com
```

This creates the CNAME record in Cloudflare DNS for you.

## 4. Configure ingress

Create `~/.cloudflared/config.yml`:

```yaml
tunnel: jobapply
credentials-file: /home/YOUR_USER/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: jobapply.yourdomain.com
    service: http://localhost:8000
  - service: http_status:404
```

## 5. Run it

Test first:

```bash
cloudflared tunnel run jobapply
```

If `https://jobapply.yourdomain.com` loads JobApply's `/setup` or login
page, install it as a persistent service so it survives reboots:

```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
```

(macOS: `sudo cloudflared service install` registers a launchd service.)

## 6. Optional but recommended: Cloudflare Access

JobApply already has its own password login, so this is optional - but
without it, that login page is directly internet-facing (bots will find
it and hammer it). Cloudflare Access adds a second gate at Cloudflare's
edge, free for personal use, so unauthenticated requests never even reach
your server:

1. Open the [Zero Trust dashboard](https://one.dash.cloudflare.com/) → **Access → Applications → Add an application → Self-hosted**.
2. Application domain: `jobapply.yourdomain.com`.
3. Add a policy - simplest option: **Include → Emails →** your email address. Visitors verify via a one-time code sent to that email, no separate password to manage.
4. Save.

Skip this step if you'd rather rely solely on JobApply's own login -
just know the login page will be reachable by anyone who finds the URL,
not just you.

## 7. Point JobApply at the public hostname

In the dashboard: **Settings → Schedule & dashboard → Dashboard base URL**
→ set to `https://jobapply.yourdomain.com` → Save.

Then **restart JobApply** (`python -m jobapply.cli serve` again, or
restart its service). This matters: the session cookie's `Secure` flag is
only read once at startup from `dashboard.base_url` - restarting is what
makes the cookie HTTPS-only, appropriate now that it's reachable
publicly.

## 8. Test from outside your network

From your phone on cellular data (not your home WiFi), visit
`https://jobapply.yourdomain.com`. You should hit Cloudflare Access first
(if you set it up), then JobApply's own login.

## Turning it off

Stop the tunnel service (`sudo systemctl stop cloudflared`) any time -
JobApply stays reachable on your LAN as before, it just won't be public
anymore.
