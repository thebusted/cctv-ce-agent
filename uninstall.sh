#!/usr/bin/env bash
# cctv-ce-agent uninstall — remove everything this agent installed.
#   curl -fsSL https://raw.githubusercontent.com/thebusted/cctv-ce-agent/main/uninstall.sh | sudo bash
# Optional: PURGE_DEPS=1 also apt-removes fping/hping3/conntrack (off by default — shared tools).
set -euo pipefail
INSTALL_DIR="/opt/cctv-ce-agent"
CONF_DIR="/etc/cctv-ce"

[ "$(id -u)" -eq 0 ] || { echo "run as root (sudo)"; exit 1; }

echo "[1/4] stop + disable timer/service"
systemctl disable --now cctv-ce.timer 2>/dev/null || true
systemctl stop cctv-ce.service 2>/dev/null || true

echo "[2/4] remove systemd units"
rm -f /etc/systemd/system/cctv-ce.service /etc/systemd/system/cctv-ce.timer
systemctl daemon-reload

echo "[3/4] remove agent + config (incl. .env, cameras.csv)"
rm -rf "$INSTALL_DIR" "$CONF_DIR"

echo "[4/4] deps"
if [ "${PURGE_DEPS:-0}" = "1" ]; then
  apt-get remove -y fping hping3 conntrack >/dev/null 2>&1 || true
  echo "    removed fping/hping3/conntrack"
else
  echo "    kept fping/hping3/conntrack (shared). PURGE_DEPS=1 to remove."
fi
# conntrack acct sysctl is runtime-only (resets on reboot) — left as-is, harmless.
echo "done. cctv-ce-agent fully removed."
