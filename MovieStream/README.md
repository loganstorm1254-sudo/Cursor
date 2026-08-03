# Reel — Wi‑Fi movies from D:\Movies

Stream `.mkv` / `.mp4` (and more) from your PC to any phone on the same Wi‑Fi.

## Use it

1. Download [`releases/Reel-Windows.zip`](../releases/Reel-Windows.zip) and unzip.
2. Put movies in **`D:\Movies`**.
3. Run **`Reel.bat`** → click **Yes** (Administrator / firewall).
4. On the PC, scan the **QR** with your phone, or open the URL in **PHONE-URL.txt** (port **8787**).
5. Tap a movie → **Open in VLC** for full audio (or **Play here** if ffmpeg is installed).

## What’s new

- QR code on the library page for easy phone pairing
- Folder filters, search, sort (A–Z / newest / largest)
- Poster thumbnails (when ffmpeg is on the PC)
- Resume progress bars
- Auto browser play with AAC audio remux when ffmpeg is available
- Opens Windows Firewall for Python + port 8787

## Phone still can’t connect?

- Same Wi‑Fi (not guest / AP isolation); Windows network = **Private**
- Use the `192.168…` link — never `127.0.0.1` on the phone
- Or join the PC to your phone hotspot and use the new IP Reel prints
