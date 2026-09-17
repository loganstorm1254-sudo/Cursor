# Shorts Blocker (Android)

Blocks **only** the addictive short feeds:

- **YouTube Shorts** (regular watch pages stay open)
- **TikTok For You / Following** vertical short feeds (Inbox, Profile, Friends, Search, LIVE stay usable)

Auto-starts on phone boot and keeps a low-priority foreground notification so it stays online in the background.

On **TikTok**, the short feed gets a mid-screen cover — top tabs and the bottom bar stay usable so you can jump to Inbox / Profile / etc. without leaving the app.

## Install

**Catbox (APK direct):** https://litter.catbox.moe/pf912a.apk

Also in-repo: [`releases/ShortsBlocker.apk`](../releases/ShortsBlocker.apk)

1. Install the APK.
2. Open **Shorts Blocker** → tap **Enable Shorts Blocker** once → flip the switch **On**.

That’s it. Boot auto-start and background stay-alive are automatic.

## How it works

An Accessibility Service watches YouTube / TikTok UI. When it detects the Shorts player or TikTok short feed, it presses Back and briefly shows a “blocked” screen, then returns you to the home screen. Everything else in those apps is left alone.

## Build

```bash
cd ShortsBlocker
./gradlew :app:assembleDebug
# APK → app/build/outputs/apk/debug/app-debug.apk
```
