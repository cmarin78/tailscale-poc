# Helios POC — Identity layer (Google Workspace sim.)

## What this is

This layer simulates a **corporate Google Workspace** inside the POC. It models:

- **Users** with verified identity (`maya.admin@helios.example`)
- **Groups** as the source of truth for ACLs (`group:platform-eng@helios.example`)
- **OIDC provider** that Tailscale/Headscale consumes for SSO

In real production, this layer is replaced 1-to-1 with Google Workspace. The integration with Tailscale is the same (issuer URL, client_id, claims). Only the vendor changes.

## Components

| Component | Version | Function |
|---|---|---|
| [Authentik](https://goauthentik.io/) | 2024.10 | Open-source IdP with an admin UI similar to Google Workspace |
| Postgres | 16-alpine | Authentik backend |
| Redis | 7-alpine | Authentik cache and queue |

## Equivalencies with Google Workspace

| Google Workspace | Helios POC (this) |
|---|---|
| `admin.google.com` → Users | Authentik web UI `http://localhost:9000` |
| `admin.google.com` → Groups | Authentik → Directory → Groups |
| SAML/OIDC app for Tailscale | Authentik → Applications → Providers → OAuth2/OpenID |
| SCIM 2.0 endpoint | Authentik has a SCIM provider (not activated in this POC) |
| `group:eng@domain.com` in policy | Identical: Tailscale receives it via OIDC claims |
| Workspace dynamic groups | Authentik has events but no native "dynamic groups" (workaround: cron + API) |
| MFA enforcement | Authentik supports TOTP/WebAuthn (not activated in this POC) |

## How to use it

```bash
# 1. Bring up the IdP
docker compose -f docker-compose.identity.yml up -d

# 2. Wait for Authentik to be ready (~30-60s the first time)
docker compose -f docker-compose.identity.yml logs -f authentik-server | grep "starting"

# 3. Access the UI
#    http://localhost:9000
#    User: akadmin
#    Pass: akadmin-helios-poc-2026

# 4. Bootstrap (users/groups/OIDC provider)
docker compose -f docker-compose.identity.yml run --rm id-bootstrap

# 5. Configure SSO in Tailscale
#    https://login.tailscale.com/admin/settings/sso
#    Issuer URL: http://localhost:9000/application/o/helios-tailnet/
#    Discovery:  http://localhost:9000/.well-known/openid-configuration
```

## What this setup demonstrates

1. **Real corporate SSO** — employees log in with their Google account (sim. Authentik) and the identity flows to the tailnet.
2. **Groups as policy primitive** — `group:platform-eng@helios.example` is referenced in `acl/policy.hujson` and Tailscale evaluates it.
3. **Granular auditing** — every access is tied to the Google user, not to an auth key.
4. **Identity rotation** — when someone leaves a group in Workspace, the change is reflected in the tailnet on the next poll (~30-60s).

## Simulator limitations

| Limitation | Impact |
|---|---|
| Authentik has no native "dynamic groups" | Groups are static (admin maintains them) |
| MFA not configured in this POC | In prod: required for all engineers |
| No active SCIM sync | Bootstrap is one-shot; rotating users requires re-running `seed.py` |
| HTTPS not configured | In prod: TLS termination mandatory (Let's Encrypt + tailscale serve) |
| No "self-service signup" flow | Appropriate for a company, not for a B2C SaaS |

## Why not Dex/Keycloak

We evaluated 3 alternatives:

- **Dex**: simpler (1 container, config-file driven). But less "real" — no admin UI. Good for K8s, bad for simulating Workspace.
- **Keycloak**: older, heavier. More features but overkill for the POC.
- **Authentik**: wins for realistic UI + clean API + modern OIDC support + blueprints for GitOps.

## Production

When Helios grows, the paths are:

1. **Stay with Authentik** — viable for <500 employees if you have the infra to operate it.
2. **Migrate to Google Workspace** — if the Google contract is already in place. Tailscale has native integration with Google Workspace SSO (deeper than generic OIDC: it syncs groups automatically via SCIM).
3. **Migrate to another IdP** (Okta, Auth0, Microsoft Entra) — Tailscale supports SSO with any of them via OIDC/SAML.

The simulator is enough to **validate the integration pattern**. The choice of IdP vendor is independent.
