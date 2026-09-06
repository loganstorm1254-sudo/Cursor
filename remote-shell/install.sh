#!/usr/bin/env bash
# Beacon Remote Shell — one-line installer for Ubuntu
# Usage:
#   curl -fsSL <raw-install-url> | sudo bash
# Or from a checkout:
#   sudo bash install.sh
set -euo pipefail

APP=beacon-remote
INSTALL_DIR="${BEACON_REMOTE_HOME:-/opt/beacon-remote}"
PORT="${BEACON_REMOTE_PORT:-7788}"
REPO_URL="${BEACON_REMOTE_REPO:-https://github.com/loganstorm1254-sudo/Cursor.git}"
REPO_REF="${BEACON_REMOTE_REF:-cursor/remote-shell-b152}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash install.sh"
  exit 1
fi

echo "==> Installing Beacon Remote Shell"

apt-get update -y
apt-get install -y python3 python3-venv python3-pip curl ca-certificates git

mkdir -p "$INSTALL_DIR/agent"

SCRIPT_DIR=""
if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

if [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/agent/server.py" ]]; then
  echo "==> Using local agent from $SCRIPT_DIR"
  cp -a "$SCRIPT_DIR/agent/." "$INSTALL_DIR/agent/"
else
  echo "==> Fetching agent from $REPO_URL ($REPO_REF)"
  TMP="$(mktemp -d)"
  git clone --depth 1 --branch "$REPO_REF" "$REPO_URL" "$TMP/src"
  cp -a "$TMP/src/remote-shell/agent/." "$INSTALL_DIR/agent/"
  rm -rf "$TMP"
fi

python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install -U pip wheel
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/agent/requirements.txt"

cat > /usr/local/bin/beacon-remote <<EOF
#!/usr/bin/env bash
exec "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/agent/server.py" "\$@"
EOF
chmod +x /usr/local/bin/beacon-remote

mkdir -p /var/lib/beacon-remote
chmod 700 /var/lib/beacon-remote

cat > /etc/systemd/system/beacon-remote.service <<EOF
[Unit]
Description=Beacon Remote Shell Agent
After=network.target

[Service]
Type=simple
Environment=BEACON_REMOTE_DATA=/var/lib/beacon-remote
Environment=BEACON_REMOTE_HOST=0.0.0.0
Environment=BEACON_REMOTE_PORT=$PORT
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/agent/server.py serve --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=3
User=root

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable beacon-remote.service
systemctl restart beacon-remote.service

if command -v ufw >/dev/null 2>&1; then
  ufw allow "$PORT"/tcp || true
fi

echo
echo "==> Installed"
echo "    CLI:     beacon-remote"
echo "    Service: systemctl status beacon-remote"
echo "    Port:    $PORT"
echo
echo "Set your PIN now (stored hashed on THIS server only):"
echo "    beacon-remote pin-set"
echo
IP="$(curl -fsS ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')"
echo "Then open your Vercel site and use agent URL:"
echo "    http://$IP:$PORT"
echo
echo "IMPORTANT: put this behind HTTPS (Caddy/Nginx + domain) for real use."
