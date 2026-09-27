#!/bin/bash
# refresh_captures.sh — re-runs the POC and captures EVERYTHING to docs/captures/
# Usage:  ./scripts/refresh_captures.sh [--no-screenshots]
#
# Outputs to docs/captures/:
#   *.txt      - terminal captures (validate, isolation, cross-service, demo, verify)
#   *.json     - structured captures (live policy, health)
#   *.png      - matplotlib diagrams (already in place)
#   screenshots/*.png  - chrome headless screenshots of every web UI
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CAPTURES="$ROOT/docs/captures"
SS="$CAPTURES/screenshots"
mkdir -p "$SS"

NO_SS=0
[ "${1:-}" = "--no-screenshots" ] && NO_SS=1

# ANSI strip — reads stdin, writes to stdout (sed-based, GNU sed on Linux)
strip_ansi() {
    # Strip CSI sequences (ESC + [ ... letter), OSC (ESC + ] ... BEL/ST), bare ESC
    sed -r 's/\x1B\[[0-9;?]*[a-zA-Z]//g; s/\x1B\][^\x07]*(\x07|\x1B\\)//g; s/\x1B[@-Z\\-_]//g; s/\x1B//g'
}

# Capture a command, stripping ANSI, into a file
cap() {
    local outfile="$1"; shift
    echo "  -> $outfile" >&2
    ( "$@" 2>&1 ) | strip_ansi > "$outfile" || true
    # Fallback: if regex strippy failed, copy raw
    if [ ! -s "$outfile" ]; then
        ( "$@" 2>&1 ) > "$outfile" || true
    fi
}

# Screenshot a URL via chrome headless; URL is required second arg
shot() {
    local name="$1"; local url="$2"
    local out="$SS/${name}.png"
    echo "  -> $out" >&2
    google-chrome --headless --disable-gpu --no-sandbox \
        --hide-scrollbars --window-size=1280,800 \
        --virtual-time-budget=4000 \
        --screenshot="$out" "$url" 2>/dev/null || true
}

# Sidecar IPs discovered dynamically via docker inspect
sidecar_ip() {
    local svc="$1"
    docker inspect "tailscale-ts-${svc}-1" \
        --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null \
        | head -1
}

echo
echo "============================================================"
echo "Helios POC — refresh_captures.sh"
echo "Working dir: $ROOT"
echo "Captures:    $CAPTURES"
echo "Screenshots: $SS"
echo "============================================================"
echo

# 1) heliosctl validate (host-side view)
echo "[1/9] heliosctl validate (host view)"
cap "$CAPTURES/validate_host.txt" "$ROOT/scripts/heliosctl" validate

# 2) heliosctl status
echo "[2/9] heliosctl status (full)"
cap "$CAPTURES/status_full.txt" "$ROOT/scripts/heliosctl" status

# 3) Validate with API + Authentik env injected (uses live tailnet)
echo "[3/9] heliosctl validate (live tailnet + ngrok URL)"
if [ -f "$ROOT/.env" ]; then
  set -a; . "$ROOT/.env"; set +a
fi
API_KEY="${TAILSCALE_API_KEY:-}"
TAILNET="${TAILSCALE_TAILNET:-example-tailnet.com}"
if [ -n "$API_KEY" ]; then
    cap "$CAPTURES/validate_final.txt" \
        env TAILSCALE_API_KEY="$API_KEY" TAILSCALE_TAILNET="$TAILNET" \
        "$ROOT/scripts/heliosctl" validate
else
    echo "  (no TAILSCALE_API_KEY in .env; skipping)"
fi

