# Helios POC — Simulated EKS with kind

This directory simulates a real EKS cluster using [kind](https://kind.sigs.k8s.io/) (Kubernetes IN Docker). The cluster brings up 3 nodes (1 control-plane + 2 workers) and loads 3 workloads representing the typical EKS resources that Tailscale would expose as services.

## Quick start

```bash
# 1. Setup (creates cluster + RBAC + workloads)
./eks/scripts/setup.sh

# 2. Validate
kubectl --context=kind-helios-eks-sim get nodes
kubectl --context=kind-helios-eks-sim get pods -A

# 3. Test RBAC
kubectl auth can-i list pods --as=system:serviceaccount:kube-system:k8s-viewer  # yes
kubectl auth can-i create pods --as=system:serviceaccount:kube-system:k8s-viewer # no
kubectl auth can-i '*' '*' --as=system:serviceaccount:kube-system:k8s-admin         # yes

# 4. (Optional) Integrate with Tailscale
# - Expose the kind API server via Tailscale (tag:eks-api)
# - Load kubeconfig into the persona containers
```

## Components

| File | What |
|---|---|
| `kind-config.yaml` | Cluster config (3 nodes, 100.64/12 network to match Tailscale) |
| `rbac/roles.yaml` | 3 ClusterRoles (viewer, editor, admin) + bindings + 3 namespaces (dev/staging/prod) |
| `workloads/metrics-server.yaml` | Pod that simulates metrics (port 9100) |
| `workloads/logs-collector.yaml` | Pod that simulates logs (port 9101) |
| `workloads/pod-exec.yaml` | Pod that simulates exec (port 9102) — equivalent to "shell into pod" |
| `scripts/setup.sh` | Idempotent setup |
| `scripts/teardown.sh` | Destroys the cluster |

## Mapping to Tailscale tags

| RBAC role | Suggested Tailscale tag | ACL grant |
|---|---|---|
| `helios-viewer` | `tag:k8s-viewer` | read-only on all resources |
| `helios-editor` | `tag:k8s-editor` | read+write in dev/staging namespaces (NOT prod) |
| `helios-admin` | `tag:k8s-admin` | full cluster |

## Mapping to Helios groups (Google Workspace)

| Google group | RBAC role | Justification |
|---|---|---|
| `group:auditors@helios.example` | viewer | Read-only access for auditing |
| `group:sre@helios.example` | viewer | SREs see metrics+logs but not exec |
| `group:sre-lead@helios.example` | admin | SRE leads can exec |
| `group:platform-eng@helios.example` | editor | Deploys in dev/staging |
| `group:data-eng@helios.example` | viewer | They only see jobs |
| `group:customer-success@helios.example` | viewer (limited) | Only sees apps, not infra |
| `group:sales-eng@helios.example` | deny | No access to K8s |

## RBAC smoke tests

```bash
# Viewer: read-only
kubectl auth can-i list pods --as=system:serviceaccount:kube-system:k8s-viewer
# → yes

kubectl auth can-i create pods --as=system:serviceaccount:kube-system:k8s-viewer
# → no

# Editor: read+write in dev/staging, NOT prod
kubectl auth can-i create pods --as=system:serviceaccount:kube-system:k8s-editor -n helios-dev
# → yes

kubectl auth can-i create pods --as=system:serviceaccount:kube-system:k8s-editor -n helios-prod
# → no

# Admin: full
kubectl auth can-i '*' '*' --as=system:serviceaccount:kube-system:k8s-admin
# → yes (everything)
```

## Differences from real EKS

| Feature | kind | Real EKS |
|---|---|---|
| IAM (IRSA) | ❌ | ✅ (use IAM roles for service accounts) |
| AWS VPC CNI | ❌ (kindnet) | ✅ |
| ALB controller | ❌ | ✅ |
| Secrets Manager integration | ❌ | ✅ (with External Secrets Operator) |
| KMS encryption | ❌ | ✅ |
| Spot instances | ❌ | ✅ |
| Managed node groups | ❌ | ✅ |
| Cluster autoscaler | ❌ | ✅ |
| 99.95% SLA | ❌ | ✅ |

kind is for **validating the access pattern**, not for validating the real operation of EKS. For that we'd need the cluster in actual AWS.

## Next step (Phase D — Full integration)

1. Expose the kind API server via Tailscale (tag:eks-api)
2. Mount the kubeconfig with the 3 contexts in the persona containers
3. `heliosctl start eks` to bring up kind + load RBAC
4. `heliosctl status` to also show the kind status
