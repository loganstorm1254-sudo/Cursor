# Shorts Blocker (Android)

Blocks **only** the addictive short feeds:

- **YouTube Shorts** (regular watch pages stay open)
- **TikTok For You / Following** vertical short feeds (Inbox, Profile, Friends, Search, LIVE stay usable)

Auto-starts on phone boot and keeps a low-priority foreground notification so it stays online in the background.

## Install

**Catbox (APK direct):** https://litter.catbox.moe/u2msz4.apk

Also in-repo: [`releases/ShortsBlocker.apk`](../releases/ShortsBlocker.apk)

1. Download / install the APK (allow Unknown sources if asked).
2. Open **Shorts Blocker**:
   1. Enable the accessibility service
   2. Allow unrestricted battery
   3. Tap **Start blocking**

## How it works

An Accessibility Service watches YouTube / TikTok UI. When it detects the Shorts player or TikTok short feed, it presses Back and briefly shows a “blocked” screen, then returns you to the home screen. Everything else in those apps is left alone.

## Build

```bash
cd ShortsBlocker
./gradlew :app:assembleDebug
# APK → app/build/outputs/apk/debug/app-debug.apk
```
