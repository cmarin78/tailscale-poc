# Helios — Corporate tailnet POC with simulated IdP

**POC that validates a realistic access management pattern for a mid-sized B2B SaaS entity**, using Tailscale as the network substrate and a simulated IdP (Google Workspace-style) as the identity source for employees.

> **Why this exists:** typical Tailscale POCs teach the "5 nodes with tags" pattern. This one goes further: it models a **~50-employee company** with 5 functional teams, 9 services, two environments (dev/staging), DataWarehouse, ML serving, customer portal, external auditor, and engineers who log in with corporate SSO. This is the distance between "demo" and "produces a credible RFC".

---

## 1. What Helios is (in this POC)

**Helios** is a fictitious company offering a B2B SaaS for accounts-payable automation aimed at fintechs. It has:

| Characteristic | Value in this POC |
|---|---|
| Size | ~50 employees, distributed across 3 regions (assumed US for the POC) |
| Teams | Platform Eng, Data Eng, SRE, Customer Success, Sales Eng, Security |
| Internal services | 7 (see §3) |
| External services | 1 (customer portal exposed via Funnel) |
| Environments | dev + staging (prod is out-of-scope for the POC) |
| Compliance | SOC 2 in progress; needs fine-grained access auditing |
| Corporate identity | sim. Google Workspace (this POC); real Google Workspace in prod |

---

## 2. Topology

```
                              ┌─────────────────────────────────┐
                              │  Identity Provider (simulated)   │
                              │  Authentik  (Google Workspace    │
                              │  style) — port 9000/9443        │
                              └────────────┬────────────────────┘
                                           │ OIDC discovery
                                           │ (Tailscale/Headscale consumes it)
                                           ▼
                              ┌─────────────────────────────────┐
                              │  Tailscale control plane        │
                              │  (SaaS in this POC)             │
                              │  policy.hujson with group:...   │
                              └────────────┬────────────────────┘
                                           │
       ┌─────────────┬─────────────┬──────┴───────┬──────────────┬──────────────┐
       ▼             ▼             ▼              ▼              ▼              ▼
  ┌─────────┐  ┌──────────┐  ┌──────────┐   ┌──────────┐  ┌──────────┐  ┌──────────┐
  │ admin-  │  │identity- │  │ api-     │   │ customer │  │  ml-     │  │ observ-  │
  │ portal  │  │bridge    │  │ gateway  │   │  portal  │  │ platform │  │ ability  │
  └─────────┘  └──────────┘  └──────────┘   └──────────┘  └──────────┘  └──────────┘
       │             │             │              │              │              │
       │             │             │              │              │              │
       ▼             ▼             ▼              ▼              ▼              ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │  Postgres primary (data/init)              │  Postgres warehouse (data/init) │
  └──────────────────────────────────────────────────────────────────────────────┘
```

**Key points of the topology:**

