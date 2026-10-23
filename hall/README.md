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
2. `npx wrangler d1 create hall`
3. Put the printed database id in `wrangler.jsonc` as `database_id`.
4. `npm run db:migrate:remote`
5. `npm run deploy`

The first request also creates the Lobby server if it is missing, so a brand-new database still comes up with `#general`, `#random`, and invite code `hall`.

Logs and traces are turned on in `wrangler.jsonc`. Trace sampling is 1%.
