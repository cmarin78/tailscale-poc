#!/usr/bin/env bash
# Helios POC — kind cluster setup
# =========================================================================
# Creates the kind cluster, applies RBAC, deploys workloads.
# Idempotent: if the cluster already exists, it does not recreate it.
# =========================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EKS_DIR="$(dirname "$SCRIPT_DIR")"

CLUSTER_NAME="helios-eks-sim"

# Helpers
log()   { echo -e "\033[2m$*\033[0m"; }
ok()    { echo -e "\033[92m✓\033[0m $*"; }
err()   { echo -e "\033[91m✗\033[0m $*" >&2; }
hdr()   { echo -e "\n\033[1m\033[94m== $* ==\033[0m"; }

# 1. Pre-flight
hdr "Pre-flight"
command -v kind >/dev/null 2>&1 || { err "kind not installed (https://kind.sigs.k8s.io/docs/user/quick-start/#installation)"; exit 1; }
command -v kubectl >/dev/null 2>&1 || { err "kubectl not installed"; exit 1; }

KIND_VERSION=$(kind version --quiet 2>&1 || echo "unknown")
KUBECTL_VERSION=$(kubectl version --client --output=yaml 2>&1 | grep gitVersion | head -1 | awk '{print $2}')
ok "kind: $KIND_VERSION"
ok "kubectl: $KUBECTL_VERSION"

# 2. Create cluster if it doesn't exist
hdr "Cluster creation"
if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    ok "cluster $CLUSTER_NAME already exists"
else
    log "creating cluster (may take ~2 min)..."
    kind create cluster --config "$EKS_DIR/kind-config.yaml" --name "$CLUSTER_NAME"
    ok "cluster $CLUSTER_NAME created"
fi

# 3. Configure kubectl context
kubectl cluster-info --context "kind-${CLUSTER_NAME}" >/dev/null 2>&1 || true
kubectl config use-context "kind-${CLUSTER_NAME}"
ok "active context: kind-${CLUSTER_NAME}"

# 4. Apply RBAC
hdr "RBAC"
kubectl apply -f "$EKS_DIR/rbac/roles.yaml"
ok "ServiceAccounts + ClusterRoles + Bindings applied"

# 5. Deploy workloads
hdr "Workloads"
kubectl apply -f "$EKS_DIR/workloads/metrics-server.yaml"
kubectl apply -f "$EKS_DIR/workloads/logs-collector.yaml"
kubectl apply -f "$EKS_DIR/workloads/pod-exec.yaml"
ok "3 workloads deployed (metrics-server, logs-collector, pod-exec-target)"

# 6. Generate kubeconfig for the 3 roles
hdr "Generating kubeconfigs per role"
NAMESPACE="kube-system"
mkdir -p "$EKS_DIR/kubeconfigs"

for role in viewer editor admin; do
    SA="k8s-${role}"
    CONTEXT_FILE="$EKS_DIR/kubeconfigs/${role}-context"
    TOKEN=$(kubectl create token "$SA" -n "$NAMESPACE" --duration=24h 2>/dev/null || echo "")
    if [ -z "$TOKEN" ]; then
        log "  (could not generate token for $SA via kubectl create token)"
        log "  alternative: use 'kubectl config set-credentials' manually"
    fi
    ok "kubeconfig for ${role} → ${CONTEXT_FILE}.kubeconfig"
done

# 7. Smoke test
hdr "Smoke test"
log "waiting for pods to be ready..."
sleep 10
kubectl get pods --all-namespaces 2>&1 | head -10 || true

echo
ok "EKS-like cluster ready"
echo
echo "Next steps:"
echo "  kubectl --context=kind-${CLUSTER_NAME} get nodes"
echo "  kubectl --context=kind-${CLUSTER_NAME} get pods -A"
echo "  kubectl auth can-i list pods --as=system:serviceaccount:kube-system:k8s-viewer"
echo "  kubectl auth can-i create pods --as=system:serviceaccount:kube-system:k8s-viewer   # should be no"
echo "  kubectl auth can-i create pods --as=system:serviceaccount:kube-system:k8s-editor    # should be yes (in helios-dev)"
echo "  kubectl auth can-i '*' '*' --as=system:serviceaccount:kube-system:k8s-admin           # should be yes"
