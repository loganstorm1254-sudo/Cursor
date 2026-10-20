# SeekAra for iOS

Native **SwiftUI** companion to the Android SeekAra app. Highlights **Beacon** (SKR-010) and opens [seekara.pt](https://seekara.pt) + [oval.seekara.pt](https://oval.seekara.pt) in-app.

> **Note on “iOS 27”:** Apple has not shipped iOS 27. This project targets **iOS 18+**. When a newer SDK lands, open the project in that Xcode and raise `IPHONEOS_DEPLOYMENT_TARGET` if you want.

## What’s inside

| Tab | Purpose |
|-----|---------|
| **Home** | SeekAra intro, Beacon + Oval cards, links out |
| **Beacon** | Full Beacon info (antinuke, backups, warns, stickies, polls, XP/economy) + Flare / Reverb / SeekDesk |
| **seekara.pt** | In-app browser for the SeekAra site |
| **Oval** | In-app browser for Oval AI chat |

Content is pulled from public SeekAra pages (Beacon listing on seekara.pt, Oval product copy on oval.seekara.pt).

## Open & run (Mac + Xcode)

1. Clone this repo and open `SeekaraIOS/Seekara.xcodeproj` in **Xcode 16+**.
2. Select the **SeekAra** scheme and an iPhone simulator or your device.
3. Set your **Team** under Signing & Capabilities (free Apple ID works).
4. Press **Run** (⌘R).

### Install on a physical iPhone (free)

1. Connect the iPhone → pick it as the run destination.
2. Trust the developer cert: **Settings → General → VPN & Device Management**.
3. Free Apple ID apps expire after ~7 days — rebuild/reinstall to refresh.

## Bundle ID

`pt.seekara.app`

## No Mac? Instant Home Screen app

Open [`releases/seekara-ios/index.html`](../releases/seekara-ios/index.html) in **Safari on iPhone** → Share → **Add to Home Screen**. Same Beacon + Oval + seekara.pt links, no Xcode required.

## Related

- Android APK: [`releases/Seekara.apk`](../releases/Seekara.apk)
- Sites: [seekara.pt](https://seekara.pt) · [oval.seekara.pt](https://oval.seekara.pt)
