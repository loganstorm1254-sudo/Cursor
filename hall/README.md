# Hall

Hall is a Discord-style chat app that runs on Cloudflare. People claim a username and talk in servers and text channels. Every username is free. **`@admin` and `@owner` are reserved** and cannot be registered. Those names are not secret logins and do not grant extra powers.

## What it runs on

- **Workers** serves the app and the API.
- **Workers Static Assets** serves the browser client.
- **D1** stores accounts, sessions, servers, channels, and memberships.
- **Durable Objects** (one SQLite object per channel) store messages and fan them out over hibernating WebSockets.

## Local

```bash
cd hall
npm install
npm test
npm run dev
```

Open the URL Wrangler prints (usually `http://localhost:8787`). Create an account, land in **Lobby** (invite `hall`), and talk in `#general`.

The Worker creates tables on first use, so local dev works before you apply migrations. `npm run db:migrate:local` applies `migrations/` to the local D1 database as well.

## Deploy

1. `npx wrangler login`
2. `npx wrangler d1 create hall` (skip if you already have the `hall` database)
3. Put the printed database id in `wrangler.jsonc` as `database_id`
4. `npx wrangler r2 bucket create hall-avatars`
5. Set the owner login password (creates/updates **Rogue1254**):

```bash
npx wrangler secret put OWNER_PASSWORD
```

6. `npm run db:migrate:remote`
7. `npm run deploy`

Sign in as **Rogue1254** with the password you put in `OWNER_PASSWORD`.

The first request also creates the Lobby server if it is missing, so a brand-new database still comes up with `#general`, `#random`, and invite code `hall`.

Everyone can set a **bio** and **profile photo** from Profile in the app.

Logs and traces are turned on in `wrangler.jsonc`. Trace sampling is 1%.
