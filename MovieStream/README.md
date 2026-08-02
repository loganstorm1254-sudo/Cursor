# Reel — Wi‑Fi movie stream (VLC audio)

Stream **MKV** and **MP4** from **`D:\Movies`** to phones on the same Wi‑Fi.

Browsers often play video with **no sound** (AC3/DTS). Use **VLC on the phone** for full audio.

## Quick start

1. Download [`releases/Reel-Windows.zip`](../releases/Reel-Windows.zip) and unzip.
2. Put movies in `D:\Movies`.
3. **Right‑click `Reel.bat` → Run as administrator** the first time (opens Windows Firewall for phones).
4. On your phone (same Wi‑Fi): install **VLC**, open one of the **PHONE** URLs printed in the window (not `127.0.0.1`).
5. Tap a movie → **Open in VLC**.

## Phone can’t connect?

- Use the PC’s Wi‑Fi IPv4 from `ipconfig` / the bat window — never `127.0.0.1` on the phone.
- Phone and PC must be on the **same Wi‑Fi** (not guest/isolated Wi‑Fi).
- Re-run `Reel.bat` as Administrator so the firewall rule is added.
- Windows network profile should be **Private**.

## Audio

| Player | Audio |
|--------|--------|
| **VLC on phone** (Open in VLC / Network stream) | Full — recommended |
| Browser + **ffmpeg** on PC | Remuxed AAC |
| Browser alone | Often silent on MKVs |

Optional: install [ffmpeg](https://ffmpeg.org/) on the PC for browser audio. Install [VLC](https://www.videolan.org/) on PC for “Play on this PC”.

## Options

```bash
python MovieStream/stream.py --movies "D:\Movies" --port 8080 --open
```
