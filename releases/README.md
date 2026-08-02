# Ready-to-install APKs (Samsung / any Android 8+)

| File | What it is |
|------|------------|
| [`Seekara.apk`](Seekara.apk) | The **Seekara** app — browse [seekara.pt](https://www.seekara.pt/) (needs internet) |
| [`NotifyReceiver.apk`](NotifyReceiver.apk) | Notify: phone that should **get** notifications (Bluetooth only) |
| [`NotifySender.apk`](NotifySender.apk) | Notify: phone that should **send** notifications (Bluetooth only) |
| [`Walkie.apk`](Walkie.apk) | **Walkie-talkie** — install on any number of phones, works over internet on any network |
| [`NovaAI.apk`](NovaAI.apk) | **Nova AI** — your own AI trained from scratch + Wikipedia lookups, unlocks with your master API key |
| [`NovaAI-Windows.zip`](NovaAI-Windows.zip) | **Nova AI for Windows** — unzip, double-click `NovaAI.exe`, chat in your browser |
| [`Reel-Windows.zip`](Reel-Windows.zip) | **Reel** — Wi‑Fi movie stream from `D:\Movies` (MKV/MP4). Unzip, double-click `Reel.bat` |

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

### Reel (Wi‑Fi movies from D:\Movies)

1. Download [`Reel-Windows.zip`](Reel-Windows.zip) and unzip it.
2. Put your `.mkv` / `.mp4` files in `D:\Movies`.
3. **Right‑click `Reel.bat` → Run as administrator** once (firewall so phones can connect). Needs Python on PATH.
4. On your phone (same Wi‑Fi): install **VLC**, open a **PHONE** URL from the window (not `127.0.0.1`).
5. Tap a movie → **Open in VLC** for sound.