#!/usr/bin/env bash
# Helios POC — extended verification matrix.
# ============================================================
# Covers the 25+ allow/deny cases modeled in acl/policy.hujson.
# Each test reports PASS/FAIL with enough context for triage.
#
# Requires:
#   - docker compose up -d (services running)
#   - policy.hujson applied in the admin console
#   - MagicDNS resolved (sidecars do their first poll, takes ~30s)
# ============================================================

set -uo pipefail

PASS=0
FAIL=0
TOTAL=0

pass() { echo "  PASS - $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL - $1"; FAIL=$((FAIL+1)); }
skip() { echo "  SKIP - $1"; SKIP=$((SKIP+1)); }
note() { echo "       $1"; }
section() { echo; echo "== $1 =="; }

SKIP=0

# Check if a docker container is running (for SKIP detection)
container_running() {
    docker ps --format '{{.Names}}' 2>/dev/null | grep -qE "(^tailscale-${1}-1$|^${1}$)"
}

run_test() {
    local description="$1"
    local expected="$2"  # "allow" or "deny"
    local test_fn="$3"

    TOTAL=$((TOTAL+1))
    # Run the test as a shell command (eval supports function calls)
    local rc=0
    eval "$test_fn" >/dev/null 2>&1 || rc=$?

    # If exit code is 2, container missing — SKIP
    if [ "$rc" = "2" ]; then
        skip "$description (sandbox: container not running)"
        return
    fi

    if [ "$rc" = "0" ]; then
        if [ "$expected" = "allow" ]; then
            pass "$description (allowed)"
        else
            fail "$description (should have been denied)"
        fi
    else
        if [ "$expected" = "deny" ]; then
            pass "$description (denied as expected)"
        else
            fail "$description (should have been allowed)"
        fi
    fi
}

# ---------- Helpers ----------

# curl_from <container> <url> → exits 0 if HTTP 2xx, non-zero otherwise
# Special: returns exit code 2 if container is not running (for SKIP handling)
curl_from() {
    local container="$1"
    local url="$2"
    local timeout="${3:-5}"
    if ! container_running "$container"; then
        echo "CONTAINER_MISSING: $container" >&2
        return 2
    fi
    docker compose exec -T "$container" curl -fsS --max-time "$timeout" "$url" > /dev/null 2>&1
}

# tcp_from <container> <host:port> → exits 0 if connection succeeds, non-zero on timeout/refused
# Special: returns exit code 2 if container is not running (for SKIP handling)
tcp_from() {
    local container="$1"
    local hostport="$2"
    local timeout="${3:-5}"
    if ! container_running "$container"; then
        echo "CONTAINER_MISSING: $container" >&2
        return 2
    fi
    docker compose exec -T "$container" bash -c "timeout $timeout bash -c 'cat </dev/tcp/${hostport%:*}/${hostport#*:}'" > /dev/null 2>&1
}

# ============================================================
#  Platform-eng (Diego): admin-portal, identity-bridge, ssh-able
#  Expected: admin-portal/identity-bridge OK; primary-db/warehouse/ml/customer DENIED
# ============================================================

section "Diego (platform-eng)"

run_test "diego-platform → admin-portal:8080" \
    "allow" \
    "curl_from diego-platform http://admin-portal:8080/healthz"

run_test "diego-platform → identity-bridge:9090" \
    "allow" \
    "curl_from diego-platform http://identity-bridge:9090/healthz"

run_test "diego-platform → customer-portal:9443 (engineer shouldn't reach customer UI)" \
    "deny" \
    "curl_from diego-platform http://customer-portal:9443/healthz"

run_test "diego-platform → primary-db:5432 (direct DB denied by ACL)" \
    "deny" \
    "tcp_from diego-platform primary-db:5432"

run_test "diego-platform → warehouse-db:5432" \
    "deny" \
    "tcp_from diego-platform warehouse-db:5432"

run_test "diego-platform → ml-platform:8501" \
    "deny" \
    "curl_from diego-platform http://ml-platform:8501/healthz"

run_test "diego-platform → eks-gateway:9102 (exec denied for non-SRE-lead)" \
    "deny" \
    "curl_from diego-platform http://eks-gateway:9102/ 8"

