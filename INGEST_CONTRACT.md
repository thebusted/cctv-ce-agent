# Ingest contract — `POST /api/v1/camera-ce`

For Jesther to add on the CE platform (`go-thailand/CE`). The agent is push-mode and
ingest-agnostic: point `INGEST_URL` at any endpoint that accepts this contract.

## Request

`POST {INGEST_URL}` · `Authorization: Bearer {API_KEY}` · `Content-Type: application/json`

```json
{
  "server_id": "songkhla1",
  "ts": "2026-05-29T07:10:00+00:00",
  "egress": {
    "host": "s3.ap-southeast-1.amazonaws.com",
    "port": 443,
    "pdr": 0.995,
    "ce": 0.005,
    "group": 1,
    "avg_rtt_ms": 28.4,
    "jitter_ms": 3.1
  },
  "camera_count": 40,
  "cameras": [
    {"id": "CAM-001", "ip": "<ip>", "reachable": true,
     "pdr": 0.99, "ce": 0.0101, "group": 1, "avg_rtt_ms": 0.6, "tx_bytes": 1234567},
    {"id": "CAM-002", "ip": "<ip>", "reachable": false,
     "pdr": null, "ce": null, "group": null, "tx_bytes": null}
  ]
}
```

`ce = -ln(PDR)` (natural log) · group: 1 `<0.5` · 2 `0.5-1.0` · 3 `1.0-1.5` · 4 `>=1.5`
(same formula as Robin Dey framework / RIC-241 — link quality, NOT the platform's
H(P,Q) traffic-anomaly CE; keep the two clearly separated in storage + UI).

## Suggested storage (new tables, do not reuse `bandwidth_metrics`)

- `camera_ce(ts, server_id, camera_id, ip, pdr, ce, ce_group, avg_rtt_ms, tx_bytes)`
  — PK `(ts, server_id, camera_id)`
- `egress_ce(ts, server_id, host, port, pdr, ce, ce_group, avg_rtt_ms, jitter_ms)`

## Response

`200 {"accepted": <n>}` on success. Non-2xx → agent logs + exits non-zero (systemd retry).
