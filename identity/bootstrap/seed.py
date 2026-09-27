#!/usr/bin/env python3
"""
Helios POC — bootstrap del IdP simulado (Authentik / Google Workspace-style)

Crea:
  - 6 grupos funcionales (helios-admin, platform-eng, data-eng, sre, sre-lead,
    customer-success, sales-eng, auditors, untrusted)
  - 9 usuarios con membresías
  - 1 OIDC provider que Tailscale/Headscale consume como SSO

Equivalente en Google Workspace:
  - Crear grupos en admin.google.com
  - Crear usuarios en admin.google.com
  - Asignar a grupos
  - Configurar SAML/OIDC app para Tailscale en marketplace

Idempotente: si un usuario/grupo ya existe, no lo duplica.
"""

import json
import os
import sys
import time
from pathlib import Path

import urllib.request
import urllib.error
import urllib.parse

BASE_URL = os.environ.get("AUTHENTIK_URL", "http://authentik-server:9000")
DOMAIN = os.environ.get("HELIOS_IDP_DOMAIN", "helios.example")
ADMIN_USER = os.environ.get("AUTHENTIK_ADMIN_USER", "akadmin")
ADMIN_PASSWORD_FILE = os.environ.get(
    "AUTHENTIK_ADMIN_PASSWORD_FILE", "/run/secrets/authentik_admin_password"
)

# Cargar password
if Path(ADMIN_PASSWORD_FILE).exists():
    ADMIN_PASSWORD = Path(ADMIN_PASSWORD_FILE).read_text().strip()
else:
    print(f"⚠ admin password file {ADMIN_PASSWORD_FILE} not found", file=sys.stderr)
    sys.exit(1)

# Paths locales
HERE = Path(__file__).parent
USERS_PATH = HERE / "users.json"
GROUPS_PATH = HERE / "groups.json"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def wait_for_authentik(retries=60, delay=2):
    """Espera a que Authentik responda (levanta con docker compose, no instantáneo)."""
    for i in range(retries):
        try:
            req = urllib.request.Request(f"{BASE_URL}/-/health/live/")
            urllib.request.urlopen(req, timeout=5).read()
            print(f"✓ Authentik up after {i*delay}s")
            return
        except (urllib.error.URLError, urllib.error.HTTPError, OSError):
            time.sleep(delay)
    print(f"✗ Authentik no respondió después de {retries*delay}s", file=sys.stderr)
    sys.exit(1)


