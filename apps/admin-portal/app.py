"""Helios admin-portal — internal admin UI for ops + support.

Reads Tailscale-User-* headers when reached via `tailscale serve`.
This is the "what should be visible only to platform-eng" surface.
"""

import socket

from flask import Flask, jsonify, request

app = Flask(__name__)


@app.get("/")
def index():
    return jsonify({
        "service": "helios-admin-portal",
        "status": "ok",
        "host": socket.gethostname(),
        "note": (
            "Visible only to platform-eng via ACL. If you're here, your Google "
            "group (platform-eng@helios.example) gave you access. Otherwise the "
            "tailnet would have rejected this connection."
        ),
    })


@app.get("/healthz")
def healthz():
    return jsonify({"status": "healthy"})


@app.get("/whoami")
def whoami():
    """Return who is on the other side, based on Tailscale-User-* headers.

    These headers are injected by `tailscale serve` when the user reaches
    the app via https://admin-portal.<tailnet>.ts.net. If you reach the app
    directly (bypassing serve), the headers are absent.
    """
    login = request.headers.get("Tailscale-User-Login")
    name = request.headers.get("Tailscale-User-Name")
    groups_raw = request.headers.get("Tailscale-User-Groups", "")

    if login:
        return jsonify({
            "authenticated_via": "tailscale-serve",
            "user_login": login,
            "user_name": name,
            "user_groups": [g for g in groups_raw.split(",") if g],
        })

    return jsonify({
        "authenticated_via": "none",
        "note": (
            "No Tailscale-User-* headers — request came directly to this port "
            "(not via tailscale serve). Tailnet ACL still gates access; this "
            "just means no identity-aware proxying."
        ),
    })


@app.get("/api/customers")
def list_customers():
    """Mock customer list. In prod, would call primary-db via internal-db creds."""
    return jsonify({
        "customers": [
            {"id": "cus_001", "name": "Acme Capital", "tier": "enterprise", "mrr": 12000},
            {"id": "cus_002", "name": "Banc Genial", "tier": "growth", "mrr": 4500},
            {"id": "cus_003", "name": "Northstar Pay", "tier": "enterprise", "mrr": 18000},
        ],
        "note": "Read via tag:admin-portal → primary-db. Direct DB access denied by ACL.",
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
