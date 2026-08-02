#!/usr/bin/env bash
# Build releases/NovaAI-Windows.zip containing NovaAI.exe + embeddable CPython
# + bundled model + native fastmath DLL.
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

CC="${CC:-x86_64-w64-mingw32-gcc}"

echo "==> Compiling NovaAI.exe"
"$CC" -O2 -s -o "$OUT/NovaAI.exe" "$DESK/launcher.c" \
  -mconsole -luser32

echo "==> Compiling nova_fastmath.dll (native matmul / f16 decode)"
"$CC" -O3 -ffast-math -shared -s -o "$OUT/app/nova_fastmath.dll" \
  "$DESK/fastmath.c"

echo "==> Downloading Windows embeddable CPython ${PYVER}"
wget -q -O "$WORK/python-embed.zip" "$PYURL"
unzip -q "$WORK/python-embed.zip" -d "$OUT/python"

# Drop modules Nova never imports — keeps the zip leaner on disk/download.
REMOVE_PYD=(
  _msi.pyd
  _elementtree.pyd
  winsound.pyd
  _zoneinfo.pyd
  _decimal.pyd
  _sqlite3.pyd
  _multiprocessing.pyd
  _overlapped.pyd
  _asyncio.pyd
  _wmi.pyd
  _uuid.pyd
  pyexpat.pyd
)
for f in "${REMOVE_PYD[@]}"; do
  rm -f "$OUT/python/$f"
done
rm -f "$OUT/python/sqlite3.dll" "$OUT/python/pythonw.exe" "$OUT/python/python.cat"

# Enable site-packages / loose imports (needed so app/ is on path via PYTHONPATH)
PTH=$(echo "$OUT"/python/python*._pth)
cat > "$PTH" <<EOF
python312.zip
.
import site
EOF

echo "==> Copying app files + bundled model"
cp "$DESK/nova_app.py" "$OUT/app/nova_app.py"
cp "$ROOT/bot3.py" "$OUT/app/bot3.py"
cp "$ROOT/NovaAI/nova_model.sc" "$OUT/app/nova_model.sc"

# Byte-compile with host Python 3.12 for a slightly faster cold start.
python3 - <<PY
import compileall
compileall.compile_dir("$OUT/app", quiet=1, optimize=2)
print("compiled $OUT/app")
PY

cat > "$OUT/README.txt" <<'EOF'
Nova AI for Windows
===================

1. Unzip this folder anywhere (keep the files together).
2. Double-click NovaAI.exe
3. Your browser opens to Nova's chat page.
4. Unlock with a master API key:
      sk-nova-m00ny4xe
   or sk-nova-58d58cec6b35ee0abfea1452f7e7d11d6a4f16b8e936220f

The brain (nova_model.sc) is already inside this pack — no download needed.
Native math (nova_fastmath.dll) speeds up replies on Windows.

Leave the black console window open while you chat. Close it to quit.

Same brain as the Android app (releases/NovaAI.apk) and Discord bot (bot3.py).
EOF

echo "==> Zipping"
(cd "$ROOT/releases" && zip -qr NovaAI-Windows.zip NovaAI-Windows)
ls -lh "$OUT/NovaAI.exe" "$OUT/app/nova_fastmath.dll" "$ZIP"
echo "DONE: $ZIP"
