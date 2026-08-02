# Cursor bots + Wi‑Fi Notify apps

## Nova — your own AI (Android, offline, trained from scratch)

A **5.9M-parameter GPT transformer trained from zero** just for you. The
neural network lives inside the APK, AES-256 encrypted, and only unlocks with
your **master API key** (see [`NovaAI/MASTER_KEY.txt`](NovaAI/MASTER_KEY.txt) —
short key `sk-nova-m00ny4xe` also works).
Anything beyond her training ("what is a black hole?") is answered live from
**Wikipedia**; without internet she still works fully offline.

Project: [`NovaAI/`](NovaAI/) · Ready APK: [`releases/NovaAI.apk`](releases/NovaAI.apk) · Windows: [`releases/NovaAI-Windows.zip`](releases/NovaAI-Windows.zip) · Full docs: [`NovaAI/README.md`](NovaAI/README.md)

### Quick start (Android)

1. Install `releases/NovaAI.apk`.
2. Open **Nova AI** and paste a master API key from `NovaAI/MASTER_KEY.txt`
   (easiest: `sk-nova-m00ny4xe`).
3. Chat: try `tell me a joke`, `what is 7 plus 5`, `name 3 colors`, `what is a black hole?`.

### Quick start (Windows)

1. Download [`releases/NovaAI-Windows.zip`](releases/NovaAI-Windows.zip) and unzip.
2. Double-click **`NovaAI.exe`** (browser opens the chat).
3. Unlock with `sk-nova-m00ny4xe`. First run downloads the model (~11 MB).
## Notify apps (Android, Bluetooth)

Two apps that send phone notifications over **Bluetooth** — no Wi‑Fi, data, hotspot, or IPs.

| App | Folder | Role |
|-----|--------|------|
| **Notify Sender** | `NotifySender/` | Links once, then sends notifications |
| **Notify Receiver** | `NotifyReceiver/` | Listens and shows the system notification |

Ready APKs: [`releases/`](releases/) · Protocol: [`shared/PROTOCOL.md`](shared/PROTOCOL.md)

## Walkie — walkie-talkie app (Android, internet)

One push-to-talk app that works like a real walkie-talkie **over any internet connection** — mobile data, different Wi-Fi networks, different cities. Install the same APK on **any number of phones**; everyone who types the same **PIN** is on the same channel. The PIN also AES-256-encrypts the audio.

No server setup: every phone connects to several public MQTT brokers **at the same time** and transmits on all of them (receivers de-duplicate), so it works even when different phones' networks can only reach different servers.

Project: [`WalkieTalkie/`](WalkieTalkie/) · Ready APK: [`releases/Walkie.apk`](releases/Walkie.apk)

### Quick start

1. Install `releases/Walkie.apk` on every phone (2, 3, 10 — as many as you want).
2. On all of them: type the **same PIN** (4+ digits, pick something random) → **Connect** → allow microphone.
3. The screen shows how many other devices are on the channel. **Hold the big button** to talk, release to listen.

### Quick start

1. Install `releases/NotifyReceiver.apk` on phone A, `releases/NotifySender.apk` on phone B.
2. Bluetooth **ON** on both. Keep them near each other.
3. Phone A: **Notify Receiver** → allow permissions → **Start**.
4. Phone B: **Link receiver** once → type a message → **Send**.

---

## `bot3.py` — Nova on Discord (your own AI as a bot)

The **same from-scratch neural network** as the Android app, running as a
Discord bot. On startup it **asks for your master API key** — just like the
app's lock screen, the key you input decrypts the model, and a wrong key
keeps Nova locked. Unknown topics are answered from Wikipedia, same as the app.

**Download just this one small file** — on first run it pulls the encrypted
model (~6 MB, `NovaAI/nova_model.sc`) straight from this repo and caches it
next to the script, then works offline. No repo clone, no numpy, no torch:

```bash
pip install discord.py
python bot3.py            # asks for the key, then starts the bot
python bot3.py --selftest # verify everything without a Discord token
# optional for servers: export NOVA_MASTER_KEY="sk-nova-..." to skip the prompt
```

1. Create a bot at the [Discord Developer Portal](https://discord.com/developers/applications), enable **Message Content Intent**
2. Put the token in `TOKEN = "..."` inside the file (or `export DISCORD_TOKEN=...`)
3. Invite it, then: `@Nova <message>`, `!nova <message>`, or just DM it. `!clear` forgets the conversation, `!novahelp` shows help.

## TTS Robot — Discord robot voice (Windows exe + one-file bot)

Joins a voice channel and speaks text with a **robot voice**. Free Edge TTS
(no API key) + ffmpeg FX presets (`robot`, `android`, `dalek`, `chip`, `clean`).

### Windows (recommended)

1. Download [`releases/TTSRobot-Windows.zip`](releases/TTSRobot-Windows.zip) and unzip.
2. Double-click **`TTSRobot.exe`** — browser opens the control panel.
3. Paste your Discord bot token → **Start bot** → invite link appears when online.
4. Join a VC, then type `!tts hello crew`.

Rebuild the zip: `TTSRobot/desktop/build_windows.sh`

### One-file Python (any OS)

```bash
pip install "discord.py[voice]" edge-tts PyNaCl
# need ffmpeg on PATH (Termux: pkg install ffmpeg)
python bot_tts.py            # start bot
python bot_tts.py --selftest # write sample WAVs without a Discord token
```

1. Create a bot at the [Discord Developer Portal](https://discord.com/developers/applications), enable **Message Content Intent**
2. Put the token in `TOKEN = "..."` inside the file (or `export DISCORD_TOKEN=...`)
3. Invite with **Connect** + **Speak** (+ Send Messages)
4. Join a VC, then: `!tts hello crew`, `!voice dalek`, `!auto on`, `@Bot say hi`

Commands: `!join` / `!leave` · `!tts` / `!say` · `!voice` · `!speaker` · `!speed` · `!auto` · `!stop` · `!ttshelp`

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
