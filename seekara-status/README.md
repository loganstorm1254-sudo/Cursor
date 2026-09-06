# Seekara Status Bot

Discord bot that reports which of **beacon**, **capsule**, and **seekdesk** are up or down on `13.140.151.124`.

## 1) Install the status agent on the VPS (reads pm2)

```bash
curl -fsSL https://raw.githubusercontent.com/loganstorm1254-sudo/Cursor/cursor/seekara-status-bot-b152/seekara-status/install-agent.sh | sudo bash
curl http://127.0.0.1:5055/status
```

Opens port **5055**. Firewall: `sudo ufw allow 5055/tcp`

## 2) Run the Discord bot

1. Create a Discord application → Bot → copy token  
   Enable **Message Content Intent**
2. Invite with scopes `bot` + `applications.commands`

```bash
cd seekara-status
python3 -m pip install -r requirements.txt
export SEEKARA_STATUS_TOKEN="YOUR_DISCORD_BOT_TOKEN"
# optional: auto-post every 5 minutes
# export SEEKARA_STATUS_CHANNEL_ID="1234567890"
python3 bot.py
```

Or put the token in `bot.py` as `TOKEN = "..."`.

## Commands

| Command | What it does |
|---------|----------------|
| `!status` / `/status` | Show up/down for beacon, capsule, seekdesk |
| `/seekara` | Same status embed |
| `!pingbots` | Alias for status |

## Notes

- Agent reads `pm2 jlist` for processes named `beacon`, `capsule`, `seekdesk`
- If the agent is down, the bot falls back to Beacon’s `http://13.140.151.124:5000/health`
- Keep the Discord token **out of GitHub**
