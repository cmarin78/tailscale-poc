"""Helios POC — Router proxy.

Sirve WebFinger en /.well-known/webfinger (necesario para Tailscale Custom OIDC)
y proxy del resto a Authentik.

Reemplaza el tunnel único de ngrok para que la misma URL sirva ambos backends
con un path-based router.
"""
import os
import urllib.request
import urllib.error
from flask import Flask, jsonify, request, Response

app = Flask(__name__)

OIDC_ISSUER = os.environ.get(
    "OIDC_ISSUER_URL",
    "https://sardine-overact-blast.ngrok-free.dev/application/o/helios-tailnet/",
)
AUTHENTIK_UPSTREAM = os.environ.get("AUTHENTIK_UPSTREAM", "http://authentik-server:9000")


# ----- WebFinger (RFC 7033) -----
@app.get("/.well-known/webfinger")
def webfinger():
    return jsonify({
        "subject": f"acct:cmarin@{OIDC_ISSUER.split('//')[1].split('/')[0]}",
        "aliases": [OIDC_ISSUER],
        "properties": {"https://tailscale.com/issuer": OIDC_ISSUER},
        "links": [
            {
                "rel": "http://openid.net/specs/connect/1.0/issuer",
                "href": OIDC_ISSUER,
            },
        ],
    })


# ----- Reverse proxy everything else to Authentik -----
@app.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@app.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def proxy(path):
    target = f"{AUTHENTIK_UPSTREAM}/{path}"
    if request.query_string:
        target += "?" + request.query_string.decode()

    body = request.get_data()
    headers = {k: v for k, v in request.headers if k.lower() not in ("host", "content-length")}

    req = urllib.request.Request(target, data=body, headers=headers, method=request.method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return Response(
                resp.read(),
                status=resp.status,
                headers=[(k, v) for k, v in resp.headers.items() if k.lower() not in ("transfer-encoding", "connection")],
            )
    except urllib.error.HTTPError as e:
        return Response(
            e.read(),
            status=e.code,
            headers=[(k, v) for k, v in e.headers.items() if k.lower() not in ("transfer-encoding", "connection")],
        )


@app.get("/healthz")
def healthz():
    return jsonify({"status": "healthy", "upstream": AUTHENTIK_UPSTREAM})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7080)
