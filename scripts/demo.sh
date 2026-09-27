#!/usr/bin/env bash
# ============================================================================
# Helios POC — End-to-end guided demo
# ============================================================================
# Walks through the whole POC showing each step. Designed for recording videos
# or for a stakeholder to watch it run.
#
# Usage:
#   scripts/demo.sh [--fast] [--stop-at=N]
#     --fast: skip long waits (for quick repetition)
#     --stop-at=N: stop after step N (1-7)
#
# Prerequisites:
#   - .env with TS_AUTHKEY_* and NGROK_AUTHTOKEN filled in
#   - ngrok account configured (if you'll show SSO)
#   - kind installed (if you'll show EKS RBAC)
# ============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

FAST=0
STOP_AT=99
for arg in "$@"; do
    case "$arg" in
        --fast) FAST=1 ;;
        --stop-at=*) STOP_AT="${arg#--stop-at=}" ;;
        *) echo "usage: $0 [--fast] [--stop-at=N]"; exit 1 ;;
    esac
done

# Presentation helpers
banner() {
    echo
    echo "╔════════════════════════════════════════════════════════════════╗"
    printf "║  %-64s║\n" "$1"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo
}

step() {
    local n="$1"; local desc="$2"
    echo
    echo "─── Step $n: $desc ──────────────────────────────────────────"
    echo
}

pause() {
    if [ "$FAST" -eq 0 ]; then
        sleep "${1:-2}"
    fi
}

wait_user() {
    if [ "$FAST" -eq 0 ] && [ -t 0 ]; then
        read -rp "[Enter to continue, Ctrl+C to exit] " _
    fi
}

# ============================================================================
banner "Helios POC — End-to-end demo"
echo "This demo walks through 7 steps:"
echo "  1. Validate the setup"
echo "  2. Bring up the full stack"
echo "  3. Show the tailnet (devices in Tailscale)"
echo "  4. Verify the applied policy"
echo "  5. Validate RBAC of the simulated EKS cluster"
echo "  6. Show the allow/deny matrix (verify.sh)"
echo "  7. Clean up / leave it running"
echo
echo "Total time: ~5 minutes (with --fast: ~1 minute)"
pause 3

# ============================================================================
step 1 "Setup validation"

echo "→ Running heliosctl validate..."
./scripts/heliosctl validate 2>&1 | tail -20
pause 2

# ============================================================================
[ "$STOP_AT" -lt 2 ] && exit 0
step 2 "Bring up the full stack"

echo "→ See what's running before..."
./scripts/heliosctl status 2>&1 | head -15
echo
echo "→ Bring up everything (this may take 2-5 min the first time due to build)..."
./scripts/heliosctl start all 2>&1 | tail -30
pause 5

echo
echo "→ Status after start..."
./scripts/heliosctl status 2>&1 | tail -15
pause 3

# ============================================================================
[ "$STOP_AT" -lt 3 ] && exit 0
step 3 "Show the tailnet (devices in Tailscale)"

echo "→ List devices in the cerberusbyte.com tailnet..."
python3 ../tools/tsctl.py device list 2>&1 | tail -20
echo
echo "→ Filter by tag (e.g. tag:eks-gateway)..."
python3 ../tools/tsctl.py device list --tag tag:eks-gateway 2>&1 | tail -10
pause 3

# ============================================================================
[ "$STOP_AT" -lt 4 ] && exit 0
step 4 "Verify the applied policy"

echo "→ Current tailnet policy (first 30 lines)..."
python3 ../tools/tsctl.py policy get 2>&1 | head -30
echo
echo "→ Tag owners in the policy..."
python3 ../tools/tsctl.py policy get 2>&1 | grep -E '"tag:' | head -15
pause 3

# ============================================================================
[ "$STOP_AT" -lt 5 ] && exit 0
step 5 "Validate RBAC of the simulated EKS cluster"

echo "→ If you ran 'heliosctl start eks', kind is running..."
echo "→ Validate cluster RBAC: viewer CANNOT create pods, editor CAN..."
echo
if command -v kind >/dev/null 2>&1 && kind get clusters 2>/dev/null | grep -q "helios-eks-sim"; then
    echo "→ Cluster detected. Running RBAC checks..."
    KUBECTL="kubectl --context=kind-helios-eks-sim"
    echo
    echo "── viewer (read-only):"
    $KUBECTL auth can-i list pods --as=system:serviceaccount:kube-system:k8s-viewer 2>&1 | head -1 | sed 's/^/   /'
    $KUBECTL auth can-i create pods --as=system:serviceaccount:kube-system:k8s-viewer 2>&1 | head -1 | sed 's/^/   /'
    $KUBECTL auth can-i get pods/log --as=system:serviceaccount:kube-system:k8s-viewer 2>&1 | head -1 | sed 's/^/   /'
    echo
    echo "── editor (read+write in dev/staging, NOT prod):"
    $KUBECTL auth can-i create pods --as=system:serviceaccount:kube-system:k8s-editor -n helios-dev 2>&1 | head -1 | sed 's/^/   /'
    $KUBECTL auth can-i create pods --as=system:serviceaccount:kube-system:k8s-editor -n helios-prod 2>&1 | head -1 | sed 's/^/   /'
    echo
    echo "── admin (full):"
    $KUBECTL auth can-i '*' '*' --as=system:serviceaccount:kube-system:k8s-admin 2>&1 | head -1 | sed 's/^/   /'
    echo
    echo "→ List deployed workloads..."
    $KUBECTL get pods -A 2>&1 | head -10
else
    echo "  (kind is not running. To see this part:"
    echo "   $ heliosctl start eks   (requires 'kind' installed)"
    echo "   $ scripts/demo.sh)"
fi
pause 5

# ============================================================================
[ "$STOP_AT" -lt 6 ] && exit 0
step 6 "Allow/deny matrix (verify.sh)"

echo "→ If the services are running, run the verification matrix..."
echo "→ (this proves the policy works end-to-end)"
echo
echo "→ Waiting 60s for MagicDNS to resolve between sidecars..."
pause 60

if docker compose ps --services --filter "running" 2>/dev/null | grep -q admin-portal; then
    ./scripts/heliosctl verify 2>&1 | tail -50
else
    echo "  (services are not running — to see this:"
    echo "   $ heliosctl restart services personas"
    echo "   $ scripts/demo.sh)"
fi
pause 5

# ============================================================================
[ "$STOP_AT" -lt 7 ] && exit 0
step 7 "Wrap-up and cleanup"

echo "→ Final status..."
./scripts/heliosctl status 2>&1 | tail -15
echo
echo "→ Do you want to leave the stack running or destroy it?"
echo "  - 'heliosctl stop all' — stops containers, keeps state"
echo "  - 'heliosctl destroy' — nuke EVERYTHING (with confirmation)"
echo
echo "To re-run the demo:"
echo "  scripts/demo.sh --fast    # fast version"
echo
echo "To run only one step:"
echo "  scripts/demo.sh --stop-at=3"
pause 3

banner "Demo complete"
echo "Next steps toward production:"
echo "  1. Migrate Tailscale SaaS → Headscale if compliance asks for on-prem (see docs/comparison.md)"
echo "  2. Setup MDM (Apple Business Manager / Mosyle / Intune)"
echo "  3. Activate Prometheus alerts + on-call runbook"
echo "  4. Audit Tailscale logs in SIEM"
echo
echo "Comparison with your previous POC (Axial):"
echo "  - Axial: 5 tags, 1 policy file, no SSO testing"
echo "  - Helios: 13 tags, 4 policy versions, simulated SSO, EKS RBAC, ngrok ready"
echo
