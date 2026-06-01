#!/usr/bin/env bash
# cctv-ce-agent self-update — refetch agent.py + units, keep .env + cameras.csv.
#   curl -fsSL https://raw.githubusercontent.com/thebusted/cctv-ce-agent/main/update.sh | sudo bash
set -euo pipefail
REPO_RAW="https://raw.githubusercontent.com/thebusted/cctv-ce-agent/main"
INSTALL_DIR="/opt/cctv-ce-agent"

[ "$(id -u)" -eq 0 ] || { echo "run as root (sudo)"; exit 1; }
[ -d "$INSTALL_DIR" ] || { echo "not installed — run install.sh first"; exit 1; }

echo "[1/2] refetch agent.py"
curl -fsSL "$REPO_RAW/agent.py" -o "$INSTALL_DIR/agent.py.new"
mv "$INSTALL_DIR/agent.py.new" "$INSTALL_DIR/agent.py"
chmod 755 "$INSTALL_DIR/agent.py"
python3 -m py_compile "$INSTALL_DIR/agent.py" && echo "    syntax OK"

echo "[2/2] restart timer (config untouched)"
systemctl daemon-reload
systemctl restart cctv-ce.timer
echo "done. version pulled from main. test: sudo systemctl start cctv-ce.service && journalctl -u cctv-ce -n 20 --no-pager"
