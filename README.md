# cctv-ce-agent

Per-camera **link-quality Cross Entropy (CE)** collector for CCTV servers.
Installs in one line, measures each camera's link quality + the egress path to AWS,
and pushes results to a central endpoint. No secrets in this repo — everything is env/variables.

## What it measures

| Metric | How | Why |
|--------|-----|-----|
| per-camera **PDR → CE = -ln(PDR)** → group 1-4 | `fping` per camera IP | classify cameras by link quality for bandwidth shaping |
| **egress CE** (RTSP server → AWS Singapore) | `hping3` TCP SYN :443 | the real bottleneck that gates 4750/500 feasibility |
| per-camera **TX bytes** | `conntrack` per source IP | feeds cost-per-camera / cost-per-request model |
| per-camera **real bitrate + RTP loss** (`RTSP_PROBE=1`) | `ffmpeg` pulls the stream `RTSP_PROBE_SECS` | true Mbps/camera (metadata reports N/A) + video-path loss for recognition |

It does **not** power-cycle cameras — flows are separated by IP, measured live in parallel.

CE groups (link quality): 1 `CE<0.5` (PDR>0.61, excellent) · 2 `0.5-1.0` · 3 `1.0-1.5` · 4 `CE>=1.5` (PDR<=0.22, poor).
Shaping rule: reduce bitrate on **poor** links (CE high — already dropping), keep bitrate
on good links that run face/LPR recognition.

> This CE (link-quality `-ln(PDR)`) is a different quantity from the CE platform's
> traffic-anomaly `H(P,Q)`. Both use a 0.5/1.0 scale — always label which one when reporting.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/thebusted/cctv-ce-agent/main/install.sh \
  | sudo API_KEY=xxx SERVER_ID=songkhla1 INGEST_URL=https://YOUR-CE-HOST/api/v1/camera-ce bash
```

Then fill the camera list and test:

```bash
sudo nano /etc/cctv-ce/cameras.csv          # id,ip per line
sudo systemctl start cctv-ce.service
journalctl -u cctv-ce -n 30 --no-pager
```

Omit `INGEST_URL` to run in **dry-run** mode (prints JSON to stdout, sends nothing).

Enable real per-camera bitrate (needs `rtsp_url` in `cameras.csv`): set `RTSP_PROBE=1` in `/etc/cctv-ce/.env`.

## Update / Uninstall

```bash
# pull latest agent (keeps your .env + cameras.csv)
curl -fsSL https://raw.githubusercontent.com/thebusted/cctv-ce-agent/main/update.sh | sudo bash

# remove everything after the job (PURGE_DEPS=1 also removes fping/hping3/conntrack)
curl -fsSL https://raw.githubusercontent.com/thebusted/cctv-ce-agent/main/uninstall.sh | sudo bash
```

## Config

All via env at install time → written to `/etc/cctv-ce/.env` (chmod 600, gitignored).
See [.env.example](.env.example). Camera IPs live in `/etc/cctv-ce/cameras.csv` (gitignored).

## Push contract

The agent POSTs one JSON payload per run. Endpoint spec for the CE platform:
[INGEST_CONTRACT.md](INGEST_CONTRACT.md).

## Requirements

Ubuntu/Debian host with root (raw sockets). Installer pulls `fping hping3 conntrack python3`.
Python stdlib only — no pip deps.
