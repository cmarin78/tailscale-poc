"""Helios observability — metrics + access logs aggregator.

This service is what Nina (the auditor) reads to do her job. It's also what
SRE uses to monitor everything. The endpoint structure mimics Prometheus
text format loosely — enough to be readable by humans, not a real Prom server.

Note: this service can be reached via Tailscale Funnel in prod to share
metrics with external vendors / status pages. In the POC it's tailnet-only.
"""

import json
import random
import socket
import time

from flask import Flask, jsonify, request

app = Flask(__name__)


# Mock access log — in prod this would be populated by tailnet logs / Prom
# metrics / structured logs from all services.
ACCESS_LOG = []


@app.before_request
def log_request():
    ACCESS_LOG.append({
        "timestamp": time.time(),
        "method": request.method,
        "path": request.path,
        "src_ip": request.remote_addr,
        "src_user": request.headers.get("Tailscale-User-Login", "anonymous"),
        "user_agent": request.headers.get("User-Agent", "unknown"),
    })


@app.get("/")
def index():
    return jsonify({
        "service": "helios-observability",
        "host": socket.gethostname(),
        "endpoints": [
            "GET /metrics — Prometheus-style metrics",
            "GET /access-log — JSON of recent requests",
            "GET /healthz",
        ],
        "reachable_by": [
            "sre (operate)",
            "sre-lead (operate)",
            "auditors (read-only via grants)",
        ],
        "note": (
            "Auditors reach this via the 'auditors' grant that wraps the whole "
            "service — they get observability.read app capability but no SSH."
        ),
    })


@app.get("/healthz")
def healthz():
    return jsonify({"status": "healthy"})


@app.get("/metrics")
def metrics():
    """Prometheus-style text exposition."""
    lines = [
        "# HELP helios_requests_total Total HTTP requests across all services",
        "# TYPE helios_requests_total counter",
        f"helios_requests_total {len(ACCESS_LOG)}",
        "",
        "# HELP helios_node_up 1 if the tailnet node is connected",
        "# TYPE helios_node_up gauge",
        "helios_node_up{node=\"admin-portal\"} 1",
        "helios_node_up{node=\"identity-bridge\"} 1",
        "helios_node_up{node=\"api-gateway\"} 1",
        "helios_node_up{node=\"primary-db\"} 1",
        "helios_node_up{node=\"warehouse-db\"} 1",
        "helios_node_up{node=\"ml-platform\"} 1",
        "",
        "# HELP helios_db_pool_active Active DB connections",
        "# TYPE helios_db_pool_active gauge",
        f"helios_db_pool_active{{db=\"primary\"}} {random.randint(2, 8)}",
        f"helios_db_pool_active{{db=\"warehouse\"}} {random.randint(1, 4)}",
    ]
    return ("\n".join(lines), 200, {"Content-Type": "text/plain; version=0.0.4"})


@app.get("/access-log")
def access_log():
    """Recent access events. Audit-relevant."""
    return jsonify({
        "window_seconds": 3600,
        "events": ACCESS_LOG[-100:],  # last 100
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9100)
