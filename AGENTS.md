# AGENTS.md

## Cursor Cloud specific instructions

This repo is a **monorepo of independent hobby projects** (no shared backend, no
database, no docker, no CI). Each project stands alone. Two groups:

- **Python** (run directly, no build step): `bot.py`, `bot2.py`, `bot3.py`,
  `MovieStream/stream.py`, `NovaAI/desktop/nova_app.py`.
- **Android/Kotlin** (Gradle): `NovaAI/`, `NotifySender/`, `NotifyReceiver/`,
  `WalkieTalkie/`. Each has its own `gradlew` wrapper (Gradle 8.9, AGP 8.7.3,
  targets Java 17). There is no top-level aggregate build — build each app from
  its own directory.

### Environment already provisioned (persisted in the VM snapshot)

- Android SDK at `/opt/android-sdk` (`platforms;android-35`,
  `build-tools;35.0.0`, `platform-tools`). `ANDROID_HOME`/`ANDROID_SDK_ROOT`
  and the SDK tools are on `PATH` via `~/.bashrc`.
- Each Android project has a gitignored `local.properties` with
  `sdk.dir=/opt/android-sdk`, so `./gradlew` works without extra env vars.
- JDK 21 is the default `java`. Gradle 8.9 runs fine on it even though the
  modules target Java 17 — do **not** expect a JDK 17 to be installed.
- Python bot deps (`discord.py`, `g4f`, `aiohttp`) are installed by the update
  script.

### Running / testing (non-obvious caveats)

- **Nova AI desktop web app** — `python3 NovaAI/desktop/nova_app.py` serves a
  chat UI on `http://127.0.0.1:8765` (`NOVA_PORT` overrides). It imports
  `bot3.py`, so run it from the repo root. On first unlock it downloads the
  encrypted model (~11 MB) from GitHub raw, then works offline. Unlock/chat with
  master key `sk-nova-m00ny4xe` via `POST /api/unlock` then `POST /api/chat`.
  This is the easiest full end-to-end demo (no Discord token needed).
- **Nova engine self-test** — `NOVA_MASTER_KEY="sk-nova-m00ny4xe" python3 bot3.py --selftest`
  runs inference + Wikipedia lookup offline of Discord. Without the key (env or
  prompt) it exits "locked" — always provide `NOVA_MASTER_KEY` in headless runs.
- **Discord bots** — `bot.py`, `bot2.py`, `bot3.py` need a Discord bot token
  (`DISCORD_TOKEN` env or `TOKEN=` in-file). With no token they print setup
  instructions and exit 1 (expected). `bot.py`/`bot2.py` also call out to free
  g4f/Pollinations providers at runtime.
- **Reel / MovieStream** — `python3 MovieStream/stream.py --movies <dir> --port 8787`.
  Default movies dir is Windows `D:\Movies`; on Linux pass `--movies`. `ffmpeg`
  is available for remux/thumbnails.
- **Android** — from an app dir: `./gradlew assembleDebug` (APK under
  `app/build/outputs/apk/debug/`), `./gradlew test` (NovaAI has unit tests;
  `-DrunLiveTests=true` additionally hits live Wikipedia). Real device/emulator
  behavior (Bluetooth for Notify apps, mic/MQTT for Walkie) cannot be exercised
  headlessly — only build + unit tests are runnable here.
- **Android lint** — `./gradlew lintDebug` currently **fails** on a
  pre-existing `UseAppTint` error in `NovaAI/app/src/main/res/layout/activity_main.xml`
  (`android:tint` → `app:tint`). This is a repo issue, not an environment
  problem; lint itself runs correctly.
