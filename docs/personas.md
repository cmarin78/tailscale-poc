# Helios POC — Personas

This document describes the 9 personas that populate the POC. Each one represents a **real functional role** in a mid-sized B2B SaaS company, not an ad-hoc case.

## Inventory

| # | Username | Sim. Email | Google Group(s) | Responsibility | Critical access |
|---|---|---|---|---|---|
| 1 | maya.admin | @helios.example | `helios-admin` + `platform-eng` | Ops lead. Tailnet admin. | Everything (incl. SSH everywhere) |
| 2 | diego.platform | @helios.example | `platform-eng` | Platform engineer. Operates core services. | admin-portal, identity-bridge, api-gateway, customer-portal |
| 3 | rafa.data | @helios.example | `data-eng` | Data engineer. Maintains warehouse and models. | warehouse-db, ml-platform |
| 4 | sam.sre | @helios.example | `sre` | Regular SRE. Reads metrics, responds to alerts. | observability, eks-gateway (9100+9101) |
| 5 | lena.sre.lead | @helios.example | `sre` + `sre-lead` | SRE lead. Runs commands in pods. | Everything Sam has + eks-gateway:9102 (exec) |
| 6 | carla.cs | @helios.example | `customer-success` | Customer success. Resolves tickets. | customer-portal, identity-bridge |
| 7 | tomas.sales | @helios.example | `sales-eng` | Sales engineer. Runs demos. | customer-portal, api-gateway, ml-platform |
| 8 | nina.auditor | @helios.example | `auditors` | External auditor (SOC 2). | observability (read), eks-gateway:9100 (read) |
| 9 | eve.attacker | @external.example | `untrusted` | Simulated external attacker. | **Nothing** — the ACL doesn't reference her |

## What each role demonstrates

### Maya (admin)
- Only one with `autogroup:admin` — can assign tags and SSH anywhere.
- Also `platform-eng` as a fallback in case she needs to act as an engineer.
- In prod: a single person with these privileges. Credential rotation every 90 days.

### Diego (platform-eng)
- Can operate internal services but **not** the DBs.
- Doesn't see the customer-portal — uses admin-portal for admin tasks.
- Demonstrates the "engineers separated from customer UI" pattern.

### Rafa (data-eng)
- Has access to the warehouse (analytics) but not the primary (transactional).
- This prevents the classic risk of "data engineer accidentally deleting tables in prod".
- Demonstrates the `warehouse-db` vs `primary-db` separation as distinct layers.

### Sam vs Lena (sre vs sre-lead)
- Same base group `sre` for both.
- Lena has the additional group `sre-lead` which enables `eks-gateway:9102` (exec).
- Demonstrates **group stacking** — the sum of groups determines permissions, not individual identity.

### Carla (customer-success)
- Reaches the customer portal but **not** admin-portal nor the DBs.
- This is defense in depth: even though she has a support role, she doesn't see internal infra.
- Demonstrates the principle of least privilege applied to support roles.

### Tomás (sales-eng)
- Reaches customer-portal, api-gateway, and ml-platform (predict).
- **Does not** reach warehouse-db or admin-portal.
- Demonstrates that an external role (sales) can run demos without touching prod.

### Nina (auditor)
- Read-only via `grants` (not `acls`).
- This means even if an `acls` rule fails, Nina can still see observability.
- Demonstrates the pattern "auditing must not depend on the main policy".

### Eve (attacker)
- Is a node in the tailnet (valid auth key) but **does not** appear in any `src` of the policy.
- All of her connection attempts must be DENIED by default.
- Demonstrates that **absence in the policy is deny**, not "permitted by oversight".

## Patterns the combination of personas proves

| Combination | What it validates |
|---|---|
| Diego (engineer) DENIED on customer-portal | "DMZ with privileges but no access" — the role determines which UI they see, not technical capability |
| Rafa (data) DENIED on primary-db | Separation of warehouse / primary |
| Sam DENIED on eks:9102, Lena ALLOWED | Group stacking — adding a group adds permissions |
| Tomás DENIED on primary-db | Sales doesn't touch transactional DBs |
| Nina DENIED on eks:9102 (exec) | Auditing is read-only, without operational privileges |
| Eve DENIED on EVERYTHING | Default-deny works even if the node is authenticated |

## Team size: 9 personas

For a ~50-employee company, 9 simulated personas (18% of headcount) cover the critical functions:

| Function | % of org (real) | Personas in POC |
|---|---|---|
| Engineering (platform + data + SRE) | ~50% | 4 (Diego, Rafa, Sam, Lena) |
| Customer-facing (CS + sales) | ~25% | 2 (Carla, Tomás) |
| Admin/security | ~10% | 2 (Maya, Nina) |
| Threat simulation | n/a | 1 (Eve) |

When Helios scales to 50 real people, this set covers the **functions** — the only difference is N people per function, not new functions.
