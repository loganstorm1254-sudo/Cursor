# Cursor bots

## `bot.py` — general Discord AI bot
Chat, image recognition, image generation (free AI via g4f).

```bash
pip install discord.py g4f
python bot.py
```

## `bot2.py` — HTML website generator (one file)
Turns a description into HTML. Replies with **source code in chat** + a downloadable `.html` file. Free AI via g4f. HTML only.

```bash
pip install discord.py g4f aiohttp
python bot2.py
```

1. Create a bot at [Discord Developer Portal](https://discord.com/developers/applications)
2. Enable **Message Content Intent**
3. Put the token in `TOKEN = "..."` inside the file (or `export DISCORD_TOKEN=...`)
4. Invite with scopes `bot` + `applications.commands` (Send Messages + Attach Files)

Commands: `!html <description>` / `/html` / `@Bot <description>`
