# Helios POC — Operations Guide

This is the "how to actually run this thing" guide for the POC. It assumes you already have Docker + ngrok + kind + kubectl installed.

## TL;DR

```bash
cd tailscale/

# 1. Initial setup
cp .env.example .env
$EDITOR .env  # paste TS_AUTHKEY_* + NGROK_AUTHTOKEN + passwords

# 2. Bring everything up
./scripts/heliosctl start all

# 3. Validate
./scripts/heliosctl validate

# 4. Guided demo
./scripts/demo.sh --fast

# 5. Clean up
./scripts/heliosctl stop all   # stops containers, keeps state
./scripts/heliosctl destroy    # nuke EVERYTHING
```

## Refresh the lab (capture everything)

A one-command lab refresh re-runs the POC and dumps every output (terminal transcripts, JSON, PNG diagrams and chrome headless screenshots of each web UI) into `docs/captures/`:

```bash
./scripts/refresh_captures.sh                 # full run, ~2 min
./scripts/refresh_captures.sh --no-screenshots   # skip chrome (no GUI in CI)
```

What the script captures:

| Source | Output file |
|---|---|
| `heliosctl validate` (host view) | `validate_host.txt` |
| `heliosctl status` | `status_full.txt` |
| `heliosctl validate` (with `TAILSCALE_API_KEY`) | `validate_final.txt` |
| `docker exec <svc> python3 urllib /healthz` per service | `health_probes.txt` |
| `tailscale status` from each sidecar | `tailscale_status.txt` |
| MagicDNS view from `ts-admin-portal` sidecar | `admin_peers.txt` |
| `tsctl.py policy get` (live HuJSON) | `live_policy_full.txt` + `live_policy_head.txt` |
| `cross_service_real.py` (admin-portal -> 4 peers via 100.x overlay) | `cross_service_real.txt` |
| `isolation_test.sh` (segregated docker networks) | `isolation_test_output.txt` |
| `demo.sh --fast` (last 30 lines) | `demo_run.log` |
| `verify.sh` (last 30 lines) | `verify_run.log` |
| chrome headless screenshots (10 web UIs incl. Authentik via ngrok) | `screenshots/*.png` |

After running it, regenerate the .docx so section 11d shows the latest evidence:

```bash
python3 scripts/generate_docs.py
# writes docs/Helios-POC-Documentation.docx with 8 screenshots + terminal blocks embedded
```

### Live lab state (Sep-27-2026 refresh)

Latest run output: `heliosctl validate` shows 7/7 checks pass, 9 of 13 sidecars logged into the live tailnet, 6 of 10 services responding HTTP 200 on `/healthz`, ngrok public URL active at `https://sardine-overact-blast.ngrok-free.dev`, Authentik OIDC discovery 200 via that URL.

`refresh_captures.sh` is idempotent — safe to run as many times as needed.

## Detailed setup (first time)

### 1. System prerequisites

```bash
# Docker + Compose v2
docker --version     # ≥ 20.10
docker compose version   # ≥ 2.0

# ngrok (for SSO against Tailscale)
brew install ngrok  # Mac
# or download from https://ngrok.com/download

# kind + kubectl (for EKS sim)
brew install kind kubectl
# or from https://kind.sigs.k8s.io/docs/user/quick-start/
```

### 2. Get tokens

| Token | Where to get it |
|---|---|
| `TS_AUTHKEY_*` (18) | https://login.tailscale.com/admin/settings/keys (or via `tsctl.py`) |
| `TAILSCALE_API_KEY` | https://login.tailscale.com/admin/settings/keys (toggle "API access") |
| `NGROK_AUTHTOKEN` | https://dashboard.ngrok.com/get-started/your-authtoken |

### 3. Configure .env

```bash
cd tailscale/
cp .env.example .env

# Paste the 18 TS_AUTHKEY_* you generated
# Paste TAILSCALE_API_KEY (optional, only for tsctl.py admin)
# Paste NGROK_AUTHTOKEN

# If you have a Tailscale Business trial, the Google Workspace groups come in via SSO
# and you can use acl/policy.hujson (the original with groups)
# If not, use acl/policy-poc-no-groups.hujson (the one that works on any plan)
```

### 4. Bring up the stack

```bash
./scripts/heliosctl start all
# → 1. ministack (AWS sim)
# → 2. identity (Authentik)
# → 3. ngrok (tunnel to Authentik)
# → 4. terraform (seeds secrets in ministack)
# → 5. eks (kind cluster + RBAC)
# → 6. services (10 services with tailscale sidecars)
# → 7. personas (8 personas)
```

Total time: 2-5 minutes the first time (image build).

### 5. Verify

```bash
./scripts/heliosctl status         # status of the 7 components
./scripts/heliosctl validate       # 7 end-to-end checks
./scripts/heliosctl verify         # allow/deny matrix (30+ cases)
./scripts/demo.sh                  # step-by-step guided demo
```

## Troubleshooting

### "all predefined address pools have been fully subnetted"

**Cause:** Docker ran out of available `/16` blocks for bridge networks. Each isolated `networks:` in `docker-compose.yml` asks for a new subnet.

**Workarounds:**

```bash
# 1. Clean unused networks
docker network prune -f

# 2. If you still run out, increase the Docker pool:
#    /etc/docker/daemon.json:
{
  "default-address-pools": [
    {"base": "172.20.0.0/14", "size": 22},  # 1024 /22 networks
    {"base": "192.168.0.0/16", "size": 24}  # 256 /24 networks
  ]
}
# sudo systemctl restart docker
```

