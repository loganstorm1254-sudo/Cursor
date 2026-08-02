#!/usr/bin/env bash
# Build releases/NovaAI-Windows.zip containing NovaAI.exe + embeddable CPython.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DESK="$(cd "$(dirname "$0")" && pwd)"
OUT="$ROOT/releases/NovaAI-Windows"
ZIP="$ROOT/releases/NovaAI-Windows.zip"
PYVER="3.12.8"
PYURL="https://www.python.org/ftp/python/${PYVER}/python-${PYVER}-embed-amd64.zip"
WORK="$DESK/_build"
rm -rf "$WORK" "$OUT" "$ZIP"
mkdir -p "$WORK" "$OUT/python" "$OUT/app"

echo "==> Compiling NovaAI.exe"
x86_64-w64-mingw32-gcc -O2 -s -o "$OUT/NovaAI.exe" "$DESK/launcher.c" \
  -mconsole -luser32

echo "==> Downloading Windows embeddable CPython ${PYVER}"
wget -q -O "$WORK/python-embed.zip" "$PYURL"
unzip -q "$WORK/python-embed.zip" -d "$OUT/python"

# Enable site-packages / loose imports (needed so app/ is on path via PYTHONPATH)
PTH=$(echo "$OUT"/python/python*._pth)
# The embeddable layout ships pythonXX._pth that isolates imports; relax it.
cat > "$PTH" <<EOF
python312.zip
.
import site
EOF

echo "==> Copying app files"
cp "$DESK/nova_app.py" "$OUT/app/nova_app.py"
cp "$ROOT/bot3.py" "$OUT/app/bot3.py"

cat > "$OUT/README.txt" <<'EOF'
Nova AI for Windows
===================

1. Unzip this folder anywhere (keep the files together).
2. Double-click NovaAI.exe
3. Your browser opens to Nova's chat page.
4. Unlock with a master API key:
      sk-nova-m00ny4xe
   or sk-nova-58d58cec6b35ee0abfea1452f7e7d11d6a4f16b8e936220f
5. First unlock downloads the model (~11 MB) from GitHub, then works offline.

Leave the black console window open while you chat. Close it to quit.

Same brain as the Android app (releases/NovaAI.apk) and Discord bot (bot3.py).
EOF

echo "==> Zipping"
(cd "$ROOT/releases" && zip -qr NovaAI-Windows.zip NovaAI-Windows)
# Also drop a copy of just the exe note? Keep the folder + zip.
ls -lh "$OUT/NovaAI.exe" "$ZIP"
echo "DONE: $ZIP"
