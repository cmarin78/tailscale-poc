# Helios POC — Maturity Roadmap

This POC is **Level 1**. It covers the network pattern and IdP integration. What follows is the path to take it to actual Helios production.

## Current state: Level 1 — Local POC

✅ 10 services simulated in Docker, with Tailscale as the network substrate.  
✅ 9 personas in Authentik (Google Workspace sim. IdP), with functional groups.  
✅ Mature HuJSON policy: 10 tags, 6 groups, grants, SSH, services.  
✅ Runnable matrix of 30+ allow/deny cases.  
✅ Terraform seeds secrets in MiniStack.  
✅ ETL pattern: warehouse-job moves data from primary to warehouse.  

**Honest limitations:**
- MagicDNS resolves with latency on the first up (~30-60s).
- No MDM (the "personas" are containers).
- No HA (each service is a single instance).
- Policy is applied manually in the admin console.
- Single environment (no separate dev/staging).

## Level 2: Helios staging (~1 sprint)

**What changes:**
- Replace Authentik with real Google Workspace (same OIDC flow, different issuer).
- Bring up the same containers in an AWS staging EKS.
- Replace the mocks (Flask apps with hardcoded JSON) with the real Helios services (`axial-api`, `service-lib`, etc).
- Activate MDM with Apple Business Manager (once the MDM vendor is decided).

**What gets validated:**
- Real SSO with Google Workspace (not simulated).
- Performance under real load (not 9 nodes but 50).
- Automated secrets rotation.
- Incident runbooks (what happens if Tailscale/Headscale goes down?).

## Level 3: Production (~1 quarter)

**What changes:**
- HA: each service with replicas + load balancer.
- Multi-region: Helios SaaS probably needs US-East + EU-West.
- Monitoring: real Prometheus + Grafana (the `observability` mock becomes a real stack).
- Centralized audit log: the `Tailscale-User-*` headers flow to a SIEM (Splunk/Datadog).
- Policy-as-code: `policy.hujson` in git, PR review, applied via the Tailscale API.
- Secrets in real Vault (not MiniStack).

**What gets validated:**
- SLOs (latency, uptime, error rate).
- DR (how long does it take to recover a downed node?).
- Compliance (SOC 2 audit trail, GDPR data residency, etc).

## Level 4: Headscale evaluation (on-demand decision)

**Trigger:** compliance asks for an on-prem control plane.

**What changes:**
- Stand up Headscale in Helios's infra (its own K8s cluster).
- The HuJSON policy is portable: the same policy works.
- Auth keys are generated via the Headscale API.
- SCIM sync from Google Workspace requires its own sync (no native SCIM in Headscale yet).

**When decided:** post-SOC 2 audit (auditors usually ask for control-plane sovereignty).

## What the POC demonstrates vs what it does NOT

| Question | Level 1 (this POC) | Level 2 (staging) | Level 3 (prod) | Level 4 (Headscale) |
|---|---|---|---|---|
| Do tag-based ACLs work? | ✅ | ✅ | ✅ | ✅ |
| SSO with real IdP? | ❌ (simulated) | ✅ | ✅ | ✅ (with own sync) |
| Group-level granularity? | ✅ | ✅ | ✅ | ✅ |
| Robust default-deny? | ✅ | ✅ | ✅ | ✅ |
| Multiple environments? | ❌ | ✅ | ✅ | ✅ |
| HA? | ❌ | partial | ✅ | ✅ |
| Audit logging? | mock | partial | ✅ | ✅ |
| Secrets rotation? | manual | automated | automated | automated |
| MDM enrollment? | ❌ | ✅ | ✅ | ✅ |
| Multi-region? | n/a | n/a | ✅ | ✅ |
| On-prem control plane? | n/a | n/a | n/a | ✅ |
| 5-year cost? | n/a | $$$ (SaaS) | $$$$ (SaaS + infra) | $$$ (self-operated) |

## Metrics to decide the next level

- **Nodes in tailnet > 30?** → Consider Level 2.
- **Audit asks for SOC 2?** → Consider Level 3.
- **Compliance asks for on-prem?** → Consider Level 4.
- **SaaS costs > 30% of infra budget?** → Re-evaluate Level 4.

## How to contribute

This POC is deliberately simple so it's easy to understand. If you're going to extend it:

1. **Don't add features that aren't in the roadmap** — the POC must remain understandable.
2. **Any change to `acl/policy.hujson` must be reflected in `scripts/verify.sh`** (the tests are the ground truth).
3. **Any new app must have its Dockerfile, requirements.txt, and entrypoint** — the mocks must be trivially replaceable.
4. **Identity (Authentik/Google Workspace) is the most fragile piece** — test the end-to-end OIDC flow before changing it.

See `decision-log.md` for the rationale of each piece.
