# HTML Website Discord Bot

Discord bot that turns a text description into a **complete single-file HTML website**. Free AI via [g4f](https://github.com/xtekky/gpt4free) — no OpenAI key.

It only generates HTML. It will not chat, write other languages, or do image gen.

## Setup

```bash
pip install -r requirements.txt
```

1. Create a bot at [Discord Developer Portal](https://discord.com/developers/applications)
2. Enable **Message Content Intent** (Bot → Privileged Gateway Intents)
3. Invite with scopes `bot` + `applications.commands` (needs Send Messages + Attach Files)
4. Put the token in `bot.py` as `TOKEN = "..."`, or:

```bash
export DISCORD_TOKEN="your-token"
python bot.py
```

## Commands

| Command | What it does |
|---------|----------------|
| `!html <description>` | Generate an `.html` website file |
| `/html <description>` | Same, as a slash command |
| `@Bot <description>` | Same via mention |
| `!help` | Show help |

**Examples**

```
!html a portfolio for a photographer with a dark theme and image gallery
!html landing page for a coffee shop, warm colors, menu section
!website minimal personal blog about hiking
```

Download the attached `.html` file and open it in a browser.

## Notes

- Free AI providers can be slow or flaky; the bot retries a few times.
- Output is one self-contained HTML file (CSS/JS inline).
- Owner commands: `!off` / `!on` / `!status` (your Discord user id is set as owner in `bot.py`).
