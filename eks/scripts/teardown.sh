#!/usr/bin/env bash
# Helios POC — kind cluster teardown
# =========================================================================
# Destroys the kind cluster created by setup.sh.
# =========================================================================

set -euo pipefail

CLUSTER_NAME="helios-eks-sim"

if command -v kind >/dev/null 2>&1 && kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    kind delete cluster --name "$CLUSTER_NAME"
    echo "✓ cluster $CLUSTER_NAME destroyed"
else
    echo "(cluster $CLUSTER_NAME does not exist — skip)"
fi

# Clean up generated kubeconfigs
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EKS_DIR="$(dirname "$SCRIPT_DIR")"
rm -rf "$EKS_DIR/kubeconfigs"
echo "✓ kubeconfigs/ cleaned"