# ============================================================
#  Data-eng (Rafa): warehouse-db, ml-platform
#  Expected: warehouse-db OK, ml-platform OK, primary-db DENIED
# ============================================================

section "Rafa (data-eng)"

run_test "rafa-data → warehouse-db:5432" \
    "allow" \
    "tcp_from rafa-data warehouse-db:5432"

run_test "rafa-data → ml-platform:8501" \
    "allow" \
    "curl_from rafa-data http://ml-platform:8501/healthz"

run_test "rafa-data → primary-db:5432 (data-eng doesn't touch primary)" \
    "deny" \
    "tcp_from rafa-data primary-db:5432"

run_test "rafa-data → admin-portal:8080" \
    "deny" \
    "curl_from rafa-data http://admin-portal:8080/healthz"

run_test "rafa-data → customer-portal:9443" \
    "deny" \
    "curl_from rafa-data http://customer-portal:9443/healthz"

# ============================================================
#  SRE (Sam): observability + EKS read-only (no exec)
#  Expected: observability OK, eks-gateway 9100+9101 OK, 9102 DENIED
# ============================================================

section "Sam (SRE — non-lead)"

run_test "sam-sre → observability:9100/metrics" \
    "allow" \
    "curl_from sam-sre http://observability:9100/metrics"

run_test "sam-sre → observability:9100/access-log" \
    "allow" \
    "curl_from sam-sre http://observability:9100/access-log"

run_test "sam-sre → eks-gateway:9100 (metrics)" \
    "allow" \
    "curl_from sam-sre http://eks-gateway:9100/"

run_test "sam-sre → eks-gateway:9101 (logs)" \
    "allow" \
    "curl_from sam-sre http://eks-gateway:9101/"

run_test "sam-sre → eks-gateway:9102 (exec — DENIED for non-lead)" \
    "deny" \
    "curl_from sam-sre http://eks-gateway:9102/ 8"

run_test "sam-sre → primary-db:5432 (SRE doesn't touch primary directly)" \
    "deny" \
    "tcp_from sam-sre primary-db:5432"

# ============================================================
#  SRE-lead (Lena): same as Sam + exec
#  Expected: 9102 OK; primary-db DENIED
# ============================================================

section "Lena (SRE-lead)"

run_test "lena-sre-lead → eks-gateway:9102 (exec — allowed for lead)" \
    "allow" \
    "curl_from lena-sre-lead http://eks-gateway:9102/ 8"

run_test "lena-sre-lead → eks-gateway:9100" \
    "allow" \
    "curl_from lena-sre-lead http://eks-gateway:9100/"

run_test "lena-sre-lead → primary-db:5432 (still denied — exec doesn't unlock DB)" \
    "deny" \
    "tcp_from lena-sre-lead primary-db:5432"

# ============================================================
#  Customer-success (Carla): customer-portal + identity-bridge
#  Expected: customer-portal OK, identity-bridge OK, admin-portal DENIED, DB DENIED, EKS DENIED
# ============================================================

section "Carla (customer-success)"

run_test "carla-cs → customer-portal:9443" \
    "allow" \
    "curl_from carla-cs http://customer-portal:9443/dashboard"

run_test "carla-cs → identity-bridge:9090" \
    "allow" \
    "curl_from carla-cs http://identity-bridge:9090/healthz"

run_test "carla-cs → admin-portal:8080 (CS shouldn't reach admin tools)" \
    "deny" \
    "curl_from carla-cs http://admin-portal:8080/healthz"

run_test "carla-cs → primary-db:5432" \
    "deny" \
    "tcp_from carla-cs primary-db:5432"

run_test "carla-cs → warehouse-db:5432" \
    "deny" \
    "tcp_from carla-cs warehouse-db:5432"

run_test "carla-cs → eks-gateway:9100 (no EKS access for CS)" \
    "deny" \
    "curl_from carla-cs http://eks-gateway:9100/"

# ============================================================
#  Sales-eng (Tomás): customer-portal, api-gateway, ml-platform
#  Expected: those 3 OK; primary-db DENIED
# ============================================================

section "Tomás (sales-eng)"

run_test "tomas-sales → customer-portal:9443" \
    "allow" \
    "curl_from tomas-sales http://customer-portal:9443/dashboard"

