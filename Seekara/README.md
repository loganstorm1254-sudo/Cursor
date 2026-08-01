# Seekara (Android)

Official-style Android wrapper for [seekara.pt](https://www.seekara.pt/).

## What it does

- Loads the Seekara site in a full-screen in-app browser (WebView).
- Branded splash screen and adaptive launcher icon.
- Pull down to refresh.
- Offline screen with a Retry button when there is no connection.
- Back button walks through the site's page history.
- Links that leave `seekara.pt` open in the phone's browser.

## Requirements

- Android 8.0 (API 26) or newer.
- Internet connection.

## Build

```bash
./gradlew assembleRelease
# APK: app/build/outputs/apk/release/app-release.apk
```

A ready-to-install copy lives in [`../releases/Seekara.apk`](../releases/Seekara.apk).
