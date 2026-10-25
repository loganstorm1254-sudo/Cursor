# iOS Toolkit (Shortcuts)

One Home Screen tap → a menu with **everything useful**: accessibility toggles, system controls, clipboard/device info, text tools, timers, network checks, media, and Settings deep links.

| Shortcut | What it does |
|----------|----------------|
| **iOS Toolkit** | Full toolkit menu (8 categories, 70+ actions) |
| **Toggle Color Invert** | One-tap Classic Invert |
| **Toggle Smart Invert** | One-tap Smart Invert |

## Install on iPhone (works)

Apple’s `shortcuts://import-shortcut?url=…` **only accepts iCloud links**, so GitHub/raw links show “shortcut URL is invalid.” Use a **download → open** flow instead:

1. On your **iPhone**, open one of the **Download** links below in **Safari** (not Chrome).
2. When the file downloads, tap the **Downloads** (↑ arrow / blue icon) → tap **`iOS-Toolkit.shortcut`**.
3. Tap **Add Shortcut** / **Open in Shortcuts**.
4. If asked: **Settings → Shortcuts → Allow Untrusted Shortcuts**.
5. In Shortcuts: open **iOS Toolkit** → share sheet → **Add to Home Screen**.

### iOS Toolkit (recommended)

| Host | Link |
|------|------|
| **Direct download (best)** | https://h.uguu.se/KGDDYOGh.shortcut |
| Gofile page | https://gofile.io/d/cIxDZGm0 |
| GitHub (permanent) | https://raw.githubusercontent.com/loganstorm1254-sudo/Cursor/cursor/ios-toolkit-shortcut-7a9a/releases/ios-shortcuts/iOS-Toolkit.shortcut |
| jsDelivr CDN | https://cdn.jsdelivr.net/gh/loganstorm1254-sudo/Cursor@cursor/ios-toolkit-shortcut-7a9a/releases/ios-shortcuts/iOS-Toolkit.shortcut |

### Classic Invert

| Host | Link |
|------|------|
| **Direct download** | https://d.uguu.se/QXAHTpbu.shortcut |
| Gofile | https://gofile.io/d/oQa6CDJ1 |
| GitHub | https://raw.githubusercontent.com/loganstorm1254-sudo/Cursor/cursor/ios-toolkit-shortcut-7a9a/releases/ios-shortcuts/Toggle-Color-Invert.shortcut |

### Smart Invert

| Host | Link |
|------|------|
| **Direct download** | https://n.uguu.se/AATdJNlr.shortcut |
| Gofile | https://gofile.io/d/gKGrIv4B |
| GitHub | https://raw.githubusercontent.com/loganstorm1254-sudo/Cursor/cursor/ios-toolkit-shortcut-7a9a/releases/ios-shortcuts/Toggle-Smart-Invert.shortcut |

> Uguu links expire after ~48 hours. GitHub / jsDelivr / Gofile stay available longer.
> If Safari shows the file as gibberish instead of downloading: long-press the link → **Download Linked File**, then open it from Downloads.

### Still stuck?

AirDrop / Files method:

1. On a computer, download the `.shortcut` from GitHub (links above).
2. AirDrop it to your iPhone, or save it to **iCloud Drive**.
3. On the phone: **Files** → tap the `.shortcut` → **Add Shortcut**.

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

To publish a true one-tap **iCloud** install link (the only kind `shortcuts://` accepts): import the signed file on a Mac/iPhone → Share → **Copy iCloud Link**.
