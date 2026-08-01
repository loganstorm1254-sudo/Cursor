# Walkie

Internet push-to-talk walkie-talkie. **One APK, any number of phones** — everyone who installs it and types the same PIN is on the same channel.

## How it works

- Every phone connects out to **public MQTT brokers**, so it works on **mobile data, different Wi-Fi networks, anywhere with internet** — no server of your own, no port forwarding, no same-network requirement.
- The **PIN** you type picks the channel *and* is used to **AES-256 encrypt** every audio packet, so only phones with the same PIN can listen.
- The public brokers are independent networks, so each phone connects to **all reachable brokers at once** and transmits on all of them; receivers drop duplicate packets by sequence number. That way it never matters which broker each phone's network lets through — everyone always hears everyone.
- Per broker, several ports/transports are tried (plain 1883, TLS 8883, WebSocket), so it connects even on networks that block the standard MQTT port.
- Audio is 16 kHz mono PCM, sent in 100 ms chunks while you hold the button (half-duplex, like a real walkie-talkie).

## Use

1. Install [`releases/Walkie.apk`](../releases/Walkie.apk) on every phone (2, 3, 10 — as many as you want).
2. On all of them: type the **same PIN** (4+ digits, pick something random like `739184`) → **Connect** → allow microphone.
3. The screen shows how many other devices are on the channel. **Hold the big button** to talk, release to listen.

## Build

```bash
./gradlew assembleDebug   # APK at app/build/outputs/apk/debug/app-debug.apk
```
