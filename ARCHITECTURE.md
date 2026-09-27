# Helios POC — Architecture

Technical document: how the pieces connect, what decisions were made in the code, and where the extension points are.

## Layers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Identity layer (Authentik / Google Workspace)                              │
│  - 9 users in helios.example                                               │
│  - 6 functional groups                                                     │
│  - 1 OIDC provider for Tailscale/Headscale                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ OIDC discovery
                                    │ (issuer URL, JWKS, userinfo)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Tailscale control plane (SaaS in this POC)                                │
│  - 1 HuJSON policy with 10 tags, 6 groups, grants, SSH, autoApprovers      │
│  - 1 set of auth keys (reusable, pre-tagged for services)                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ WireGuard + Noise protocol
                                    │
            ┌───────────────────────┴───────────────────────┐
            │                                               │
            ▼                                               ▼
  ┌──────────────────────┐                      ┌──────────────────────┐
  │  Services with tag   │                      │  Personas (user-     │
  │  (preauth key with   │                      │  owned nodes)        │
  │   tag:X)             │                      │  (preauth key with-  │
  │                      │                      │   out tag, SSO login │
  │  - admin-portal      │                      │   in prod)           │
  │  - identity-bridge   │                      │                      │
  │  - api-gateway       │                      │  - diego (platform)  │
  │  - customer-portal   │                      │  - rafa (data)       │
  │  - primary-db        │                      │  - sam (sre)         │
  │  - warehouse-db      │                      │  - lena (sre-lead)   │
  │  - ml-platform       │                      │  - carla (cs)        │
  │  - warehouse-job     │                      │  - tomas (sales)     │
  │  - observability     │                      │  - nina (auditor)    │
  │  - eks-gateway       │                      │  - eve (attacker)    │
  └──────────────────────┘                      └──────────────────────┘
            │                                               │
            └───────────────────────┬───────────────────────┘
                                    │
                                    │ policy.hujson evaluates each flow
                                    ▼
                          ┌────────────────────┐
                          │  Allow / Deny      │
                          └────────────────────┘
```

## End-to-end flow (example)

**Scenario:** Diego (platform-eng) wants to read `/healthz` from `admin-portal`.

1. Diego runs `docker compose exec diego-platform curl http://admin-portal:8080/healthz`.
2. The curl leaves the diego-platform namespace. Tailscale intercepts because admin-portal is a MagicDNS name.
3. Tailscale queries the control plane: "Can diego reach admin-portal:8080?"
4. The control plane evaluates policy.hujson:
   - `tag:admin-portal:8080` appears as dst in an `accept` rule.
   - The rule has `src: ["group:platform-eng@helios.example", "autogroup:admin"]`.
   - Diego is `platform-eng` (his OIDC login made him part of platform-eng).
   - **Allow.**
5. The WireGuard tunnel is established between diego-platform and admin-portal.
6. The request reaches admin-portal, which responds `{"status": "healthy"}`.

**If it were Eve (untrusted):**

1. Same step 1-2.
2. Same step 3.
3. Control plane evaluates: Eve does not appear in any `src` that has dst=`tag:admin-portal:8080`.
4. **Deny.** Tailscale rejects the flow without establishing a tunnel.
5. The curl returns `Connection timed out` (no explicit error — this is deliberate to avoid leaking info).

## Decisions reflected in the code

### 1. `network_mode: "service:ts-X"` + isolated network per node

```yaml
ts-admin-portal:
  image: tailscale/tailscale:latest
  hostname: admin-portal
  environment:
    TS_AUTHKEY: ${TS_AUTHKEY_ADMIN_PORTAL}
    # (common config in x-ts-env)

admin-portal:
  build: ./apps/admin-portal
  network_mode: "service:ts-admin-portal"  # shares the sidecar's namespace
  depends_on:
    - ts-admin-portal
```

The service lives inside the sidecar's namespace. This means the service sees `tailscale0` as its network interface and MagicDNS resolves as if it were on the tailnet.

The `net-admin-portal` network is isolated so other containers can't reach `admin-portal` directly — only via the tailnet.

### 2. `environment` as a map, not a list

```yaml
x-tailscale-env: &ts-env
  TS_STATE_DIR: /var/lib/tailscale
  TS_USERSPACE: "false"      # without this, tailscaled falls back to userspace networking
  TS_ACCEPT_DNS: "true"

services:
  ts-admin-portal:
    environment:
      <<: *ts-env           # correct merge because it's a map
      TS_AUTHKEY: ${...}
      TS_TAGS: "tag:admin-portal"
```

