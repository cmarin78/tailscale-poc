"""Helios eks-gateway — three independent resources on one node.

Simulates the EKS pattern: a single "gateway" node fronts three
independently-accessible resources (metrics, logs, exec). The Tailscale
ACL scopes access PER PORT, so SRE can read metrics+logs but not exec,
while SRE-lead gets exec too. Auditors get metrics only.

This is the strongest demonstration in the POC of "grant exactly the
capability needed, nothing else" applied to a non-trivial backend.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RESOURCES = {
    9100: {
        "resource": "metrics",
        "sample": {
            "cluster": "helios-staging",
            "nodes": 3,
            "pods": 42,
            "cpu_pct_avg": 23.5,
            "mem_mb_avg": 1820,
            "network_mbps": 12.4,
        },
    },
    9101: {
        "resource": "logs",
        "sample": [
            "2026-09-26T00:00:00Z INFO  api-gateway: request_id=abc123 status=200 latency_ms=42",
            "2026-09-26T00:00:01Z INFO  api-gateway: request_id=abc124 status=200 latency_ms=38",
            "2026-09-26T00:00:02Z WARN  identity-bridge: legacy_user_lookup_slow duration_ms=820",
            "2026-09-26T00:00:03Z INFO  warehouse-job: aggregated 1247 rows in 4.2s",
            "2026-09-26T00:00:04Z ERROR ml-platform: prediction_timeout input_id=inv_998",
        ],
    },
    9102: {
        "resource": "exec",
        "sample": {
            "note": (
                "Would open a shell into a pod. POC only echoes the request "
                "so a denied ACL doesn't crash the server."
            ),
            "would_run": "kubectl exec -it <pod> -- /bin/sh",
        },
    },
}


def make_handler(port):
    payload = RESOURCES[port]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass  # silence

    return Handler


if __name__ == "__main__":
    servers = [ThreadingHTTPServer(("0.0.0.0", port), make_handler(port)) for port in RESOURCES]
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"eks-gateway listening on ports {list(RESOURCES.keys())}")
    threading.Event().wait()
