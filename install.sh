#!/usr/bin/env bash
# cctv-ce-agent installer — curl | bash bootstrap.
#
# Usage (secrets/IDs passed as env, NEVER committed):
#   curl -fsSL https://raw.githubusercontent.com/thebusted/cctv-ce-agent/main/install.sh \
#     | sudo API_KEY=xxx SERVER_ID=songkhla1 INGEST_URL=https://YOUR-CE-HOST/api/v1/camera-ce bash
#
# Required env:  SERVER_ID
# Recommended:   API_KEY, INGEST_URL   (omit INGEST_URL to run in dry-run/stdout mode)
# Optional:      AWS_PROBE_HOST, AWS_PROBE_PORT, PING_COUNT, PING_INTERVAL_MS, RUN_EVERY
set -euo pipefail

REPO_RAW="https://raw.githubusercontent.com/thebusted/cctv-ce-agent/main"
INSTALL_DIR="/opt/cctv-ce-agent"
CONF_DIR="/etc/cctv-ce"
RUN_EVERY="${RUN_EVERY:-*:0/10}"   # systemd OnCalendar: every 10 min

[ "$(id -u)" -eq 0 ] || { echo "run as root (sudo) — needs apt + raw sockets"; exit 1; }
: "${SERVER_ID:?set SERVER_ID, e.g. SERVER_ID=songkhla1}"

echo "[1/5] deps"
apt-get update -qq
apt-get install -y fping hping3 conntrack python3 curl
# per-flow byte accounting for per-camera TX (best-effort)
sysctl -w net.netfilter.nf_conntrack_acct=1 >/dev/null 2>&1 || true

echo "[2/5] agent -> $INSTALL_DIR"
mkdir -p "$INSTALL_DIR" "$CONF_DIR"
curl -fsSL "$REPO_RAW/agent.py" -o "$INSTALL_DIR/agent.py"
chmod 755 "$INSTALL_DIR/agent.py"

echo "[3/5] config -> $CONF_DIR/.env (chmod 600, not in repo)"
cat > "$CONF_DIR/.env" <<EOF
SERVER_ID=${SERVER_ID}
API_KEY=${API_KEY:-}
INGEST_URL=${INGEST_URL:-}
CAMERAS_FILE=${CONF_DIR}/cameras.csv
AWS_PROBE_HOST=${AWS_PROBE_HOST:-s3.ap-southeast-1.amazonaws.com}
AWS_PROBE_PORT=${AWS_PROBE_PORT:-443}
PING_COUNT=${PING_COUNT:-100}
PING_INTERVAL_MS=${PING_INTERVAL_MS:-200}
COLLECT_TX=${COLLECT_TX:-1}
EOF
chmod 600 "$CONF_DIR/.env"
# camera list: keep existing if present, else drop the example for the operator to fill
if [ ! -f "$CONF_DIR/cameras.csv" ]; then
  curl -fsSL "$REPO_RAW/cameras.example.csv" -o "$CONF_DIR/cameras.csv"
  echo "    -> edit $CONF_DIR/cameras.csv with real camera ids/IPs"
fi

echo "[4/5] systemd unit + timer"
cat > /etc/systemd/system/cctv-ce.service <<EOF
[Unit]
Description=cctv-ce-agent per-camera CE collector
After=network-online.target
[Service]
Type=oneshot
EnvironmentFile=${CONF_DIR}/.env
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/agent.py
User=root
EOF
cat > /etc/systemd/system/cctv-ce.timer <<EOF
[Unit]
Description=Run cctv-ce-agent on a schedule
[Timer]
OnCalendar=${RUN_EVERY}
Persistent=true
[Install]
WantedBy=timers.target
EOF

echo "[5/5] enable"
systemctl daemon-reload
systemctl enable --now cctv-ce.timer
echo "done. test now:  sudo systemctl start cctv-ce.service && journalctl -u cctv-ce -n 30 --no-pager"
echo "dry-run:        sudo env \$(grep -v '^#' $CONF_DIR/.env | xargs) INGEST_URL= python3 $INSTALL_DIR/agent.py"
