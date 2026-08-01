# Walkie A

Internet push-to-talk walkie-talkie. Pair app: [`WalkieTalkieB/`](../WalkieTalkieB/) (identical, different name/color so both fit on one phone).

## How it works

- Both phones connect out to a **public MQTT broker** (`broker.hivemq.com`, fallback `broker.emqx.io`), so it works on **mobile data, different Wi-Fi networks, anywhere with internet** — no server of your own, no port forwarding, no same-network requirement.
- The **PIN** you type picks the channel *and* is used to **AES-256 encrypt** every audio packet, so only phones with the same PIN can listen.
- Audio is 16 kHz mono PCM, sent in 100 ms chunks while you hold the button (half-duplex, like a real walkie-talkie).

## Use

1. Install Walkie A on one phone and Walkie B on the other (or the same app on both — any mix works, they share the protocol).
2. On both phones: type the **same PIN** (4+ digits, pick something random like `739184`) → **Connect** → allow microphone.
3. Wait for "Other phone is on the channel ✓", then **hold the big button** to talk.

## Build

```bash
./gradlew assembleDebug   # APK at app/build/outputs/apk/debug/app-debug.apk
```
