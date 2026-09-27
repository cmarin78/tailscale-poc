# Helios POC — Full Roadmap

This is the **complete work list** to take the POC from "basic functional POC" (what we have today) to "realistic POC for stakeholder demo" (what you want).

## Current status

| Component | Status | Notes |
|---|---|---|
| `tailscale/` base POC | ✅ complete | 10 services + 8 personas + ACL + verify |
| HuJSON Policy with 10 tags | ✅ complete | 4 variants (no-groups, original, v2, v3) |
| Auth keys (18) generated via tsctl | ✅ complete | Pasted in `.env` |
| `heliosctl` lifecycle CLI | ✅ complete | start/stop/restart/destroy/clean + add/remove + validate + help |
| `tools/tsctl.py` admin CLI | ✅ complete | with bugs fixed |
| `tools/hsctl.py` admin CLI (Headscale) | ✅ complete | |
| Parallel POC with Headscale (`headscale/`) | ✅ complete | parallel structure |
| Documentation (ARCHITECTURE, MATURITY, decision-log, comparison, ROADMAP, POC_OPERATIONS) | ✅ complete | |
| **Active Business Trial (`cerberusbyte.com`)** | ✅ operational | Supports SSO + SCIM + custom OIDC |
| **Phase A: ngrok + Authentik setup** | ✅ structurally complete | Your action pending: paste NGROK_AUTHTOKEN + configure SSO in admin console |
| **Phase B: kind + EKS RBAC** | ✅ structurally complete | Your action pending: `eks/scripts/setup.sh` (requires kind installed) |
| **Phase C: refined roles matrix (viewers/externals/admins)** | ✅ complete | policy-v3-roles.hujson |

## What's missing (roadmap)

### Phase A — ngrok + Authentik + real SSO (Level 1)

**Why:** for the policy with `group:platform-eng@helios.example` to work, Tailscale SaaS needs to receive those groups via OIDC. Authentik emits them, ngrok exposes them publicly.

**Tasks:**
1. [ ] Create OAuth client in Google Cloud Console for `cmarinvalios@cerberusbyte.com` (or use Authentik as IdP instead of Google)
2. [ ] Bring up ngrok (`ngrok http 9000`) to expose Authentik
3. [ ] Configure Authentik as IdP in Tailscale SaaS admin console
4. [ ] Configure redirect URI in Authentik: `https://login.tailscale.com/a/callback`
5. [ ] Validate end-to-end SSO login
6. [ ] Re-apply `policy.hujson` (with groups) and verify it works

**Expected output:** the 6 Helios groups appear in Tailscale, `group:platform-eng@helios.example` resolves in the policy.

### Phase B — kind + EKS-like cluster (EKS simulation)

**Why:** the user wants granular access to EKS. We need a realistic K8s cluster where we can test RBAC.

**Tasks:**
1. [ ] Install `kind` (Kubernetes in Docker)
2. [ ] Create kind cluster with 3 nodes (simulates multi-AZ EKS)
3. [ ] Deploy 3 EKS-like workloads: metrics-server, logs-collector, pod-exec
4. [ ] Configure RBAC:
   - `role:k8s-viewer` → get/list/watch on everything
   - `role:k8s-editor` → + create/update/delete in designated namespaces
   - `role:k8s-admin` → cluster-admin
5. [ ] kubeconfig with 3 contexts (one per role)
6. [ ] Each context reachable via `tag:k8s-{viewer,editor,admin}` in Tailscale

**Expected output:** `heliosctl start eks` brings up the kind cluster + RBAC + kubeconfig.

### Phase C — Specific roles & permissions (granular access)

**Why:** the "DMZ with privileges but no prod" + "least privilege" pattern requires each group to have a well-defined scope.

**Roles matrix:**

