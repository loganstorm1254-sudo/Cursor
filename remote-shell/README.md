# Beacon Remote Shell

Browser remote terminal for your Ubuntu VPS.

- PIN is stored **only on the Ubuntu server** (PBKDF2 hash)
- Vercel site **never saves** the PIN (no cookies / localStorage)
- After PIN auth you get a live shell over WebSocket

## 1) Install agent on Ubuntu (one-liner)

```bash
curl -fsSL https://raw.githubusercontent.com/loganstorm1254-sudo/Cursor/cursor/remote-shell-b152/remote-shell/install.sh | sudo bash
sudo beacon-remote pin-set
```

Check it:

```bash
systemctl status beacon-remote
curl http://127.0.0.1:7788/health
```

Default port: **7788**  
Firewall: `sudo ufw allow 7788/tcp`

## 2) Deploy website to Vercel

Upload `remote-shell/beacon-remote-web.zip`, or set Root Directory to `remote-shell/web`.

## 3) Use it

1. Open the site
2. Agent URL: `http://YOUR.VPS.IP:7788`
3. Enter the PIN you set with `beacon-remote pin-set`
4. Open terminal

**Important:** a HTTPS Vercel site cannot talk to a plain `http://IP:7788` agent (browser blocks it). Either:
- put HTTPS in front of the agent (Caddy/Nginx), or
- open an HTTP page that can reach the agent

## Security

- Treat the PIN like a root password
- Prefer HTTPS reverse proxy in front of 7788
- Auth is rate-limited on the agent
- Change PIN only on the server: `sudo beacon-remote pin-set`
