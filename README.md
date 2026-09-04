# Beacon Console

Read-only remote console for your Discord bot server PC. Deploy this repo to **Vercel**, then run `BeaconConsoleBridge.exe` on the PC.

## Deploy on Vercel

1. Import this GitHub repo in [Vercel](https://vercel.com/new)
2. Framework: **Next.js** (auto)
3. Add environment variable:
   - `SESSION_SECRET` = any long random string
4. Optional (recommended): free Upstash Redis
   - `UPSTASH_REDIS_REST_URL`
   - `UPSTASH_REDIS_REST_TOKEN`
5. Deploy → copy your `https://….vercel.app` URL

## PC bridge

On your server PC, unzip `BeaconConsoleBridge-Windows.zip` from the main Cursor releases, run **BeaconConsoleBridge.exe**, enter the Vercel URL + username/password + `py smmod.py` (or your bot exe).

Website is **view-only** — no typing, no remote shell.

## Local dev

```bash
npm install
cp .env.example .env.local   # set SESSION_SECRET
npm run dev
```
