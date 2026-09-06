#!/usr/bin/env bash
# Install Seekara Status Agent on the Ubuntu VPS (reads pm2).
# Usage: curl -fsSL <raw-url> | sudo bash
set -euo pipefail

APP=seekara-status-agent
DIR="${SEEKARA_STATUS_HOME:-/opt/seekara-status}"
PORT="${SEEKARA_STATUS_PORT:-5055}"
REPO_URL="${SEEKARA_STATUS_REPO:-https://github.com/loganstorm1254-sudo/Cursor.git}"
REPO_REF="${SEEKARA_STATUS_REF:-cursor/seekara-status-bot-b152}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash install-agent.sh"
  exit 1
fi

apt-get update -y
apt-get install -y python3 curl ca-certificates git

mkdir -p "$DIR"

SCRIPT_DIR=""
if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

if [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/agent.py" ]]; then
  cp -a "$SCRIPT_DIR/agent.py" "$DIR/agent.py"
else
  TMP="$(mktemp -d)"
  git clone --depth 1 --branch "$REPO_REF" "$REPO_URL" "$TMP/src"
  cp -a "$TMP/src/seekara-status/agent.py" "$DIR/agent.py"
  rm -rf "$TMP"
fi

cat > /usr/local/bin/seekara-status-agent <<EOF
#!/usr/bin/env bash
exec python3 "$DIR/agent.py" "\$@"
EOF
chmod +x /usr/local/bin/seekara-status-agent

cat > /etc/systemd/system/seekara-status-agent.service <<EOF
[Unit]
Description=Seekara Status Agent (pm2 probe)
After=network.target

[Service]
Type=simple
Environment=SEEKARA_STATUS_HOST=0.0.0.0
Environment=SEEKARA_STATUS_PORT=$PORT
Environment=SEEKARA_STATUS_PUBLIC_HOST=13.140.151.124
Environment=SEEKARA_STATUS_APPS=beacon,capsule,seekdesk
ExecStart=/usr/bin/python3 $DIR/agent.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable seekara-status-agent.service
systemctl restart seekara-status-agent.service

if command -v ufw >/dev/null 2>&1; then
  ufw allow "$PORT"/tcp || true
fi

echo
echo "Installed Seekara Status Agent"
echo "  URL: http://13.140.151.124:$PORT/status"
echo "  Check: curl http://127.0.0.1:$PORT/status"
echo "  Service: systemctl status seekara-status-agent"