| Group | EKS | RDS | Grafana | Intranet | Customer Portal |
|---|---|---|---|---|---|
| `viewer@helios.example` | read metrics, logs | read schema only | read all dashboards | read all pages | read |
| `external@helios.example` | deny | deny | deny | public pages only | read (own data) |
| `admin@helios.example` | full | full | full | full | full |
| `sre@helios.example` | read metrics, logs | deny direct | read + write | full | full |
| `sre-lead@helios.example` | full | full | full | full | full |
| `platform-eng@helios.example` | deny direct | deny direct | deny direct | full | deny |
| `data-eng@helios.example` | deny | read warehouse only | read | deny | deny |
| `customer-success@helios.example` | deny | read primary (PII) | read | full | full |
| `sales-eng@helios.example` | deny | deny | deny | deny | demo data |

**Tasks:**
1. [ ] Define the 9 roles in `identity/bootstrap/groups.json`
2. [ ] Update `policy.hujson` with the roles matrix
3. [ ] For each role, identify the apps/resources they need
4. [ ] Validate with extended `verify.sh`

### Phase D — kind + Tailscale + RBAC integration

**Tasks:**
1. [ ] kind cluster with ingress to expose internal services
2. [ ] `tag:eks-gateway` points to a service inside kind
3. [ ] RBAC verified by `kubectl auth can-i` from each context
4. [ ] kubeconfig mounted in the persona containers

### Phase E — MiniStack + RDS sim + Secrets Manager + Authentik + kind

**Tasks:**
1. [ ] MiniStack serves as Secrets Manager (✅ already working)
2. [ ] MiniStack RDS sim → postgres-as-a-service for an app that prefers it
3. [ ] Authentik OIDC → kubeapps (K8s dashboard) for SSO in K8s
4. [ ] Cross-cutting: `kubectl get secrets` must use MiniStack as the backend

### Phase F — Demo and validation

**Tasks:**
1. [ ] Document the demo flow (what to test, what to show)
2. [ ] Create `scripts/demo.sh` that runs the verification matrix with colors
3. [ ] Generate screenshots of the admin console
4. [ ] Write a `RECORDING.md` with the scripted demo

## Pending decisions

| Question | Options | Recommendation |
|---|---|---|
| ngrok paid or free? | free ($0, random URL) / paid (fixed URL, ~$8/mo) | paid for demos (predictable URL) |
| kind or k3d? | kind (official Kubernetes SIG) / k3d (k3s, lighter) | kind (more realistic, better testing) |
| Where to host kind? | local Docker / cloud VM | local for POC, cloud for staging |
| IdP: Authentik or Google Workspace? | Authentik (in POC) / Google Workspace (in prod) | Authentik to validate, swap for prod |
| Helm or kubectl apply? | Helm (cleaner) / kubectl (more direct) | kubectl for POC, Helm for prod |
| CI? | GitHub Actions / local pre-commit | pre-commit now, Actions as it grows |

## Suggested order

1. **Phase A** (ngrok + SSO) — unlocks `group:X` in policy
2. **Phase C** (roles matrix) — refines the policy
3. **Phase B + D** (kind + EKS) — adds the K8s component
4. **Phase E** (full integration) — ties it all together
5. **Phase F** (demo) — packages for presentation

## Time estimate

| Phase | Estimated time |
|---|---|
| A — ngrok + SSO | 2-3 hours |
| C — Roles matrix | 1-2 hours (refining policy.hujson) |
| B + D — kind + EKS | 3-4 hours (install + workloads + RBAC + tags) |
| E — Integration | 2-3 hours |
| F — Demo + docs | 2-3 hours |
| **Total** | **10-15 hours** |

## Identified risks

| Risk | Mitigation |
|---|---|
| ngrok free URL changes every restart | ngrok paid + custom domain |
| Authentik is not production-grade | document the swap to Google Workspace |
| kind is not real EKS (some features missing: IAM, ALB, etc.) | document the differences |
| SSO setup requires coordination with admin console (manual) | document step by step |
| Policy becomes complex with groups | modularize into files per role |
