# Helios POC — Decision log

Why we chose each piece. This is for future contributors wondering "why not X instead of Y".

## IdP: Authentik, not Google Workspace directly

**Decision:** use Authentik as the simulated IdP in this POC. In prod it gets replaced by real Google Workspace.

**Why:**
- The POC needs a locally controllable IdP (without depending on real credentials from a real Google Workspace).
- Authentik provides real OIDC + an admin UI similar to Google Workspace (developers see "this is what they'd do in prod").
- Dex was the alternative but it doesn't have an admin UI — a good pure-OIDC replacement, bad for simulating the "Workspace admin" experience.
- Keycloak is heavier and older. Authentik is the modern equivalent.

**When to change:** once Helios has its real Google Workspace configured, the integration with Tailscale is 1-to-1 — only the issuer URL changes. The policy doesn't need to be modified.

## Tailscale SaaS, not Headscale

**Decision:** use Tailscale SaaS in this POC.

**Why:**
- The team already agreed on this direction in Sep-2026 (see `decision-log.md` of the original Axial POC).
- Headscale is excellent but requires operating 162K LoC of code + maintaining parity with upstream Tailscale. It brings no immediate benefit for the pattern we're validating.
- Tailscale SaaS provides SSO with Google Workspace out of the box (deeper than generic OIDC: it syncs groups via SCIM automatically).

**When to evaluate Headscale:**
- Compliance asks for an on-prem control plane.
- SaaS starts charging for a critical feature.
- We need a feature that Tailscale Inc. refuses to implement.

**What we must keep:** the policy is portable between Tailscale SaaS and Headscale (it's standard HuJSON). Migrating is a vendor swap, not a rewrite.

## Docker Compose, not Kubernetes

**Decision:** docker compose for the POC.

**Why:**
- The POC must run on a laptop with a single command.
- K8s would add operational complexity that doesn't contribute to the pattern we're validating (which is about networking, not orchestration).
- When Helios scales to prod, the same containers go to K8s (EKS or similar) without changes.

**When to change:** when Helios has >20 services or needs HA by design. Not before.

## MiniStack, not LocalStack

**Decision:** MiniStack to emulate AWS Secrets Manager.

**Why:**
- LocalStack moved several services behind paid plans (Jul-2024). MiniStack is the open-source alternative.
- We only need Secrets Manager (not RDS, not EC2). MiniStack provides it for free.

**When to change:** when Helios uses real AWS, MiniStack is replaced by a `provider "aws"` pointing to the real account.

## Flask, not FastAPI

**Decision:** Flask 3 for all apps.

**Why:**
- The apps are mocks (they respond with hardcoded JSON or make 1 query to the DB). Flask is more concise for that.
- FastAPI would be preferable if we needed real async or pydantic types — that's not the case.

**When to change:** when the mock apps are replaced by the real ones (which will have async, validation, auto-generated OpenAPI, etc).

## Identity-bridge uses boto3 + Secrets Manager (not env vars)

**Decision:** DB credentials come from Secrets Manager at runtime, not from env vars.

**Why:**
- Allows secrets rotation without redeploy.
- Models the exact prod pattern. The earlier POC (migration-bridge in the original Axial POC) already validated this pattern; we extend it.
- The lazy cache prevents the container from crashing if MiniStack isn't ready at boot.

**Trade-off:** adds latency on the first request. Acceptable for a low-frequency service like identity-bridge. For something high-frequency (api-gateway) we'd use a secrets sidecar or env vars.

## Tags XOR user-owned (not both)

**Decision:** a node is `tag:X` (service) OR user-owned (persona), never both.

**Why:**
- This is the load-bearing rule of Tailscale and Headscale (in code: `node.IsTagged()` in Headscale).
- Mixing both makes the ACL impossible to reason about ("is this tag from the service or from the engineer who logged in?").

**How we implement it:**
- Services: preauth keys with `tag:` (Tailscale defines this when the authkey is generated).
- Personas: preauth keys WITHOUT tag (user-owned nodes). In prod they'd be real laptops with SSO.

## network_mode: service:* + isolated networks

**Decision:** each node in its own Docker network, sidecar `tailscale/tailscale` shares the namespace.

**Why:**
- Without this, Docker resolves hostnames between containers via its embedded DNS, bypassing the tailnet.
- Each isolated network forces traffic to cross the real tailnet, where the ACL evaluates.

**Trade-off:** services inside a namespace can't talk to each other directly (e.g., identity-bridge can't reach api-gateway directly — it must go via the tailnet). This is **desirable**, not a problem.

## Policy pasted manually in the admin console

**Decision:** the policy is pasted manually into the Tailscale admin console in this POC.

**Why:**
- It's the fastest way to validate the pattern.
- The policy is small (10 tags, 9 personas) — manageable by hand.

**When to change (prod):**
- Move `policy.hujson` to a git repo with PR review.
- Apply it via the Tailscale API programmatically (or Terraform provider, or Atlantis).
- CI that validates the syntax and runs `verify.sh` on every PR.

## No automated tests of the policy (yet)

**Decision:** tests live in `policy.hujson` (`tests` section) but they aren't run automatically.

**Why:**
- Tailscale supports a `tests` section in the policy that validates rules, but it requires external tooling to run against a real server.
- `verify.sh` covers the end-to-end verification (it's the ground truth).

**When to change:** when the team grows, add `tacl` (https://github.com/devopsworks-llc/tacl) or similar to CI to validate the policy before applying it.

## No MDM in this POC

**Decision:** the "personas" are containers with tailscale, not real laptops.

**Why:**
- The POC runs on a laptop. There are no 9 real laptops to test on.
- In prod: Apple Business Manager + Mosyle/Intune enrolls laptops and adds them to the tailnet automatically.

**When to change:** when Helios has real employees using the infra. MDM is the piece that connects "the employee has a laptop" with "the laptop is in the tailnet with its correct group".
