# Cursor bots + Wi‑Fi Notify apps

## Wi‑Fi Notify (Android)

Two apps that talk **only over your local Wi‑Fi** — no internet, no accounts.

| App | Folder | Role |
|-----|--------|------|
| **Notify Sender** | `NotifySender/` | Finds receivers and sends a notification |
| **Notify Receiver** | `NotifyReceiver/` | Listens and shows the system notification |

Protocol details: [`shared/PROTOCOL.md`](shared/PROTOCOL.md)

### Quick start

1. Open each folder in Android Studio and install on two phones.
2. Put both phones on the same Wi‑Fi.
3. On the receiver phone: open **Notify Receiver** → **Start** (allow notifications).
4. On the sender phone: **Find receivers** → pick the other phone → send.

> Some guest/public Wi‑Fi networks block phone-to-phone traffic (AP/client isolation). Use a normal home/office network if discovery fails.

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
