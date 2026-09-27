# Helios Policy — variants

There are two versions of the policy:

| File | Google groups | Where it applies |
|---|---|---|
| `policy.hujson` | ✅ yes (group:platform-eng@helios.example, etc.) | Production with Google Workspace SSO + SCIM |
| `policy-poc-no-groups.hujson` | ❌ no (only `autogroup:admin` + tags) | POC without SSO, any plan |

## Which to use

- **Local POC without SSO** (this case): `policy-poc-no-groups.hujson`
  - Works with any Tailscale plan (even free)
  - Personas (Diego, Rafa, etc.) are user-owned nodes with a simple auth key
  - Services are tagged nodes
  - The policy evaluates by tag and by `autogroup:admin`

- **Production with Google Workspace** (future): `policy.hujson`
  - Requires Tailscale Business (or trial)
  - Configure SSO with Google Workspace
  - Enable SCIM for automatic group sync
  - Personas log in with their Google account; their groups flow via OIDC claims
  - The policy evaluates by `group:role@helios.example`

## Why the policy with groups fails in this tailnet

When I tried to apply `policy.hujson` directly, the Tailscale API returned:

```
HTTP 400: groups not found: ["group:platform-eng@helios.example" ...]
```

That's because Tailscale validates that each `group:X` referenced actually exists in the tailnet. Without SSO/SCIM, the groups don't exist. That's why the POC version replaces them with `autogroup:admin` (always valid).

## Differences between the two policies

| Section | policy.hujson | policy-poc-no-groups.hujson |
|---|---|---|
| `tagOwners` | tags with groups + autogroup:admin | tags with only autogroup:admin |
| `acls` src | mix groups + tags + autogroup | only tags + autogroup:admin |
| `acls` dst | tags:port | tags:port (same) |
| `ssh` | ssh by group | ssh by autogroup:admin |
| `grants` | yes (for auditors) | no |
| `tests` | yes (33 embedded cases) | no (API doesn't support it) |
| `autoApprovers` | yes | no (API doesn't support it) |
| `postures` | placeholder | no |

## How to promote the POC to production

```bash
# 1. Configure SSO with Google Workspace in admin console
# 2. Enable SCIM (syncs users and groups)
# 3. Wait 5-10 min for the first Tailscale poll to bring in the groups
# 4. Verify in admin console that the 6 Helios groups appear
# 5. Apply the full policy:
python3 tools/tsctl.py policy set acl/policy.hujson

# 6. If it still says "groups not found", the groups haven't arrived via SCIM yet
#    → wait and retry
```

## How to verify the effective policy

```bash
python3 tools/tsctl.py policy get  # shows the effective JSON
python3 tools/tsctl.py policy get --format json  # explicit
```

## Notes about fields not supported by the API

- `tests`: the API accepts it in the admin console but not in POST. Workaround: validate tests via `scripts/verify.sh` (E2E).
- `autoApprovers.routes`: requires Manager plan.
- `postures` and `devicePosture`: require Business + Manager.
- `grants.app` with custom capability: the name must have the format `domain/path` (e.g. `helios/observability.read` not just `observability.read`).

If the API rejects the `set` with a 400, copy the error body (`grep -A 5 "HTTP 400"` in the output) and adjust.
