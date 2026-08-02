#!/usr/bin/env bash
# Build releases/TTSRobot-Windows.zip — TTSRobot.exe + embeddable CPython + deps + ffmpeg.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DESK="$(cd "$(dirname "$0")" && pwd)"
OUT="$ROOT/releases/TTSRobot-Windows"
ZIP="$ROOT/releases/TTSRobot-Windows.zip"
PYVER="3.12.8"
PYURL="https://www.python.org/ftp/python/${PYVER}/python-${PYVER}-embed-amd64.zip"
# Compact static ffmpeg (extracted on first run from the .gz next to the app)
FFURL="https://github.com/eugeneware/ffmpeg-static/releases/download/b6.0/ffmpeg-win32-x64.gz"
WORK="$DESK/_build"

rm -rf "$WORK" "$OUT" "$ZIP"
mkdir -p "$WORK" "$OUT/python" "$OUT/app" "$OUT/ffmpeg"

echo "==> Compiling TTSRobot.exe"
x86_64-w64-mingw32-gcc -O2 -s -o "$OUT/TTSRobot.exe" "$DESK/launcher.c" \
  -mconsole -luser32

echo "==> Downloading Windows embeddable CPython ${PYVER}"
wget -q -O "$WORK/python-embed.zip" "$PYURL"
unzip -q "$WORK/python-embed.zip" -d "$OUT/python"

PTH=$(echo "$OUT"/python/python*._pth)
cat > "$PTH" <<EOF
python312.zip
.
Lib/site-packages
import site
EOF

echo "==> Installing Windows wheels into embeddable site-packages"
mkdir -p "$OUT/python/Lib/site-packages"
python3 -m pip install -q \
  --target "$OUT/python/Lib/site-packages" \
  --platform win_amd64 \
  --python-version 312 \
  --implementation cp \
  --abi cp312 \
  --only-binary=:all: \
  "discord.py[voice]" edge-tts PyNaCl

python3 - <<PY
from pathlib import Path
sp = Path("$OUT/python/Lib/site-packages")
print("site-packages entries:", len(list(sp.iterdir())))
for need in ("discord", "edge_tts", "nacl"):
    ok = any(p.name.startswith(need) for p in sp.iterdir())
    print(f"  {need}: {'OK' if ok else 'MISSING'}")
    if not ok:
        raise SystemExit(f"missing dependency: {need}")
PY

echo "==> Bundling compressed static ffmpeg (first run extracts ffmpeg.exe)"
wget -q -O "$OUT/ffmpeg/ffmpeg-win64.gz" "$FFURL"
test -s "$OUT/ffmpeg/ffmpeg-win64.gz"

echo "==> Copying app files"
cp "$DESK/tts_app.py" "$OUT/app/tts_app.py"
cp "$ROOT/bot_tts.py" "$OUT/app/bot_tts.py"

cat > "$OUT/README.txt" <<'EOF'
TTS Robot for Windows
=====================

Discord robot voice engine — all-in-one pack.

1. Unzip this folder anywhere (keep the files together).
2. Double-click TTSRobot.exe
3. Your browser opens the control panel.
4. Paste your Discord bot token → Start bot
5. Invite the bot (link appears when online), join a voice channel,
   then type:  !tts hello crew

Voice presets: robot | android | dalek | chip | clean
Also: !voice, !speaker, !speed, !auto on, !stop, !ttshelp

Leave the black console window open while the bot runs. Close it to quit.

Needs internet for Discord + Edge TTS.
First launch extracts bundled ffmpeg (~30 MB gz) for robot voice FX.
Create a bot at https://discord.com/developers/applications
Enable MESSAGE CONTENT INTENT. Invite with Connect + Speak permissions.
EOF

echo "==> Zipping"
(cd "$ROOT/releases" && zip -qr TTSRobot-Windows.zip TTSRobot-Windows)
ls -lh "$OUT/TTSRobot.exe" "$OUT/ffmpeg/ffmpeg-win64.gz" "$ZIP"
echo "DONE: $ZIP"
du -sh "$OUT" "$ZIP"