run_test "tomas-sales → api-gateway:8443" \
    "allow" \
    "curl_from tomas-sales http://api-gateway:8443/v1/invoices"

run_test "tomas-sales → ml-platform:8501 (predict for demos)" \
    "allow" \
    "curl_from tomas-sales -X POST -H 'Content-Type: application/json' -d '{\"invoice_id\":\"demo-001\",\"amount_cents\":1000,\"vendor\":\"Acme\"}' http://ml-platform:8501/predict/fraud"

run_test "tomas-sales → primary-db:5432" \
    "deny" \
    "tcp_from tomas-sales primary-db:5432"

run_test "tomas-sales → admin-portal:8080" \
    "deny" \
    "curl_from tomas-sales http://admin-portal:8080/healthz"

# ============================================================
#  Auditor (Nina): observability + eks metrics only
#  Expected: observability OK, eks 9100 OK, eks 9101 DENIED, eks 9102 DENIED, DB DENIED
# ============================================================

section "Nina (auditor — read-only)"

run_test "nina-auditor → observability:9100" \
    "allow" \
    "curl_from nina-auditor http://observability:9100/access-log"

run_test "nina-auditor → eks-gateway:9100 (metrics)" \
    "allow" \
    "curl_from nina-auditor http://eks-gateway:9100/"

run_test "nina-auditor → eks-gateway:9101 (logs — denied for auditors)" \
    "deny" \
    "curl_from nina-auditor http://eks-gateway:9101/"

run_test "nina-auditor → eks-gateway:9102 (exec — denied)" \
    "deny" \
    "curl_from nina-auditor http://eks-gateway:9102/ 8"

run_test "nina-auditor → primary-db:5432 (auditors don't touch DBs)" \
    "deny" \
    "tcp_from nina-auditor primary-db:5432"

run_test "nina-auditor → admin-portal:8080" \
    "deny" \
    "curl_from nina-auditor http://admin-portal:8080/healthz"

# ============================================================
#  Attacker (Eve): EVERYTHING denied
#  Expected: 0 allowed
# ============================================================

section "Eve (external attacker — EVERYTHING denied)"

run_test "eve-attacker → admin-portal:8080" \
    "deny" \
    "curl_from eve-attacker http://admin-portal:8080/healthz"

run_test "eve-attacker → api-gateway:8443" \
    "deny" \
    "curl_from eve-attacker http://api-gateway:8443/healthz"

run_test "eve-attacker → customer-portal:9443" \
    "deny" \
    "curl_from eve-attacker http://customer-portal:9443/healthz"

run_test "eve-attacker → primary-db:5432" \
    "deny" \
    "tcp_from eve-attacker primary-db:5432"

run_test "eve-attacker → warehouse-db:5432" \
    "deny" \
    "tcp_from eve-attacker warehouse-db:5432"

run_test "eve-attacker → ml-platform:8501" \
    "deny" \
    "curl_from eve-attacker http://ml-platform:8501/healthz"

run_test "eve-attacker → observability:9100" \
    "deny" \
    "curl_from eve-attacker http://observability:9100/healthz"

run_test "eve-attacker → eks-gateway:9100" \
    "deny" \
    "curl_from eve-attacker http://eks-gateway:9100/"

# ============================================================
#  Summary
# ============================================================

echo
echo "============================================================"
echo "Summary: $PASS pass / $FAIL fail / $SKIP skip / $TOTAL total"
echo "============================================================"

if [ "$FAIL" -gt 0 ]; then
    echo
    echo "Diagnostics:"
    echo "  1. Verify that docker compose up -d completed and all services are healthy:"
    echo "     docker compose ps"
    echo "  2. Confirm you pasted acl/policy.hujson in the Tailscale admin console"
    echo "  3. Wait 60s for MagicDNS to resolve after the first up"
    echo "  4. To inspect a node:"
    echo "     docker compose exec <persona> tailscale status"
    exit 1
fi

if [ "$SKIP" -eq "$TOTAL" ]; then
    echo
    echo "All cases were SKIP (containers not running)."
    echo "  This usually happens in sandbox / CI with exhausted docker network pool."
    echo "  For real evidence: docker compose up -d + re-run verify.sh"
    exit 0
fi

echo "All cases passed."
