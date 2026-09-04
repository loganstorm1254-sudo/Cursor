#!/usr/bin/env bash
# Build releases/BeaconConsoleBridge-Windows.zip with BeaconConsoleBridge.exe
# + embeddable CPython + bridge.py (stdlib only).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
AGENT="$(cd "$(dirname "$0")" && pwd)"
OUT="$ROOT/releases/BeaconConsoleBridge-Windows"
ZIP="$ROOT/releases/BeaconConsoleBridge-Windows.zip"
PYVER="3.12.8"
PYURL="https://www.python.org/ftp/python/${PYVER}/python-${PYVER}-embed-amd64.zip"
WORK="$AGENT/_build"

rm -rf "$WORK" "$OUT" "$ZIP"
mkdir -p "$WORK" "$OUT/python" "$OUT/app"

echo "==> Compiling BeaconConsoleBridge.exe"
x86_64-w64-mingw32-gcc -O2 -s -o "$OUT/BeaconConsoleBridge.exe" "$AGENT/launcher.c" \
  -mconsole -luser32

echo "==> Downloading Windows embeddable CPython ${PYVER}"
wget -q -O "$WORK/python-embed.zip" "$PYURL"
unzip -q "$WORK/python-embed.zip" -d "$OUT/python"

PTH=$(echo "$OUT"/python/python*._pth)
cat > "$PTH" <<EOF
python312.zip
.
import site
EOF

echo "==> Copying bridge"
cp "$AGENT/bridge.py" "$OUT/app/bridge.py"
cp "$AGENT/bridge_config.example.json" "$OUT/bridge_config.example.json"

cat > "$OUT/README.txt" <<'EOF'
Beacon Console Bridge (Windows)
================================

Streams your Discord bot CMD window to your Vercel Beacon Console site.
The website is READ-ONLY (no typing / no remote shell).

1. Deploy BotConsole to Vercel first (see BotConsole-Vercel.zip / BotConsole/README.md).
2. Unzip this folder. Keep files together.
3. Prefer putting this folder next to smmod.py, OR use a full path for the command.
4. Double-click BeaconConsoleBridge.exe
5. Enter:
     - Website URL  (https://your-app.vercel.app)
     - Username
     - Password
     - Command to run  (default: py smmod.py   or your .exe path)
6. Leave this window open while the bot runs.
7. On your phone/laptop, open the Vercel URL and log in with the same username/password.

Config is saved as bridge_config.json next to the exe (do not share it).
EOF

echo "==> Zipping"
(cd "$ROOT/releases" && zip -qr BeaconConsoleBridge-Windows.zip BeaconConsoleBridge-Windows)
ls -lh "$OUT/BeaconConsoleBridge.exe" "$ZIP"
echo "DONE: $ZIP"