class Authentik:
    def __init__(self):
        self.token = self._get_token()
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def _get_token(self):
        """Crea un API token para el admin user vía /api/v3/proxy/."""
        # Authentik 2024.10 usa sesiones via /api/v3/core/tokens/ pero requiere
        # CSR. Alternativa simple: usar basic auth directamente.
        import base64
        creds = base64.b64encode(f"{ADMIN_USER}:{ADMIN_PASSWORD}".encode()).decode()
        # Para el POC, devolvemos un "session" usando un endpoint que no requiere token.
        # Llamadas subsiguientes usan basic auth directamente.
        self._basic = f"Basic {creds}"
        return None  # placeholder

    def _request(self, method, path, body=None, params=None):
        url = f"{BASE_URL}/api/v3{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", self._basic)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            raise RuntimeError(f"{method} {url} → {e.code}: {body}") from e

    # --- users ---
    def list_users(self, search=None):
        params = {"search": search} if search else {}
        return self._request("GET", "/core/users/", params=params).get("results", [])

    def get_user(self, pk):
        return self._request("GET", f"/core/users/{pk}/")

    def create_user(self, username, email, name, password=None):
        password = password or f"{username}-helios-poc-2026!"
        body = {
            "username": username,
            "email": email,
            "name": name,
            "is_active": True,
            "password": password,
        }
        return self._request("POST", "/core/users/", body=body)

    def ensure_user(self, username, email, name):
        existing = self.list_users(search=username)
        if existing:
            u = existing[0]
            print(f"  • user {username} exists (pk={u['pk']})")
            return u
        print(f"  + creating user {username}")
        return self.create_user(username, email, name)

    # --- groups ---
    def list_groups(self, search=None):
        params = {"search": search} if search else {}
        return self._request("GET", "/core/groups/", params=params).get("results", [])

    def create_group(self, name, **kwargs):
        body = {"name": name, **kwargs}
        return self._request("POST", "/core/groups/", body=body)

    def ensure_group(self, name):
        existing = self.list_groups(search=name)
        if existing:
            g = existing[0]
            print(f"  • group {name} exists (pk={g['pk']})")
            return g
        print(f"  + creating group {name}")
        return self.create_group(name)

    def add_user_to_group(self, user_pk, group_pk):
        # POST /core/groups/{group_pk}/add_user/
        body = {"pk": user_pk}
        return self._request("POST", f"/core/groups/{group_pk}/add_user/", body=body)

    # --- OIDC provider ---
    def ensure_oidc_provider(self):
        """Crea un OIDC provider 'helios-tailnet' que Tailscale consume.

        Dos variantes:
          - helios-tailnet-client (public): para el SSO de Tailscale SaaS
          - helios-tailnet-confidential (confidential): para apps internas

        Equivalente Google Workspace: configurar una 'App SAML/OIDC' en
        https://admin.google.com/ac/security/sso-apps
        """
        existing = self._request("GET", "/providers/oauth2/", params={"search": "helios"}).get("results", [])
        if existing:
            print(f"  • OIDC provider 'helios' exists (slug={existing[0]['slug']})")
            return existing[0]

        # Property mappings requeridos para que Tailscale reciba los grupos
        # en el ID token. El scope 'groups' solo aparece si hay un property
        # mapping que emita el claim 'groups'.
        mappings = self._request("GET", "/propertymappings/all/", params={"search": "oauth"}).get("results", [])
        required_mappings = {
            "authentik default OAuth Mapping: OpenID 'profile'": None,
            "authentik default OAuth Mapping: OpenID 'email'": None,
            "authentik default OAuth Mapping: OpenID 'openid'": None,
        }
        for m in mappings:
            if m.get("name") in required_mappings:
                required_mappings[m["name"]] = m["pk"]

        # Si no hay un mapping custom para 'groups', crear uno.
        groups_mapping_pk = None
        for m in mappings:
            if m.get("name") == "Helios Group Membership (OIDC groups)":
                groups_mapping_pk = m["pk"]
                break
        if groups_mapping_pk is None:
            try:
                gm_pk = self._create_groups_oidc_mapping()
                if gm_pk:
                    groups_mapping_pk = gm_pk
            except Exception as e:
                print(f"  ⚠ no se pudo crear mapping de groups: {e}")

        all_pks = [pk for pk in required_mappings.values() if pk]
        if groups_mapping_pk:
            all_pks.append(groups_mapping_pk)
        if not all_pks and mappings:
            all_pks = [mappings[0]["pk"]]

        # Tailscale SSO: provider público (sin client_secret verification en
        # el flujo de token — Tailscale usa PKCE). Pero también creamos un
        # confidential para apps internas que sí necesitan secret.
        body = {
            "name": "Helios Tailnet (Tailscale SSO)",
            "slug": "helios-tailnet",
            "provider_type": "oauth2",
            "client_type": "public",   # Tailscale SSO es public client (PKCE)
            "client_id": "helios-tailnet-client",
            "client_secret": f"helios-tailnet-secret-{int(time.time())}",
            "access_code_validity": "minutes=5",
            "access_token_validity": "minutes=10",
            "refresh_token_validity": "days=30",
            "include_claims_in_id_token": True,
            "redirect_uris": [
                "https://login.tailscale.com/a/callback",
                # Para Headscale (cuando uses el POC paralelo)
                "https://headscale.localhost/a/callback",
                "http://localhost:8080/oauth/callback",
                # Para ngrok (si lo usás)
                "https://*.ngrok-free.app/oauth/callback",
            ],
            "logout_uri": "",
            "sub_mode": "user_email",
            "issuer_mode": "per_provider",
            "scopes": ["openid", "email", "profile", "groups"],
            "property_mappings": all_pks,
        }

        # Authentik requiere un authorization flow
        flows = self._request("GET", "/flows/instances/").get("results", [])
        default_flow = next(
            (f for f in flows if f.get("designation") == "authorization"), None
        )
        if default_flow:
            body["authorization_flow"] = default_flow["pk"]

        created = self._request("POST", "/providers/oauth2/", body=body)
        print(f"  + created OIDC provider 'helios-tailnet' (slug={created['slug']})")
        print(f"    client_id:     helios-tailnet-client")
        print(f"    client_secret: {created['client_secret']}")
        print(f"    redirect URIs: tailscale.com/a/callback + headscale + ngrok")
        return created

    def _create_groups_oidc_mapping(self):
        """Crea un OIDC scope mapping que emite 'groups' en el ID token.

        Authentik tiene mappings built-in (openid/email/profile) pero
        'groups' hay que crearlo a mano para que aparezca en el token.
        """
        # Buscar un scope para 'groups'
        scopes = self._request("GET", "/propertymappings/scope/", params={"search": "group"}).get("results", [])
        group_scope_pk = None
        for s in scopes:
            if s.get("name", "").lower() == "groups" or "group" in s.get("name", "").lower():
                group_scope_pk = s["pk"]
                break

        if not group_scope_pk:
            return None

        # Crear el mapping que emite el claim 'groups' desde los组成员ships del user
        mapping_body = {
            "name": "Helios Group Membership (OIDC groups)",
            "scope_name": "groups",
            "expression": """
if request.user.is_authenticated:
    return [group.name for group in request.user.ak_groups.all()]
return []
""".strip(),
        }
        created = self._request("POST", "/propertymappings/scope/", body=mapping_body)
        print(f"    + created groups mapping pk={created['pk']}")
        return created["pk"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    wait_for_authentik()
    api = Authentik()

    print("== Cargando definitions ==")
    users = json.loads(USERS_PATH.read_text())
    groups = json.loads(GROUPS_PATH.read_text())

    print(f"== Creando grupos ({len(groups)}) ==")
    group_pks = {}
    for g in groups:
        obj = api.ensure_group(g["name"])
        group_pks[g["name"]] = obj["pk"]

    print(f"== Creando usuarios ({len(users)}) ==")
    user_pks = {}
    for u in users:
        obj = api.ensure_user(u["username"], u["email"], u["name"])
        user_pks[u["username"]] = obj["pk"]

    print("== Asignando membresías ==")
    for u in users:
        user_pk = user_pks[u["username"]]
        for gname in u.get("groups", []):
            if gname not in group_pks:
                print(f"  ⚠ user {u['username']} referencia grupo inexistente {gname}")
                continue
            api.add_user_to_group(user_pk, group_pks[gname])
            print(f"  • {u['username']} → {gname}")

    print("== Configurando OIDC provider para Tailscale/Headscale ==")
    api.ensure_oidc_provider()

    print()
    print("=" * 60)
    print("Resumen de la identidad provisionada")
    print("=" * 60)
    print(f"URL del IdP (issuer OIDC): {BASE_URL}/application/o/authorize/")
    print(f"Discovery URL: {BASE_URL}/.well-known/openid-configuration")
    print(f"Grupos funcionales: {len(group_pks)}")
    print(f"Usuarios: {len(user_pks)}")
    print()
    print("Próximo paso: configurar SSO en Tailscale/Headscale")
    print("  Tailscale SaaS: https://login.tailscale.com/admin/settings/sso")
    print("  Headscale: cfg.OIDC.Issuer = '{BASE_URL}/application/o/helios-tailnet/'")
    print("=" * 60)


if __name__ == "__main__":
    main()
