"""Helios ml-platform — serves ML models for fraud scoring and categorization.

Two endpoints:
  - /predict/fraud: returns a fraud risk score for an invoice
  - /predict/categorize: returns GL category for a vendor description

This is a mock — in prod would call a real model server (BentoML, TF Serving,
or SageMaker). The point is to test the ACL: sales-eng and CS can predict
(client-facing), data-eng can read for analysis, SRE cannot.
"""

import hashlib
import random
import socket

from flask import Flask, jsonify, request

app = Flask(__name__)


def _deterministic_score(seed: str, low: float = 0.0, high: float = 1.0) -> float:
    """Hash-based deterministic 'prediction' so tests are reproducible."""
    h = hashlib.sha256(seed.encode()).digest()
    return low + (int.from_bytes(h[:4], "big") / 0xFFFFFFFF) * (high - low)


@app.get("/")
def index():
    return jsonify({
        "service": "helios-ml-platform",
        "host": socket.gethostname(),
        "models": ["fraud-scoring-v3", "categorizer-v2"],
        "reachable_by": [
            "data-eng (read)",
            "sales-eng (predict)",
            "customer-success (predict)",
        ],
        "note": (
            "Predictions are deterministic per-input so the verify script "
            "can assert specific values."
        ),
    })


@app.get("/healthz")
def healthz():
    return jsonify({"status": "healthy"})


@app.post("/predict/fraud")
def predict_fraud():
    body = request.get_json(force=True, silent=True) or {}
    invoice_id = body.get("invoice_id", "")
    amount_cents = body.get("amount_cents", 0)
    vendor = body.get("vendor", "")

    if not invoice_id:
        return jsonify({"error": "invoice_id required"}), 400

    seed = f"{invoice_id}:{amount_cents}:{vendor}"
    score = _deterministic_score(seed)

    return jsonify({
        "invoice_id": invoice_id,
        "fraud_score": round(score, 4),
        "risk_band": "high" if score > 0.8 else ("medium" if score > 0.4 else "low"),
        "model_version": "fraud-scoring-v3",
    })


@app.post("/predict/categorize")
def predict_categorize():
    body = request.get_json(force=True, silent=True) or {}
    description = body.get("description", "")

    if not description:
        return jsonify({"error": "description required"}), 400

    seed = description
    cats = ["office_supplies", "software_subscription", "travel", "marketing", "consulting"]
    idx = int(_deterministic_score(seed, 0, len(cats) - 0.01) * len(cats))
    idx = min(idx, len(cats) - 1)

    return jsonify({
        "description": description,
        "category": cats[idx],
        "confidence": round(_deterministic_score(seed + ":conf", 0.5, 1.0), 4),
        "model_version": "categorizer-v2",
    })


@app.get("/models")
def list_models():
    """Data-eng reads this for analysis; sales-eng shouldn't but can't access."""
    return jsonify({
        "models": [
            {"name": "fraud-scoring-v3", "deployed_at": "2026-09-15", "trained_on_rows": 1_240_000},
            {"name": "categorizer-v2", "deployed_at": "2026-08-20", "trained_on_rows": 480_000},
        ],
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8501)
