# Seekara Status Bot

One Discord command: **`!status`** / **`/status`**

Shows only:

```
beacon: online
capsule: offline
seekdesk: online
```

## 1) VPS agent (so capsule/seekdesk are checked via pm2)

```bash
curl -fsSL https://raw.githubusercontent.com/loganstorm1254-sudo/Cursor/cursor/seekara-status-bot-b152/seekara-status/install-agent.sh | sudo bash
sudo ufw allow 5055/tcp
```

## 2) Run the bot

Put your Discord token in `bot.py` as `TOKEN = "..."`, then:

```bash
cd seekara-status
pip install -r requirements.txt
python3 bot.py
```

**Do not commit a real Discord token to GitHub.**