**Alternative:** consolidate networks in docker-compose (lose the isolation guarantee, but fewer networks).

### "groups not found" when applying policy.hujson

**Cause:** the policy references `group:platform-eng@helios.example` but Tailscale doesn't know those groups (no SSO configured).

**Solution:** use `acl/policy-poc-no-groups.hujson` instead of `policy.hujson`. The difference is that the POC doesn't use groups (only tags + autogroup:admin).

```bash
python3 ../tools/tsctl.py policy set acl/policy-poc-no-groups.hujson
```

### "permission denied" on `docker exec`

Cause: the sidecar container has `NET_ADMIN` and the devices. If your user is not in the `docker` group, it fails.

```bash
sudo usermod -aG docker $USER
newgrp docker
```

### "TS_AUTHKEY has been used" or "key not found"

Auth keys are consumed ONCE when the sidecar comes up for the first time. If you want to reset:

```bash
docker compose down
docker volume rm <name>-state  # delete the sidecar's state
./scripts/heliosctl restart services  # use a fresh auth key
```

### Tailscale sidecars don't register with the control plane

**Symptoms:** in `heliosctl status`, services show "running" but `tailscale status` inside the container says "not logged in".

**Common causes:**
- Auth key pasted incorrectly (typo, expired key)
- `ts-*` container can't reach `controlplane.tailscale.com` (DNS issue)
- Tailscale SaaS rejects the auth key because it was already used

**Debug:**
```bash
docker compose exec ts-admin-portal tailscaled --help
docker compose logs ts-admin-portal | grep -i error
```

## Common commands (cheatsheet)

| Action | Command |
|---|---|
| Bring everything up | `heliosctl start all` |
| Services only | `heliosctl start services` |
| Personas only | `heliosctl start personas` |
| Full status | `heliosctl status` |
| Re-apply policy | `heliosctl policy` |
| Regenerate auth keys | `heliosctl authkeys` |
| Logs for a service | `heliosctl logs admin-portal` |
| Shell into a container | `heliosctl exec diego-platform bash` |
| Restart everything | `heliosctl restart all` |
| Stop everything | `heliosctl stop all` |
| Nuke EVERYTHING | `heliosctl destroy` |
| Validate setup | `heliosctl validate` |
| Guided demo | `scripts/demo.sh` |
| Test allow/deny | `heliosctl verify` |
| Add service | `heliosctl add service <name> --tag tag:X` |
| Add persona | `heliosctl add persona <name>` |
| Remove service | `heliosctl remove service <name>` |
| Remove persona | `heliosctl remove persona <name>` |

## Workflows

### Workflow 1: Stakeholder demo

```bash
heliosctl start all
heliosctl status          # show everything is running
heliosctl verify          # show the allow/deny matrix
scripts/demo.sh          # guided 7-step demo
# leave it running for questions
```

### Workflow 2: Iterate on the policy

```bash
# Edit acl/policy.hujson
heliosctl policy          # re-apply
heliosctl verify          # validate that the new policy passes the cases
```

### Workflow 3: Add a new service

```bash
# 1. Create the service code
mkdir apps/my-service
# Dockerfile, app.py, requirements.txt

# 2. Add it to the POC
heliosctl add service my-service --tag tag:my-service
# → generates auth key, appends to docker-compose.yml, adds to .env

# 3. Add to the policy
# edit acl/policy.hujson, add my-service to tagOwners + acls

# 4. Apply
heliosctl policy
heliosctl restart services
```

### Workflow 4: Test real SSO (with Google Workspace)

1. Set up Google Workspace OAuth client
2. Configure Tailscale admin console → SSO
3. Apply `acl/policy.hujson` (with groups)
4. Log in via Google → groups appear in Tailscale

(See `ngrok/README.md` for detailed setup with Authentik as IdP.)

### Workflow 5: Test EKS RBAC

```bash
# 1. Install kind + kubectl
brew install kind kubectl

# 2. Bring up the cluster
./eks/scripts/setup.sh

# 3. Validate RBAC
kubectl --context=kind-helios-eks-sim get nodes
kubectl auth can-i create pods --as=system:serviceaccount:kube-system:k8s-editor -n helios-prod
# → no (editor CANNOT touch prod)
kubectl auth can-i create pods --as=system:serviceaccount:kube-system:k8s-admin
# → yes (admin full)

# 4. Clean up
./eks/scripts/teardown.sh
```

## Differences with the original previous POC

| Aspect | previous POC (orig) | Helios POC (this) |
|---|---|---|
| Tag count | 9 | 13 (+ EKS roles) |
| Policy versions | 1 | 4 (no-groups, v1, v2, v3) |
| IdP | ❌ | ✅ Authentik sim + ngrok ready |
| Personas | 8 | 8 |
| Services | 10 | 10 |
| EKS sim | ❌ | ✅ kind + RBAC |
| Lifecycle CLI | ❌ | ✅ heliosctl |
| Guided demo | ❌ | ✅ scripts/demo.sh |
| Dynamic CRUD | ❌ | ✅ add/remove |

## Next steps toward production

See `MATURITY.md` and `ROADMAP.md`. Short version:

1. **Migrate to Headscale** if compliance asks for on-prem (the same policy works)
2. **MDM rollout** (Apple Business Manager / Mosyle) — automates onboarding
3. **Audit logging in SIEM** (Splunk / Datadog) — the `Tailscale-User-*` headers are already available
4. **Alerts + runbook** — Prometheus is already integrated in observability
