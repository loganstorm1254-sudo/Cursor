# Seekara (Android)

Native Android app for [Seekara](https://www.seekara.pt/) — fully dark, sleek Material 3 design built with Jetpack Compose. No WebView.

## Screens

- **Home** — gradient hero ("Experiences for everybody."), live stats (16 creators, 15 Discord bots, 2+ projects coming), featured experiences and the Seekara story.
- **Projects** — every Seekara project as a native card: Cloud Gaming, Browse, View, Security Bots, Sonar Instigator, plus what's coming next. Tap to open on seekara.pt.
- **Support** — open a support ticket, get Discord bot help, or jump to the site.

## Details

- 100% Kotlin + Jetpack Compose (Material 3, dark theme).
- Branded splash screen and adaptive launcher icon.
- Requires no permissions at all.
- Android 8.0 (API 26) or newer.

## Build

```bash
./gradlew assembleRelease
# APK: app/build/outputs/apk/release/app-release.apk
```

A ready-to-install copy lives in [`../releases/Seekara.apk`](../releases/Seekara.apk).
