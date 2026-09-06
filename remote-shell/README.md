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

From a local checkout instead:

```bash
cd remote-shell
sudo bash install.sh
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

```bash
cd remote-shell/web
npm install
npx vercel
```

Or in the Vercel dashboard: **Import** this GitHub repo and set **Root Directory** to `remote-shell/web`.

## 3) Use it

1. Open the Vercel site
2. Agent URL: `http://YOUR.VPS.IP:7788`
3. **Set PIN** once (or use `beacon-remote pin-set` on the server)
4. Enter PIN → **Open terminal**

PIN is sent only for that request, then cleared from the page. Nothing is written to localStorage.

## Security

- Treat the PIN like a root password
- Prefer HTTPS reverse proxy (Caddy/Nginx) in front of 7788
- Auth is rate-limited on the agent
- First-time Set PIN from the site only works when no PIN exists yet; changing later needs the current PIN
