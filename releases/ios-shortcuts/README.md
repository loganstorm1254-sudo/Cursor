# iOS Toolkit (Shortcuts)

One Home Screen tap → a menu with **everything useful**: accessibility toggles, system controls, clipboard/device info, text tools, timers, network checks, media, and Settings deep links.

| Shortcut | What it does |
|----------|----------------|
| **[iOS Toolkit](iOS-Toolkit.shortcut)** | Full toolkit menu (8 categories, 70+ actions) |
| **[Toggle Color Invert](Toggle-Color-Invert.shortcut)** | One-tap Classic Invert |
| **[Toggle Smart Invert](Toggle-Smart-Invert.shortcut)** | One-tap Smart Invert |

## Install on iPhone

Open these in **Safari on your iPhone**, then tap **Add Shortcut**.

### iOS Toolkit (recommended)

- File: https://raw.githubusercontent.com/loganstorm1254-sudo/Cursor/cursor/ios-toolkit-shortcut-7a9a/releases/ios-shortcuts/iOS-Toolkit.shortcut
- One-tap import: [Add iOS Toolkit](shortcuts://import-shortcut?url=https%3A%2F%2Fraw.githubusercontent.com%2Floganstorm1254-sudo%2FCursor%2Fcursor%2Fios-toolkit-shortcut-7a9a%2Freleases%2Fios-shortcuts%2FiOS-Toolkit.shortcut&name=iOS%20Toolkit)

### Classic Invert

- File: https://raw.githubusercontent.com/loganstorm1254-sudo/Cursor/cursor/ios-toolkit-shortcut-7a9a/releases/ios-shortcuts/Toggle-Color-Invert.shortcut
- One-tap import: [Add Toggle Color Invert](shortcuts://import-shortcut?url=https%3A%2F%2Fraw.githubusercontent.com%2Floganstorm1254-sudo%2FCursor%2Fcursor%2Fios-toolkit-shortcut-7a9a%2Freleases%2Fios-shortcuts%2FToggle-Color-Invert.shortcut&name=Toggle%20Color%20Invert)

### Smart Invert

- File: https://raw.githubusercontent.com/loganstorm1254-sudo/Cursor/cursor/ios-toolkit-shortcut-7a9a/releases/ios-shortcuts/Toggle-Smart-Invert.shortcut
- One-tap import: [Add Toggle Smart Invert](shortcuts://import-shortcut?url=https%3A%2F%2Fraw.githubusercontent.com%2Floganstorm1254-sudo%2FCursor%2Fcursor%2Fios-toolkit-shortcut-7a9a%2Freleases%2Fios-shortcuts%2FToggle-Smart-Invert.shortcut&name=Toggle%20Smart%20Invert)

If prompted: **Settings → Shortcuts → Allow Untrusted Shortcuts**.

Then open the shortcut → share sheet → **Add to Home Screen** (or pin it in the Shortcuts widget).

## What’s inside iOS Toolkit

### Accessibility
Classic Invert · Smart Invert · Color Filters · Reduce Motion · Reduce Transparency · Increase Contrast · White Point · AssistiveTouch · Zoom · Live Captions · Voice Control · Mono Audio

### Controls
Flashlight · Dark Mode · Low Power Mode · Orientation Lock · True Tone · Night Shift · Always On Display · Wi‑Fi · Bluetooth · Airplane Mode · Cellular Data · Personal Hotspot · Brightness 50% · Brightness Ask · Volume Ask · Lock Screen · Vibrate

### Clipboard & Device
Show / Clear Clipboard · Copy Battery % · Device Name · System Version · Model · Network Name · Public IP

### Text Tools
UPPERCASE · lowercase · Title Case · Count Characters / Words · Base64 Encode / Decode · URL Encode / Decode · SHA256 · Generate UUID · Generate Password

### Time & Focus
Show Date & Time · Copy ISO 8601 · Copy Unix Timestamp · Timer 5 / 10 / 25 min · Toggle Focus · Get Current Focus

### Network
Public / Local IP · Wi‑Fi Details · Speedtest · Down for Everyone? · WhatsMyIP · DNS Google · Cloudflare 1.1.1.1

### Media
Screenshot · Photo · Video · Shazam · Latest Photo · Latest Screenshot

### Quick Open
Settings deep links (Accessibility, Wi‑Fi, Bluetooth, Battery, Display, Focus, Sounds, General, VPN, Cellular, Wallpaper, Shortcuts, App Store) · Home Screen

## Rebuild / resign

```bash
cd releases/ios-shortcuts
python3 build_toolkit.py          # rebuild + HubSign all three
python3 build_toolkit.py --only toolkit
python3 build_toolkit.py --no-sign  # unsigned plist + XML only
```

Requires network for HubSign (RoutineHub). On a Mac you can instead:

```bash
shortcuts sign --mode anyone --input iOS-Toolkit.unsigned.shortcut --output iOS-Toolkit.shortcut
```
