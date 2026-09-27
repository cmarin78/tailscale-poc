"""Helios api-gateway — customer-facing B2B API.

In prod: serves customers' integrations (REST + webhooks). In this POC:
mock endpoints that respond based on the auth context.

The interesting bit: customers reach this via tag:customer-portal (their
portal frontend) or directly via API key. Either way, tailnet ACL gates
who can call it (no anonymous API access — auth required at the app layer).
"""

import os
import socket

from flask import Flask, jsonify, request

app = Flask(__name__)


@app.get("/")
def index():
    return jsonify({
        "service": "helios-api-gateway",
        "version": "v1",
        "host": socket.gethostname(),
        "endpoints": [
            "GET /v1/invoices",
            "POST /v1/invoices",
            "GET /v1/customers/{id}",
            "POST /v1/webhooks",
        ],
        "note": (
            "Reached by: customer-portal (frontend), sales-eng (demos), "
            "platform-eng (ops). NOT by data-eng or sre."
        ),
    })


@app.get("/healthz")
def healthz():
    return jsonify({"status": "healthy"})


@app.get("/v1/invoices")
def list_invoices():
    return jsonify({
        "invoices": [
            {"id": "inv_001", "amount_cents": 12500, "status": "paid", "customer_id": "cus_001"},
            {"id": "inv_002", "amount_cents": 49900, "status": "pending", "customer_id": "cus_001"},
            {"id": "inv_003", "amount_cents": 2400, "status": "paid", "customer_id": "cus_002"},
        ],
        "next_cursor": None,
    })


@app.get("/v1/customers/<customer_id>")
def get_customer(customer_id):
    return jsonify({
        "id": customer_id,
        "name": "Acme Capital",
        "tier": "enterprise",
        "mrr_cents": 1200000,
        "created_at": "2024-01-15T00:00:00Z",
    })


@app.post("/v1/webhooks")
def register_webhook():
    body = request.get_json(force=True, silent=True) or {}
    return jsonify({
        "webhook_id": "whk_" + os.urandom(8).hex(),
        "url": body.get("url"),
        "events": body.get("events", []),
        "status": "registered",
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8443)
