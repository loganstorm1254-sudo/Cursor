# Shorts Blocker (Android)

Blocks **only** the addictive short feeds:

- **YouTube Shorts** (regular watch pages stay open)
- **TikTok For You / Following** vertical short feeds (Inbox, Profile, Friends, Search, LIVE stay usable)

Auto-starts on phone boot and keeps a low-priority foreground notification so it stays online in the background.

## Install

**Catbox (APK direct):** https://litter.catbox.moe/ptkjc2.apk

Also in-repo: [`releases/ShortsBlocker.apk`](../releases/ShortsBlocker.apk)

1. Download / install the APK (allow Unknown sources if asked).
2. Open **Shorts Blocker** and follow the steps:
   1. **Allow restricted settings** (Android 13+): App info → tap **⋮** (top right) → **Allow restricted settings**
   2. Enable the accessibility service (it will stay greyed out until step 1 is done)
   3. Allow unrestricted battery
   4. Tap **Start blocking**

If Accessibility shows **“Controlled by restricted setting”**, that means step 1 is still needed — the app *is* listed, just locked by Android for sideloaded APKs.

## How it works

An Accessibility Service watches YouTube / TikTok UI. When it detects the Shorts player or TikTok short feed, it presses Back and briefly shows a “blocked” screen, then returns you to the home screen. Everything else in those apps is left alone.

## Build

```bash
cd ShortsBlocker
./gradlew :app:assembleDebug
# APK → app/build/outputs/apk/debug/app-debug.apk
```
