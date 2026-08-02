# Reel — Wi‑Fi movies from D:\Movies

## Fix: phone can’t connect / no movies

1. Re-download [`releases/Reel-Windows.zip`](../releases/Reel-Windows.zip) and unzip (overwrite old files).
2. Put `.mp4` / `.mkv` files in **`D:\Movies`**.
3. Double-click **`Reel.bat`** → click **Yes** on the Administrator prompt (required for firewall).
4. On the PC, confirm movies are listed in the window and at `http://127.0.0.1:8787/`.
5. On your phone (same Wi‑Fi), open the big URL shown, e.g. `http://192.168.x.x:8787/`  
   Also saved in **`PHONE-URL.txt`**. Never use `127.0.0.1` on the phone.
6. Tap a movie → **Open in VLC** for audio.

### Still can’t connect from phone?

- PC and phone on the **same Wi‑Fi** (not guest / “AP isolation”).
- Windows Wi‑Fi profile = **Private**.
- Try turning the PC into a hotspot and joining from the phone, or join the PC to the phone’s hotspot — then use the new IP Reel prints.
- Antivirus may block Python; allow it when asked.

Port is **8787** (not 8080).
