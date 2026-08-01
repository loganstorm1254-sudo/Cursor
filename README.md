# Cursor bots + Android apps

## Seekara app (Android)

Branded Android app for [seekara.pt](https://www.seekara.pt/): splash screen, in-app browsing with pull-to-refresh, offline screen with retry, and external links opening in the phone's browser.

- Source: [`Seekara/`](Seekara/)
- Ready APK: [`releases/Seekara.apk`](releases/Seekara.apk) (Android 8+)

## Notify apps (Android, Bluetooth)

Two apps that send phone notifications over **Bluetooth** — no Wi‑Fi, data, hotspot, or IPs.

| App | Folder | Role |
|-----|--------|------|
| **Notify Sender** | `NotifySender/` | Links once, then sends notifications |
| **Notify Receiver** | `NotifyReceiver/` | Listens and shows the system notification |

Ready APKs: [`releases/`](releases/) · Protocol: [`shared/PROTOCOL.md`](shared/PROTOCOL.md)

### Quick start

1. Install `releases/NotifyReceiver.apk` on phone A, `releases/NotifySender.apk` on phone B.
2. Bluetooth **ON** on both. Keep them near each other.
3. Phone A: **Notify Receiver** → allow permissions → **Start**.
4. Phone B: **Link receiver** once → type a message → **Send**.

---

## `bot.py` — general Discord AI bot
Chat, image recognition, image generation (free AI via g4f).

```bash
pip install discord.py g4f
python bot.py
```

## `bot2.py` — HTML website generator (one file)
Turns a description into HTML. Replies with a downloadable `.html` file only (no code in chat).

Uses **free unlimited AI** (no paid credits): g4f model rotation + Pollinations anonymous failover. Includes moderation (no porn/NSFW, CSAM, gore, scams, hate, illegal shops).

```bash
pip install discord.py g4f aiohttp
python bot2.py
```

1. Create a bot at [Discord Developer Portal](https://discord.com/developers/applications)
2. Enable **Message Content Intent**
3. Put the token in `TOKEN = "..."` inside the file (or `export DISCORD_TOKEN=...`)
4. Invite with scopes `bot` + `applications.commands` (Send Messages + Attach Files)

Commands: `!html <description>` / `/html` / `@Bot <description>`

**Continue editing:** reply to the bot message that has the `.html` file and describe your changes (e.g. `make it darker and add a pricing section`). You can also use `!html …` as a reply to that file message.
