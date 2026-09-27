"""Helios customer-portal — frontend for Helios customers.

In prod: served via Tailscale Funnel (HTTPS público) behind identity-aware
proxy. In this POC: serves a mock dashboard that customer-success and
sales-eng use to demonstrate the product to customers.

Note: NOT reached by engineers — even though they have admin access, they
should use admin-portal for that. This is the "DMZ with privileges" rule:
the principal's role determines which UI they get, not just whether they
can technically reach the host.
"""

import socket
from datetime import datetime, timedelta

from flask import Flask, jsonify, request

app = Flask(__name__)


def _now():
    return datetime.utcnow().isoformat() + "Z"


@app.get("/")
def index():
    return jsonify({
        "service": "helios-customer-portal",
        "host": socket.gethostname(),
        "ui_branding": {
            "company": "Helios",
            "tagline": "AP automation for fintechs",
            "primary_color": "#0F4C81",
        },
        "reachable_by": ["customer-success", "sales-eng", "autogroup:admin"],
        "note": (
            "Engineers CAN technically reach this host (it's in the tailnet), "
            "but ACL denies them. The rule enforces UX as much as security: "
            "engineers shouldn't debug customer issues via the customer portal."
        ),
    })


@app.get("/healthz")
def healthz():
    return jsonify({"status": "healthy"})


@app.get("/dashboard")
def dashboard():
    customer_id = request.args.get("customer_id", "cus_001")
    return jsonify({
        "customer_id": customer_id,
        "metrics": {
            "invoices_processed_30d": 1247,
            "auto_categorized_pct": 0.92,
            "avg_processing_time_seconds": 4.2,
            "fraud_blocked_30d": 8,
        },
        "recent_activity": [
            {"timestamp": _now() - timedelta(minutes=5), "event": "invoice_paid", "amount_cents": 12500},
            {"timestamp": _now() - timedelta(minutes=12), "event": "invoice_flagged", "reason": "duplicate"},
            {"timestamp": _now() - timedelta(minutes=18), "event": "invoice_categorized", "category": "office_supplies"},
        ],
    })


@app.get("/whoami")
def whoami():
    """If reached via `tailscale serve`, headers tell us who."""
    login = request.headers.get("Tailscale-User-Login")
    return jsonify({
        "authenticated_via": "tailscale-serve" if login else "none",
        "user_login": login,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9443)