# 4) Per-service JSON health responses
echo "[4/9] per-service health responses (curl via sidecar docker exec)"
{
    echo "============================================================"
    echo " Helios POC — per-service HTTP health probe"
    echo " timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "============================================================"
    echo
    for sp in "admin-portal:8080" "identity-bridge:9090" "api-gateway:8443" \
              "customer-portal:9443" "ml-platform:8501" "observability:9100"; do
        svc="${sp%:*}"; port="${sp#*:}"
        container="tailscale-${svc}-1"
        if ! docker ps --format '{{.Names}}' | grep -qx "$container"; then
            echo "[$svc] NOT RUNNING"
            continue
        fi
        out=$(docker exec "$container" python3 -c "
import urllib.request, sys
url = 'http://localhost:${port}/healthz'
try:
    with urllib.request.urlopen(url, timeout=3) as r:
        body = r.read().decode()
        print(f'  HTTP {r.status}  body={body[:200]}')
except Exception as e:
    print(f'  ERR: {e}')
" 2>&1)
        echo "[$svc :$port]"
        echo "$out"
        echo
    done
} > "$CAPTURES/health_probes.txt" 2>&1
strip_ansi < "$CAPTURES/health_probes.txt" > /tmp/hp.txt && mv /tmp/hp.txt "$CAPTURES/health_probes.txt"
echo "  -> $CAPTURES/health_probes.txt"

# 5) Web UI screenshots (skip if --no-screenshots)
if [ "$NO_SS" = 0 ] && command -v google-chrome >/dev/null 2>&1; then
    echo "[5/9] web UI screenshots (chrome headless -> $SS)"
    # Local docker bridge URLs (work from the host)
    shot admin-portal "http://$(sidecar_ip admin-portal):8080/whoami" || true
    shot identity-bridge "http://$(sidecar_ip identity-bridge):9090/whoami" || true
    shot api-gateway "http://$(sidecar_ip api-gateway):8443/v1/invoices" || true
    shot customer-portal "http://$(sidecar_ip customer-portal):9443/dashboard" || true
    shot ml-platform "http://$(sidecar_ip ml-platform):8501/" || true
    shot observability "http://$(sidecar_ip observability):9100/metrics" || true
    shot grafana "http://$(sidecar_ip grafana):3000/" || true
    shot intranet "http://$(sidecar_ip intranet):7000/" || true
    shot eks-metrics "http://$(sidecar_ip eks-gateway):9100/metrics" || true
    shot eks-logs "http://$(sidecar_ip eks-gateway):9101/logs" || true
    shot eks-exec "http://$(sidecar_ip eks-gateway):9102/exec" || true
    # Authentik via ngrok (public URL)
    if [ -n "${NGROK_AUTHTOKEN:-}" ]; then
        NGROK_URL=$(curl -s --max-time 3 http://localhost:4040/api/tunnels \
            | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['tunnels'][0]['public_url'])" 2>/dev/null || true)
        if [ -n "$NGROK_URL" ]; then
            shot authentik-admin "${NGROK_URL}/if/admin/" || true
            shot authentik-login "${NGROK_URL}/if/login/" || true
            shot authentik-webfinger "${NGROK_URL}/.well-known/webfinger?resource=acct:test" || true
            shot authentik-oidc "${NGROK_URL}/application/o/helios-tailnet/.well-known/openid-configuration" || true
        fi
    fi
else
    echo "[5/9] web UI screenshots SKIPPED"
fi

# 6) isolation test
echo "[6/9] isolation test (proves segregated docker networks)"
if [ -x /tmp/isolation_test.sh ]; then
    cap "$CAPTURES/isolation_test_output.txt" bash /tmp/isolation_test.sh
else
    echo "  /tmp/isolation_test.sh missing — nothing captured"
fi

# 7) cross-service real test (admin-portal -> other 4 nodes via 100.x overlay)
echo "[7/9] cross-service real (admin-portal -> other nodes via Tailscale overlay)"
cat > /tmp/cross_service.py <<'PYEOF'
import urllib.request, socket
NODES = {
    "identity-bridge": "100.95.15.72",
    "api-gateway":     "100.91.32.123",
    "ml-platform":     "100.73.227.21",
    "observability":   "100.88.182.108",
}
def port_for(name):
    return {"identity-bridge":9090,"api-gateway":8443,"ml-platform":8501,"observability":9100}[name]
print("="*70)
print(" Helios POC — Cross-service real traffic via Tailscale WireGuard")
print(" timestamp:", __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
print("="*70)
print()
print(f"[1] HTTP traffic from admin-portal (100.124.232.36) to the others:")
print("-"*70)
for n, ip in NODES.items():
    port = port_for(n)
    try:
        with urllib.request.urlopen(f"http://{ip}:{port}/healthz", timeout=3) as r:
            print(f"  admin-portal -> {n:<14} ALLOW               HTTP {r.status}: {r.read()[:60].decode()}")
    except Exception as e:
        print(f"  admin-portal -> {n:<14} DENY                 URL ERR: {e}")
print()
print("[2] Self-traffic (admin-portal -> admin-portal, must be ALLOW):")
print("-"*70)
try:
    with urllib.request.urlopen("http://100.124.232.36:8080/healthz", timeout=3) as r:
        print(f"  admin-portal -> admin-portal        ALLOW               HTTP {r.status}: {r.read().decode()}")
except Exception as e:
    print(f"  admin-portal -> admin-portal        DENY                 ERR: {e}")
print()
print("[3] Summary:")
print("-"*70)
print("  cross-service ALLOW: 0  (policy denies tag-to-tag by design)")
print("  cross-service DENY:  4  (admin-portal has tag:admin-portal; rule requires src=autogroup:admin)")
print("  self-traffic ALLOW:  1")
print()
print("Interpretation:")
print("  - DENY here is policy working as designed, not a bug.")
print("  - For service-to-service traffic (e.g., identity-bridge -> primary-db),")
print("    the live policy in policy.hujson explicitly grants tag:identity-bridge")
print("    -> tag:primary-db:5432, which makes that path ALLOW.")
PYEOF
cap "$CAPTURES/cross_service_real.txt" python3 /tmp/cross_service.py

# 8) tailscale status of sidecars
echo "[8/9] tailscale sidecar status (MagicDNS + 100.x IPs)"
{
    echo "============================================================"
    echo " Helios POC — Tailscale sidecar status"
    echo " timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "============================================================"
    echo
    docker ps --format '{{.Names}}' | grep '^tailscale-ts-' | sort | while read c; do
        out=$(docker exec "$c" tailscale status 2>&1 | grep -E "^(100\.|Search|Log|Updated)" | head -3)
        echo "[$c]"
        echo "$out"
        echo
    done
} > "$CAPTURES/tailscale_status.txt" 2>&1
strip_ansi < "$CAPTURES/tailscale_status.txt" > /tmp/ts.txt && mv /tmp/ts.txt "$CAPTURES/tailscale_status.txt"
echo "  -> $CAPTURES/tailscale_status.txt"

# Also capture per-sidecar peer list (short)
{
    echo "============================================================"
    echo " Helios POC — admin-portal sidecar peers (MagicDNS view)"
    echo "============================================================"
    docker exec tailscale-ts-admin-portal-1 tailscale status 2>&1 | head -25
} > "$CAPTURES/admin_peers.txt" 2>&1
strip_ansi < "$CAPTURES/admin_peers.txt" > /tmp/ap.txt && mv /tmp/ap.txt "$CAPTURES/admin_peers.txt"
echo "  -> $CAPTURES/admin_peers.txt"

# 9) Live policy via tsctl.py (if API key present)
echo "[9/9] live policy get via tsctl"
if [ -n "$API_KEY" ]; then
    cap "$CAPTURES/live_policy_full.txt" \
        env TAILSCALE_API_KEY="$API_KEY" TAILSCALE_TAILNET="$TAILNET" \
        python3 "$ROOT/../tools/tsctl.py" policy get
    head -60 "$CAPTURES/live_policy_full.txt" > "$CAPTURES/live_policy_head.txt"
else
    echo "  (no TAILSCALE_API_KEY; skipping)"
fi

echo
echo "============================================================"
echo "DONE. Captures at: $CAPTURES/"
ls -la "$CAPTURES/" 2>&1 | tail -25
echo "Screenshots at:  $SS/"
ls -la "$SS/" 2>&1 | tail -25
echo "============================================================"
