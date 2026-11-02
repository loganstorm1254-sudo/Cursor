# TapShare

Tap the **tops of two Samsung/Android phones** together to share the photo on screen — like Apple’s tap-to-share / NameDrop.

## What it does

- **Always active** — foreground service stays running even after you leave the app
- **Starts on boot** — comes back after reboot / Quick Boot (Samsung)
- **Gallery** — open a photo in TapShare (or share one from the system Gallery into TapShare)
- **NFC tap** — hold the tops of two phones with TapShare installed; rings animate and the photo transfers over Bluetooth
- **Opens on their screen** — the other phone saves it and shows it full screen

## Install

1. Install `releases/TapShare.apk` on **both** phones (same APK).
2. Open **TapShare** once → allow photos, nearby devices, notifications, and NFC.
3. Tap **Allow background** so Samsung doesn’t sleep the service.
4. On phone A: **Open Gallery** → pick a photo.
5. Hold the **tops** of phone A and phone B together.
6. Watch the ripple animation — the photo lands full screen on phone B.

## Requirements

- Android 8+ with **NFC** and **Bluetooth**
- NFC turned **On** in system settings on both phones
- Both phones need TapShare installed and the always-on notification visible

## Project

Android app under `TapShare/` — package `com.tapshare.app`.
