# Beacon Console (Vercel)

Read-only remote console for the Discord bot you run on your server PC (`smmod.py` / exe).

- **Website (Vercel):** login with a username/password → black console that mirrors the CMD window
- **PC bridge:** sets that username/password, runs your bot, and streams stdout/stderr to Vercel
- **No typing on the website** — view logs only, no remote shell / no full access

```
Server PC (CMD)                     Vercel                          Your phone/laptop
py smmod.py  ──bridge──push logs──▶  /api/push  ──store──▶  /console (read-only view)
                 claim user/pass──▶  /api/claim             / login
```

## Downloads

| File | What |
|------|------|
| [`releases/BotConsole-Vercel.zip`](../releases/BotConsole-Vercel.zip) | Website pack for Vercel |
| [`releases/BeaconConsoleBridge-Windows.zip`](../releases/BeaconConsoleBridge-Windows.zip) | Windows bridge (`BeaconConsoleBridge.exe`) |

## 1. Deploy the website to Vercel

1. Push this repo (or import `BotConsole/` as the project root).
2. In Vercel: **Add New Project** → select this repo → set **Root Directory** to `BotConsole`.
3. Environment variables (Project → Settings → Environment Variables):

| Name | Required | Notes |
|------|----------|--------|
| `SESSION_SECRET` | yes | Long random string (cookie signing) |
| `CONSOLE_RESET_SECRET` | optional | Emergency reclaim password |
| `UPSTASH_REDIS_REST_URL` | recommended | Free Upstash Redis REST URL |
| `UPSTASH_REDIS_REST_TOKEN` | recommended | Free Upstash Redis REST token |

Without Upstash, logs live in memory on one serverless instance and can reset on cold starts. For a personal bot, add free Redis from [upstash.com](https://upstash.com) (create Redis DB → copy REST URL + token into Vercel).

4. Deploy. Copy your URL, e.g. `https://beacon-console.vercel.app`.

## 2. Run the bridge on your server PC

On the same PC where you normally run `py smmod.py`:

1. Copy the `BotConsole/agent/` folder to the PC (next to `smmod.py` is ideal).
2. Double-click **`bridge.bat`** (or `py bridge.py`).
3. Enter:
   - Website URL
   - Username
   - Password
   - Command (default `py smmod.py` — or your `.exe` path)
4. Leave that window open. It prints the same bot output locally **and** streams it to the website.

Config is saved as `bridge_config.json` next to `bridge.py` (gitignored).

### Examples

```bat
bridge.bat
py bridge.py --cmd "py smmod.py"
py bridge.py --cmd "C:\bots\Beacon.exe"
py bridge.py --setup
```

## 3. Open the console from anywhere

1. Visit your Vercel URL
2. Log in with the **same** username/password you set on the PC
3. Watch the live mirror — **read only**

## API (for the bridge)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/claim` | Set/confirm username + password from the PC |
| POST | `/api/push` | Append console lines (agent token) |
| POST | `/api/heartbeat` | Keep LIVE status green |
| POST | `/api/login` | Browser login |
| GET | `/api/logs` | Browser poll (session cookie) |
| GET | `/api/status` | Claimed / online flags |

## Security notes

- Website cannot type into the bot or open a shell — push is one-way from the PC.
- Use a strong password; anyone with it can **view** bot logs.
- Prefer HTTPS Vercel URLs only.
- Rotate `SESSION_SECRET` if you suspect cookie theft (logs out everyone).