If `environment:` were a list, the `<<: *ts-env` would be replaced by the service's list and `TS_USERSPACE`/`TS_ACCEPT_DNS` would be lost. The consequence: `tailscaled` starts without a kernel interface and all traffic goes through userspace (slow and sometimes blocked by Docker).

This bug is **silent**: the container starts "fine" but the tailnet doesn't behave as expected. That's why the YAML anchor is a map.

### 3. Identity = Google group, NOT tag

Services have **tags** (`tag:admin-portal`). Personas are **user-owned nodes** (no tag, their identity is the Google login).

In the policy:
```json
{
  "src": ["tag:admin-portal", "group:platform-eng@helios.example"],
  "dst": ["tag:identity-bridge:9090"]
}
```

The first src is a service (which also consumes identity-bridge). The second is a human. The policy evaluates both the same way.

### 4. SSH rules separate from acls

```json
{
  "ssh": [
    {
      "action": "accept",
      "src": ["group:platform-eng@helios.example"],
      "dst": ["tag:admin-portal", "tag:identity-bridge"],
      "users": ["autogroup:nonroot"]  // no root
    }
  ]
}
```

SSH has its own section because the Tailscale SSH client is evaluated differently. `users: ["autogroup:nonroot"]` prevents SSH as root (defense in depth).

### 5. Grants for Nina (auditor)

```json
{
  "grants": [
    {
      "src": ["group:auditors@helios.example"],
      "dst": ["tag:observability"],
      "ip":  ["*"],
      "app": { "observability.read": [{}] }
    }
  ]
}
```

Grants are a richer form than `acls`. Here Nina can read observability regardless of what the main `acl` says. This is defense in depth: if an acl rule breaks, Nina can still audit.

### 6. Identity-bridge reads credentials at runtime

```python
_secrets_client = boto3.client("secretsmanager", endpoint_url=...)
_dsn_cache = None

def get_dsn():
    if _dsn_cache: return _dsn_cache
    with _dsn_lock:
        if _dsn_cache is None:
            secret = _secrets_client.get_secret_value(...)["SecretString"]
            _dsn_cache = f"host={secret['host']} port={...} ..."
    return _dsn_cache
```

Three non-obvious details:
- **Lazy fetch:** doesn't fail the container if MiniStack isn't ready yet.
- **Lock:** avoids race conditions on cold start with multiple requests.
- **In-process cache:** secrets rotation requires a container restart (in prod: sidecar with refresh, or AWS SDK with short cache).

### 7. Warehouse-job is one-shot

```yaml
warehouse-job:
  restart: "no"  # ← does not restart
```

The job runs once (when `docker compose up` is run), copies data from primary to warehouse, and ends. In prod it would be a K8s CronJob or Dagster/Airflow.

### 8. EKS gateway exposes 3 ports

```python
RESOURCES = {
    9100: {"resource": "metrics", ...},
    9101: {"resource": "logs", ...},
    9102: {"resource": "exec", ...},
}

servers = [ThreadingHTTPServer(...) for port in RESOURCES]
```

Each port is an independent "resource" from the ACL's point of view. SRE can see metrics+logs, SRE-lead can exec. Per-port granularity.

## Extension points

If you're going to extend this POC, look at these places first:

| If you want to change... | Edit |
|---|---|
| What each persona can do | `acl/policy.hujson` + `scripts/verify.sh` |
| Add a new service | `docker-compose.yml` + `apps/<service>/` + entry in `acl/policy.hujson` |
| Add a new persona | `identity/bootstrap/users.json` + node in `docker-compose.yml` |
| Change the IdP | `docker-compose.identity.yml` (replace Authentik with another) |
| Change the control plane to Headscale | `policy.hujson` stays the same. Change `cfg.OIDC` and the auth keys. |
| Change the secrets pattern | `terraform/main.tf` + `apps/identity-bridge/app.py` (same SECRET_ID) |

## Limitations the code honestly exposes

- The DSN cache in identity-bridge lasts the entire lifetime of the process. If you rotate the DB password without redeploying, the bridge won't notice.
- The Authentik seed (`seed.py`) creates the OIDC provider but **doesn't** configure the authorization flow to ask for consent. In prod: every login to Tailscale asks for consent the first time — that's fine for a company.
- `verify.sh` uses `docker compose exec`, which requires each persona to be a container. In prod personas are real laptops — the script changes to `ssh diego-platform@...` or similar.
- Reusable auth keys are appropriate for the POC. In prod: each laptop receives a single-use auth key during MDM enrollment.
