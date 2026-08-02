# Reel — Wi‑Fi movie stream

Stream **MKV** and **MP4** files from your Movies folder to any phone, tablet, or laptop on the same Wi‑Fi. No install on the clients — just a browser.

Default library path: **`D:\Movies`**.

## Quick start (Windows)

1. Put your `.mkv` / `.mp4` files in `D:\Movies` (subfolders are fine).
2. On that PC:

```bash
python MovieStream/stream.py
```

3. Open the printed URL on your phone (same Wi‑Fi), e.g. `http://192.168.1.23:8080/`
4. Tap a title to play. Keep the Python window open while watching.

### Options

```bash
python MovieStream/stream.py --movies "D:\Movies" --port 8080 --open
```

| Flag | Meaning |
|------|---------|
| `--movies PATH` / `-m` | Folder to scan (default `D:\Movies`, or `REEL_MOVIES_DIR`) |
| `--port N` / `-p` | Port (default `8080`) |
| `--host ADDR` | Bind address (default `0.0.0.0` so phones can connect) |
| `--open` | Open the library in this PC’s browser |

Stdlib only — no `pip install`.

## Playback notes

- **MP4** (H.264 + AAC) plays in virtually every phone browser.
- **MKV** often works in Chrome/Edge when the video inside is H.264; Safari/iOS usually needs MP4. If an MKV won’t play, remux it once:

```bash
ffmpeg -i "movie.mkv" -c copy "movie.mp4"
```

Seeking uses HTTP range requests.

## Firewall

If phones can’t connect, allow Python (or port 8080) on the **Private** network in Windows Firewall.
