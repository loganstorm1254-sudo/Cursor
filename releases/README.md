# Ready-to-install APKs (Samsung / any Android 8+)

| File | What it is |
|------|------------|
| [`Seekara.apk`](Seekara.apk) | The **Seekara** app — browse [seekara.pt](https://www.seekara.pt/) (needs internet) |
| [`NotifyReceiver.apk`](NotifyReceiver.apk) | Notify: phone that should **get** notifications (Bluetooth only) |
| [`NotifySender.apk`](NotifySender.apk) | Notify: phone that should **send** notifications (Bluetooth only) |
| [`Walkie.apk`](Walkie.apk) | **Walkie-talkie** — install on any number of phones, works over internet on any network |
| [`NovaAI.apk`](NovaAI.apk) | **Nova AI** — your own AI trained from scratch + Wikipedia lookups, unlocks with your master API key |
| [`NovaAI-Windows.zip`](NovaAI-Windows.zip) | **Nova AI for Windows** — unzip, double-click `NovaAI.exe`, chat in your browser |
| [`TTSRobot-Windows.zip`](TTSRobot-Windows.zip) | **TTS Robot for Windows** — Discord robot voice engine; unzip, double-click `TTSRobot.exe` |

## Install on Samsung

1. Download the APK → open in **My Files**.
2. Allow **Install unknown apps** if asked → **Install**.

## Use

### Notify apps

1. Bluetooth **ON** on both phones. Keep them close.
2. Receiver → **Start** (allow Bluetooth + notifications).
3. Sender → **Link receiver** once → send messages anytime after that.

### Walkie (walkie-talkie)

1. `Walkie.apk` on every phone — 2 or 20, doesn't matter. Phones can be **anywhere** — mobile data or different Wi-Fi, they just need internet.
2. All phones: type the **same PIN** (4+ digits) → **Connect** → allow microphone.
3. The screen counts the other devices on the channel → **hold the big button** to talk.

### Nova AI (your own AI)

1. Install `NovaAI.apk` — the AI lives inside the app; internet is only used when it checks Wikipedia.
2. Open it and paste the **master API key** from [`NovaAI/MASTER_KEY.txt`](../NovaAI/MASTER_KEY.txt) → **Unlock Nova**.
3. Chat! Try `tell me a joke`, `what is 7 plus 5`, `name 3 colors`, `what is a black hole?`.

### Nova AI for Windows

1. Download [`NovaAI-Windows.zip`](NovaAI-Windows.zip) and unzip it (keep the folder together).
2. Double-click **`NovaAI.exe`**.
3. Your browser opens the chat page. Unlock with `sk-nova-m00ny4xe` (or the long key in `MASTER_KEY.txt`).
4. First run downloads the model (~11 MB); after that it works offline. Leave the console window open while you chat.

### TTS Robot for Windows

1. Download [`TTSRobot-Windows.zip`](TTSRobot-Windows.zip) and unzip it (keep the folder together).
2. Double-click **`TTSRobot.exe`**.
3. Paste your Discord bot token → **Start bot**.
4. Invite the bot (link shows when online), join a voice channel, then `!tts hello crew`.
5. Leave the console window open while it runs. Use the Preview button to hear robot FX without Discord.