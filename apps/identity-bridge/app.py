"""Helios identity-bridge — generic SSO bridge.

In prod, this is the service that responds to a custom auth flow when an IdP
needs to validate against a legacy user store. For Helios it's modeled as a
service that resolves customer logins against the primary-db (legacy_users).

The network-level access is gated by the Tailscale ACL: only
identity-bridge can talk to primary-db.
"""

import json
import os
import socket
import struct
import threading

import boto3
from flask import Flask, jsonify, request
import psycopg

app = Flask(__name__)

SECRET_ID = os.environ.get("SECRETS_MANAGER_SECRET_ID", "helios/poc/secrets")
SECRET_KEY = os.environ.get("PRIMARY_DB_SECRET_KEY", "primary_db")


def _default_gateway_ip():
    """The container has no network of its own (network_mode: service:*), so
    there's no host.docker.internal. MiniStack stands in for AWS's public API,
    reachable through the docker bridge's default gateway — same way a real
    AWS SDK call would leave over the host's internet uplink.
    """
    with open("/proc/net/route") as f:
        for line in f.readlines()[1:]:
            fields = line.split()
            if fields[1] == "00000000" and int(fields[3], 16) & 2:
                return socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))
    return "127.0.0.1"


_secrets_client = boto3.client(
    "secretsmanager",
    endpoint_url=os.environ.get(
        "MINISTACK_ENDPOINT", f"http://{_default_gateway_ip()}:4566"
    ),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
    aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
    aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
)

_dsn_cache = None
_dsn_lock = threading.Lock()


def get_dsn():
    """Lazy + cached fetch of DB creds from MiniStack (Secrets Manager sim).

    Mirrors how this service would reach the real Secrets Manager in production:
    fetch on first use, cache for the lifetime of the process.
    """
    global _dsn_cache
    if _dsn_cache is not None:
        return _dsn_cache
    with _dsn_lock:
        if _dsn_cache is None:
            secret = json.loads(
                _secrets_client.get_secret_value(SecretId=SECRET_ID)["SecretString"]
            )
            db = secret[SECRET_KEY]
            _dsn_cache = (
                f"host={db['host']} port={db['port']} dbname={db['dbname']} "
                f"user={db['username']} password={db['password']}"
            )
        return _dsn_cache


@app.get("/healthz")
def healthz():
    return jsonify({"status": "healthy"})


@app.post("/resolve-legacy-user")
def resolve_legacy_user():
    """Simulates: IdP calls this when a customer tries to log in.

    Looks up email in helios.legacy_users (representing the pre-migration
    auth schema) and returns whether the user exists and what their internal
    ID is. If the IdP gets a hit, the IdP can create the user in the new
    system using the internal ID — classic lazy migration pattern.
    """
    body = request.get_json(force=True, silent=True) or {}
    email = body.get("email")
    if not email:
        return jsonify({"error": "email required"}), 400

    try:
        dsn = get_dsn()
    except Exception as exc:
        return jsonify({"error": f"could not fetch db credentials: {exc}"}), 502

    try:
        with psycopg.connect(dsn, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT user_public_id, email FROM helios.legacy_users WHERE email = %s",
                    (email,),
                )
                row = cur.fetchone()
    except Exception as exc:
        return jsonify({"error": f"could not reach primary-db: {exc}"}), 502

    if row is None:
        return jsonify({"found": False}), 404

    return jsonify({"found": True, "user_public_id": str(row[0]), "email": row[1]})


@app.get("/whoami")
def whoami():
    return jsonify({
        "service": "helios-identity-bridge",
        "host": socket.gethostname(),
        "reachable_via_tailnet": True,
        "notes": (
            "This is the only path to primary-db. ACL denies direct DB access "
            "to anyone — including engineers. Customer success uses this for "
            "login troubleshooting."
        ),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9090)
