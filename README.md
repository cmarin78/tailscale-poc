# Helios POC — Tailscale SaaS variant

**Realistic access management POC for a mid-sized B2B SaaS company** — uses Tailscale as the network substrate and a simulated IdP (Google Workspace-style) as the identity source.

> **Why this exists:** typical Tailscale POCs teach the "5 nodes with tags" pattern. This one models a **~50-employee company** with 5 functional teams, 9 services, two environments (dev/staging), DataWarehouse, ML serving, customer portal, external auditor, and engineers who log in with corporate SSO.

## Repo layout

```
.
├── README.md               # this file
├── ROADMAP.md              # full work plan
├── ARCHITECTURE.md         # layers, decisions, components
├── POC_OPERATIONS.md       # cheatsheet, troubleshooting, workflows
├── MATURITY.md             # Level 1-4 roadmap
├── docker-compose.yml      # 10 services + sidecars + personas
├── docker-compose.identity.yml  # Authentik stack (IdP sim)
├── acl/                    # policy.hujson + variants
├── apps/                   # 10 Flask apps + Grafana + intranet
├── identity/               # Authentik config + bootstrap
├── ngrok/                  # tunnel for IdP SSO callback
├── terraform/              # secrets module
├── ministack/              # AWS-like simulator
├── eks/                    # kind cluster sim
├── scripts/
│   ├── heliosctl           # lifecycle CLI (start/stop/status/destroy/clean)
│   ├── verify.sh           # 46-case allow/deny matrix
│   ├── demo.sh             # 7-step guided demo
│   └── generate_docs.py    # produces docs/Helios-POC-Documentation.docx
├── docs/                   # captures + diagrams (PNG)
└── tools/
    ├── tsctl.py            # admin CLI for Tailscale API
    └── lib/, tsctl/        # helper modules
```

## Quickstart

```bash
# 1. Configure secrets
cp .env.example .env
$EDITOR .env  # add TAILSCALE_API_KEY, TAILSCALE_TAILNET, NGROK_AUTHTOKEN

# 2. Validate POC is ready
./scripts/heliosctl validate

# 3. Bring up services + personas
./scripts/heliosctl start services
./scripts/heliosctl start personas

# 4. Apply ACL policy
python3 tools/tsctl.py policy set acl/policy.hujson

# 5. Run verification matrix
bash scripts/verify.sh
```

See [POC_OPERATIONS.md](POC_OPERATIONS.md) for full workflows.

## Comparison with `headscale-poc`

For the parallel POC using Headscale self-hosted as control plane, see [`cmarin78/headscale-poc`](https://github.com/cmarin78/headscale-poc).

Same architecture, same policies (HuJSON is portable), different control plane infra.

## License

MIT — POC for evaluation purposes.