- Each service runs with a `tailscale/tailscale` sidecar + `network_mode: service:*` (same trick as the original POC, avoids Compose's embedded DNS).
- Each service has a **different tag** (the network namespace is not shared).
- Employees are **nodes in the tailnet with Google identity** (or, in this POC, Authentik) — their `group:` is evaluated in the policy.
- **MiniStack** simulates AWS Secrets Manager + RDS for the secrets patterns.
- **Terraform** seeds the secrets once, before the first `up`.

---

## 3. POC Services (tags)

| Tag | Service | Function | Port |
|---|---|---|---|
| `tag:admin-portal` | Flask app | Internal admin panel (Helios ops + support) | 8080/443 |
| `tag:identity-bridge` | Flask app | Generic SSO bridge (similar to the migration-bridge, agnostic of upstream IdP) | 9090 |
| `tag:api-gateway` | Flask app | Public gateway for B2B clients (Helios clients consume the API) | 8443 |
| `tag:customer-portal` | Flask app | External portal for Helios clients (Tailscale Funnel in prod) | 9443 |
| `tag:primary-db` | Postgres | Main transactional DB (customers, invoices, users) | 5432 |
| `tag:warehouse-db` | Postgres | Data warehouse (analytics, ML training) | 5432 |
| `tag:ml-platform` | Flask app | Serves ML models (fraud scoring, categorization) | 8501 |
| `tag:warehouse-job` | Python job | Batch job that moves data from primary → warehouse | n/a |
| `tag:observability` | Flask app | Metrics (Prometheus-style) + logs | 9100 |
| `tag:eks-gateway` | Python app | Simulates 3 EKS resources (metrics/logs/exec) on different ports | 9100/9101/9102 |

**10 tags, 10 containers, 10 isolated networks.** This is the attack-surface matrix that the policy has to govern.

---

## 4. Personas

The POC simulates 9 personas (Helios employees) who log in to the tailnet via SSO. See `docs/personas.md` for details.

| Persona | Email (simulated) | Google Group | What they can do |
|---|---|---|---|
| Maya (admin) | `maya.admin@helios.example` | `group:helios-admin` | Everything (including SSH) |
| Diego (platform eng) | `diego.platform@helios.example` | `group:platform-eng` | admin-portal, identity-bridge, observability, SSH to those 3 |
| Rafa (data eng) | `rafa.data@helios.example` | `group:data-eng` | warehouse-db, ml-platform (read), warehouse-job (run) |
| Sam (SRE) | `sam.sre@helios.example` | `group:sre` | observability, eks-gateway (9100+9101 read), SSH to eks-gateway |
| Lena (SRE lead) | `lena.sre@helios.example` | `group:sre-lead` | Everything Sam has + eks-gateway:9102 (exec) |
| Carla (customer success) | `carla.cs@helios.example` | `group:customer-success` | customer-portal (read), api-gateway (read), primary-db (read-only via SQL) |
| Tomás (sales eng) | `tomas.sales@helios.example` | `group:sales-eng` | customer-portal (demo data), ml-platform (predict) |
| Nina (auditor) | `nina.auditor@helios.example` | `group:auditors` | observability (read), ml-platform (read) — no exec, no direct DB |
| Eve (simulated external attacker) | `eve.attacker@external.example` | `group:untrusted` | **Nothing** — must be denied everywhere |

**Key distinction:** engineers log in with SSO (`group:...`); **services** use preauth keys with tags. The policy treats both as valid srcs but routes them differently.

---

## 5. POC Components

```
tailscale/
├── README.md                       ← this file
├── ARCHITECTURE.md                 ← detailed design (layers, MapRequest flow, sync points)
├── MATURITY.md                     ← what it demonstrates, what it doesn't, path to production
├── docker-compose.yml              ← service layer
├── docker-compose.identity.yml     ← identity layer (Authentik)
├── docker-compose.ministack.yml    ← AWS simulator
├── .env.example
├── acl/
│   ├── policy.hujson               ← main policy (10 tags, 6 groups, SSH, services)
│   └── services.json               ← advertised services (svc:warehouse-db, svc:ml-platform)
├── identity/
│   ├── docker-compose.yml          ← (reference, same as docker-compose.identity.yml)
│   ├── bootstrap/
│   │   ├── users.json              ← 9 personas with their groups
│   │   ├── groups.json             ← 6 functional groups
│   │   ├── tailscale-oidc.json     ← OIDC provider configured in Authentik
│   │   ├── seed.py                 ← bootstrap script (Authentik API)
│   │   └── requirements.txt
│   └── README.md                   ← how the simulated IdP operates
├── apps/
│   ├── admin-portal/               ← Flask app + Dockerfile
│   ├── identity-bridge/            ← Flask app + Dockerfile (with boto3 + psycopg)
│   ├── api-gateway/                ← Flask app + Dockerfile
│   ├── customer-portal/            ← Flask app + Dockerfile
│   ├── ml-platform/                ← Flask app + Dockerfile (mock model)
│   ├── warehouse-job/              ← Python job (one-shot script + Dockerfile)
│   └── observability/              ← Flask app + Dockerfile (simulated metrics)
├── data/
│   └── init/                       ← bootstrap SQL for primary-db and warehouse-db
├── terraform/                      ← seeds secrets in MiniStack
├── ministack/                      ← MiniStack config
├── scripts/
│   ├── bootstrap.sh                ← full sequence: identity → secrets → tailnet
│   ├── verify.sh                   ← allow/deny matrix (~25 cases)
│   ├── teardown.sh                 ← cleanup
│   └── tailnet-bootstrap.sh        ← generates authkeys per tag via Tailscale API
└── docs/
    ├── personas.md                 ← detail of the 9 personas
    ├── decision-log.md             ← rationale for each piece
    └── diagrams/architecture.mmd   ← Mermaid source
```

---

## 6. How to run it

### Prerequisites

- Docker + Compose v2
- Tailscale account (free tier is enough for this POC)
- Terraform ≥ 1.5 (for the MiniStack part)
- jq, curl, python3

### Sequence (with Google Workspace as IdP)

```bash
# 1. Authkeys: generate 10 reusable auth keys (one per tag) in the Tailscale admin console
#    https://login.tailscale.com/admin/settings/keys
#    Paste them in .env

cp .env.example .env
$EDITOR .env

# 2. Configure Google Workspace as IdP (in production)
#    a. Tailscale admin console → Settings → Identity Providers → Connect Google Workspace
#    b. Select the Google groups to sync to Tailscale via SCIM
#    c. policy.hujson references those groups as src

# 3. (Optional) Start MiniStack to simulate AWS Secrets Manager locally
docker compose -f docker-compose.ministack.yml up -d

# 4. Seed secrets in MiniStack via Terraform
cd terraform && terraform init && terraform apply -auto-approve && cd ..

# 5. Start services (each with its tailscale sidecar)
docker compose up -d --build

# 6. Apply the policy in the Tailscale admin console
#    Paste the contents of acl/policy.hujson into Access Controls

# 7. Run the verification matrix
./scripts/verify.sh
```

### Alternative sequence (with Authentik as Google Workspace simulator)

If you want to validate the IdP pattern without depending on a real Google Workspace, you can use Authentik (the original setup) — useful when the POC runs on a laptop without access to Helios's real Google Workspace:

```bash
docker compose -f docker-compose.identity.yml up -d
docker compose -f docker-compose.ministack.yml up -d
docker compose -f docker-compose.identity.yml run --rm id-bootstrap  # creates users/groups
# Then configure Tailscale admin console → SSO → use Authentik as the issuer
```

**Key differences: real Google Workspace vs simulated Authentik**
- **SCIM sync**: Google Workspace → automatic; Authentik → manual (re-run `seed.py`)
- **MFA**: Google Workspace → configurable via Google admin; Authentik → TOTP/WebAuthn
- **Admin UI**: Google Workspace → `admin.google.com`; Authentik → `localhost:9000`
- **Everything else (OIDC, groups in policy, etc.) is identical**

### Cleanup

```bash
./scripts/teardown.sh
docker compose down -v
docker compose -f docker-compose.identity.yml down -v
docker compose -f docker-compose.ministack.yml down -v
```

---

## 7. What this POC **proves** vs the original POC

| Question | Original POC (previous POC) | Helios (this one) |
|---|---|---|
| Do tag-based ACLs work? | ✅ 5 tags | ✅ 10 tags, more complex scenarios |
| Do Tailscale Services (svc:X) work? | ✅ `svc:rds-sim` | ✅ `svc:warehouse-db`, `svc:ml-platform` (multiple) |
| Does SSH bastion-less work? | ✅ basic | ✅ with group check + "DMZ with privileges" logic |
| Does the `Tailscale-User-*` header flow? | ✅ basic | ✅ + comparison with/without |
| Does it work with IdP SSO? | ❌ not tested | ✅ Authentik + OIDC + groups |
| Granular by IdP group? | ❌ | ✅ `group:platform-eng@helios.example` |
| dev/staging differentiation? | ❌ | ✅ two separate environments |
| Does it work with multiple DBs? | ❌ | ✅ primary-db + warehouse-db, different groups |
| Access auditing? | partial | ✅ `tag:observability` with detailed metrics |
| Customer portal exposed via Funnel? | ❌ | ✅ modeled (not exposed publicly) |
| Realistic multi-persona? | ❌ 2 engineers | ✅ 9 personas, 6 groups |

---

## 8. What it does **NOT** prove (honestly)

| Gap | When it matters |
|---|---|
| MDM rollout (Apple Business Manager, Mosyle, Intune) | When Helios decides employees receive pre-configured laptops |
| Scaling to +100 nodes | The Tailscale/Headscale mapper is measured for +5K nodes/tailnet, but the policy becomes hard to maintain by hand beyond ~50 nodes |
| HA subnet router failover | Helios is multi-tenant SaaS; if it goes prod, subnet routers must be HA |
| Policy as code (PR review of `policy.hujson`) | The POC applies the policy via the admin console; in prod it should live in git with CI |
| Integration with real Vault (not MiniStack) | When Helios touches real AWS; the pattern is the same, the addresses change |
| Automatic secrets rotation | The POC reads secrets once and caches; in prod they rotate every N days |
| Custom claim enrichment (Google claims → ACL attrs) | Tailscale supports it, but requires custom OIDC mapping |

---

## 9. Maturity roadmap

See `MATURITY.md`. Short version:

1. ✅ This POC: pattern validated locally, ~50 nodes in mind.
2. ⏭ Real Helios staging: bring up the same services in AWS staging, use real Google Workspace (not Authentik), add MDM.
3. ⏭ Production: define SLOs, alerting, on-call, incident runbook, disaster-recovery tests.
4. ⏭ Headscale evaluation: if compliance asks for an on-prem control plane, stand up Headscale as drop-in (the same `policy.hujson` should work; see `decision-log.md`).
