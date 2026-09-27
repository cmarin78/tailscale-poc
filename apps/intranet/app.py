"""Helios Intranet — portal interno corporativo.

Simula la intranet de una empresa B2B SaaS:
  - Home con links a servicios internos
  - Sección de "engineering" (visible a engineers)
  - Sección de "operations" (visible a SRE)
  - Sección de "people" (visible a todos)

El acceso a cada sección se evalúa contra el grupo Google del usuario (via
header `Tailscale-User-Groups` que inyecta `tailscale serve` cuando el
usuario llega via https://intranet.<tailnet>.ts.net).

Sin esos headers (acceso directo al container), la app asume "anonymous"
y muestra solo la home.
"""

import os
import socket
from flask import Flask, jsonify, request

app = Flask(__name__)


def get_user_groups() -> list[str]:
    """Lee grupos del header Tailscale-User-Groups (comma-separated)."""
    raw = request.headers.get("Tailscale-User-Groups", "")
    return [g.strip() for g in raw.split(",") if g.strip()]


def get_user_login() -> str | None:
    return request.headers.get("Tailscale-User-Login")


@app.get("/")
def index():
    user = get_user_login()
    return jsonify({
        "service": "helios-intranet",
        "host": socket.gethostname(),
        "user": user,
        "message": (
            f"Hola {user}" if user
            else "Hola visitante (no veo headers Tailscale-User-* — llegaste sin `tailscale serve`)"
        ),
        "links": [
            {"name": "Admin Portal",       "url": "http://admin-portal:8080",    "visible_to": "platform-eng"},
            {"name": "API Gateway",        "url": "http://api-gateway:8443",     "visible_to": "platform-eng"},
            {"name": "Customer Portal",    "url": "http://customer-portal:9443", "visible_to": "customer-success,sales-eng"},
            {"name": "Grafana",            "url": "http://grafana:3000",         "visible_to": "sre,sre-lead,platform-eng"},
            {"name": "Observability",      "url": "http://observability:9100",   "visible_to": "sre,sre-lead"},
            {"name": "ML Platform",        "url": "http://ml-platform:8501",     "visible_to": "data-eng,sales-eng,customer-success"},
            {"name": "Warehouse DB",       "url": "postgres://warehouse-db:5432","visible_to": "data-eng"},
            {"name": "Identity Bridge",    "url": "http://identity-bridge:9090", "visible_to": "platform-eng,customer-success"},
        ],
        "policy_note": (
            "Esta intranet está detrás del tailnet. Los links solo funcionan si la ACL "
            "permite al usuario llegar al servicio. Aunque el link esté en el HTML, "
            "Tailscale filtra al nivel de red."
        ),
    })


@app.get("/healthz")
def healthz():
    return jsonify({"status": "healthy"})


@app.get("/whoami")
def whoami():
    """Detalle del usuario actual (extraído de headers Tailscale-User-*)."""
    return jsonify({
        "user": get_user_login(),
        "name": request.headers.get("Tailscale-User-Name"),
        "profile_pic": request.headers.get("Tailscale-User-Profile-Pic"),
        "groups": get_user_groups(),
        "tailnet_ip": request.headers.get("X-Forwarded-For", request.remote_addr),
        "authenticated_via": "tailscale-serve" if get_user_login() else "none",
    })


@app.get("/engineering")
def engineering():
    """Sección de engineering — solo visible para engineers."""
    groups = get_user_groups()
    allowed = [g for g in groups if g in ("platform-eng", "data-eng", "sre", "sre-lead")]

    if not allowed:
        return jsonify({
            "error": "forbidden",
            "message": "Esta sección es solo para engineering team.",
            "your_groups": groups,
        }), 403

    return jsonify({
        "section": "engineering",
        "your_groups": groups,
        "engineering_groups": allowed,
        "content": {
            "deploys_today": 12,
            "incidents_open": 0,
            "p1_bugs": 2,
            "next_sprint": "Sprint 42 — focus on Tailscale MDM rollout",
            "links": {
                "grafana": "http://grafana:3000",
                "runbook": "https://wiki.helios.example/runbooks",
                "oncall_rotation": "https://wiki.helios.example/oncall",
            },
        },
    })


@app.get("/people")
def people():
    """Sección pública — directorio de la empresa."""
    return jsonify({
        "section": "people",
        "directory": [
            {"name": "Maya",   "team": "platform-eng",   "role": "admin",     "status": "online"},
            {"name": "Diego",  "team": "platform-eng",   "role": "engineer",  "status": "online"},
            {"name": "Rafa",   "team": "data-eng",       "role": "engineer",  "status": "away"},
            {"name": "Sam",    "team": "sre",            "role": "engineer",  "status": "online"},
            {"name": "Lena",   "team": "sre-lead",       "role": "lead",      "status": "offline"},
            {"name": "Carla",  "team": "customer-success","role": "cs",       "status": "online"},
            {"name": "Tomás",  "team": "sales-eng",      "role": "se",        "status": "online"},
            {"name": "Nina",   "team": "auditors",       "role": "external",  "status": "offline"},
        ],
    })


@app.get("/admin-tools")
def admin_tools():
    """Sección de admin tools — solo admins."""
    groups = get_user_groups()
    is_admin = "admins" in groups or "helios-admin" in groups or "autogroup:admin" in groups

    if not is_admin:
        return jsonify({
            "error": "forbidden",
            "message": "Solo helios-admin puede acceder.",
        }), 403

    return jsonify({
        "section": "admin-tools",
        "tools": [
            {"name": "tailnet-audit",   "description": "Ver todos los devices en el tailnet con sus tags"},
            {"name": "policy-editor",   "description": "Modificar policy.hujson y aplicarla"},
            {"name": "user-provisioner","description": "Crear/deshabilitar usuarios en Authentik"},
            {"name": "backup-restore",  "description": "Backup de la DB de Headscale"},
        ],
    })


# ----- WebFinger for Tailscale Custom OIDC discovery -----
@app.get("/.well-known/webfinger")
def webfinger():
    """WebFinger endpoint required by Tailscale Custom OIDC integration.

    Returns the OIDC issuer URL so Tailscale can discover Authentik's
    OpenID Connect endpoints.
    """
    issuer = (
        os.environ.get("OIDC_ISSUER_URL")
        or "https://sardine-overact-blast.ngrok-free.dev/application/o/helios-tailnet/"
    )
    # RFC 7033 WebFinger response
    return jsonify({
        "subject": f"acct:cmarin@{issuer.split('//')[1].split('/')[0]}",
        "aliases": [issuer],
        "properties": {
            "https://tailscale.com/issuer": issuer,
        },
        "links": [
            {
                "rel": "http://openid.net/specs/connect/1.0/issuer",
                "href": issuer,
            },
        ],
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7000)
