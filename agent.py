#!/usr/bin/env python3
"""
cctv-ce-agent — per-camera link-quality CE collector for CCTV servers.

Measures, per run:
  - per-camera PDR (packet delivery ratio) via fping        -> CE = -ln(PDR) -> group 1..4
  - egress link CE to AWS (TCP SYN, not ICMP) via hping3     -> gate for 4750/500 feasibility
  - per-camera TX bytes via conntrack (best-effort)          -> feeds cost model

Then POSTs one JSON payload to INGEST_URL (Bearer auth). If INGEST_URL is empty,
prints the payload to stdout (dry-run / local testing).

ALL config comes from environment (see .env.example). No secrets, IPs, or hosts
are baked into this file.

CE math is identical to the team standard (Robin Dey framework / RIC-241):
    CE = -ln(PDR),  PDR clamped to [EPSILON, 1.0]
Groups (link quality):
    1: CE < 0.5   (PDR > 0.61)   excellent
    2: 0.5-1.0                    good
    3: 1.0-1.5                    medium
    4: CE >= 1.5  (PDR <= 0.22)   poor
"""
import csv
import json
import math
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

EPSILON = 1e-10


def env(key, default=None, required=False):
    val = os.environ.get(key, default)
    if required and not val:
        sys.exit(f"[cctv-ce-agent] missing required env: {key}")
    return val


def ce_from_pdr(pdr):
    pdr = min(max(pdr, EPSILON), 1.0)
    return -math.log(pdr) + 0.0  # +0.0 normalizes -0.0 (PDR=1.0) to 0.0


def ce_group(ce):
    if ce < 0.5:
        return 1
    if ce < 1.0:
        return 2
    if ce < 1.5:
        return 3
    return 4


def run(cmd, timeout):
    """Run a command, return combined stdout+stderr text (never raises)."""
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        return (p.stdout or "") + (p.stderr or "")
    except Exception as exc:  # noqa: BLE001 - best-effort probe
        return f"__ERROR__ {exc}"


def measure_camera_pdr(ip, count, interval_ms):
    """fping -> packet delivery ratio. Returns (pdr, avg_rtt_ms) or (None, None)."""
    out = run(
        ["fping", "-c", str(count), "-p", str(interval_ms), "-q", ip],
        timeout=count * (interval_ms / 1000.0) + 15,
    )
    # fping -q line: "IP : xmt/rcv/%loss = 100/98/2%, min/avg/max = 0.1/0.5/2.0"
    m = re.search(r"xmt/rcv/%loss\s*=\s*\d+/\d+/(\d+)%", out)
    if not m:
        return None, None
    loss_pct = int(m.group(1))
    pdr = 1.0 - loss_pct / 100.0
    rtt = re.search(r"min/avg/max\s*=\s*[\d.]+/([\d.]+)/[\d.]+", out)
    return pdr, (float(rtt.group(1)) if rtt else None)


def measure_egress(host, port, count, interval_us):
    """hping3 TCP SYN -> loss + RTT. Needs root (raw socket)."""
    out = run(
        ["hping3", "-S", "-p", str(port), "-c", str(count),
         "-i", f"u{interval_us}", "-q", host],
        timeout=count * (interval_us / 1_000_000.0) + 20,
    )
    loss = re.search(r"(\d+)% packet loss", out)
    rtt = re.search(r"round-trip min/avg/max\s*=\s*[\d.]+/([\d.]+)/([\d.]+)\s*ms", out)
    if not loss:
        return None
    pdr = 1.0 - int(loss.group(1)) / 100.0
    avg = float(rtt.group(1)) if rtt else None
    mx = float(rtt.group(2)) if rtt else None
    ce = ce_from_pdr(pdr)
    return {
        "host": host, "port": int(port), "pdr": round(pdr, 4),
        "ce": round(ce, 4), "group": ce_group(ce),
        "avg_rtt_ms": avg, "jitter_ms": (round(mx - avg, 3) if avg and mx else None),
    }


def camera_tx_bytes(ip):
    """conntrack original-direction bytes for flows from this camera. Best-effort."""
    out = run(["conntrack", "-L", "--src", ip], timeout=10)
    if out.startswith("__ERROR__"):
        return None
    total = 0
    found = False
    for m in re.finditer(r"\bbytes=(\d+)", out):
        total += int(m.group(1))
        found = True
    return total if found else None


def load_cameras(path):
    """CSV: id,ip  (header optional). Lines starting with # ignored."""
    cams = []
    if not path or not os.path.exists(path):
        return cams
    with open(path, newline="") as fh:
        for row in csv.reader(fh):
            if not row or row[0].lstrip().startswith("#"):
                continue
            cid = row[0].strip()
            ip = row[1].strip() if len(row) > 1 else ""
            if cid.lower() in ("id", "camera_id") or not ip:
                continue
            cams.append({"id": cid, "ip": ip})
    return cams


def main():
    server_id = env("SERVER_ID", required=True)
    ingest_url = env("INGEST_URL", "")
    api_key = env("API_KEY", "")
    cameras_file = env("CAMERAS_FILE", "/etc/cctv-ce/cameras.csv")
    count = int(env("PING_COUNT", "100"))
    interval_ms = int(env("PING_INTERVAL_MS", "200"))
    aws_host = env("AWS_PROBE_HOST", "s3.ap-southeast-1.amazonaws.com")
    aws_port = int(env("AWS_PROBE_PORT", "443"))
    collect_tx = env("COLLECT_TX", "1") == "1"

    cams = load_cameras(cameras_file)
    results = []
    for c in cams:
        pdr, rtt = measure_camera_pdr(c["ip"], count, interval_ms)
        entry = {"id": c["id"], "ip": c["ip"]}
        if pdr is None:
            entry.update({"reachable": False, "pdr": None, "ce": None, "group": None})
        else:
            ce = ce_from_pdr(pdr)
            entry.update({
                "reachable": True, "pdr": round(pdr, 4),
                "ce": round(ce, 4), "group": ce_group(ce), "avg_rtt_ms": rtt,
            })
        if collect_tx:
            entry["tx_bytes"] = camera_tx_bytes(c["ip"])
        results.append(entry)

    payload = {
        "server_id": server_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "egress": measure_egress(aws_host, aws_port, max(count, 50),
                                 int(env("EGRESS_INTERVAL_US", "50000"))),
        "camera_count": len(results),
        "cameras": results,
    }

    if not ingest_url:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    req = urllib.request.Request(
        ingest_url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"[cctv-ce-agent] posted {len(results)} cameras -> {resp.status}")
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"[cctv-ce-agent] POST failed: {exc}")


if __name__ == "__main__":
    main()
