#!/usr/bin/env bash
# Pack BotConsole for Vercel upload (no node_modules / .next).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
ZIP="$REPO/releases/BotConsole-Vercel.zip"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$WORK/BotConsole"
rsync -a \
  --exclude node_modules \
  --exclude .next \
  --exclude .env \
  --exclude .env.local \
  --exclude .vercel \
  --exclude agent/_build \
  --exclude agent/bridge_config.json \
  --exclude '*.log' \
  "$ROOT/" "$WORK/BotConsole/"

# Drop a short deploy note at the zip root
cat > "$WORK/DEPLOY.txt" <<'EOF'
Beacon Console — deploy to Vercel
=================================

Option A (easiest): GitHub
  1. Push this repo
  2. Vercel → New Project → import repo
  3. Root Directory = BotConsole
  4. Add env SESSION_SECRET (long random string)
  5. Optional: UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN
  6. Deploy

Option B: upload this zip
  1. Vercel → New Project → upload / CLI deploy from BotConsole folder
  2. Same env vars as above

Then run BeaconConsoleBridge.exe on your server PC (see
releases/BeaconConsoleBridge-Windows.zip).
EOF

rm -f "$ZIP"
(cd "$WORK" && zip -qr "$ZIP" BotConsole DEPLOY.txt)
ls -lh "$ZIP"
echo "DONE: $ZIP"
