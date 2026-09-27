"""
tsctl — admin CLI for Tailscale SaaS (Tailscale Inc. control plane)

Usage:
    tsctl.py authkey create --tag tag:admin-portal [--reusable] [--ephemeral] [--days 30]
    tsctl.py authkey list
    tsctl.py device list [--tag tag:foo] [--user user@email.com]
    tsctl.py device delete <device-id>
    tsctl.py device expire <device-id>
    tsctl.py policy get
    tsctl.py policy set <file.hujson>
    tsctl.py user list
    tsctl.py dns list
    tsctl.py webhooks list
    tsctl.py login-info  # check API connection

Config (in .env or env vars):
    TAILSCALE_API_KEY=tskey-api-...
    TAILSCALE_TAILNET=githubusercontent-com/foo  # or the tailnet name

API ref: https://tailscale.com/kb/1101/api
"""

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

# Allow imports from sibling lib/
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import (
    C, cprint, info, ok, warn, err, header, subheader,
    table, fmt_age, fmt_bool, fmt_expiry, http_json, HTTPError,
    load_config,
)

API_BASE = "https://api.tailscale.com/api/v2"


class TailscaleClient:
    def __init__(self, api_key: str, tailnet: str):
        if not api_key:
            err("TAILSCALE_API_KEY not set (https://login.tailscale.com/admin/settings/keys)")
            sys.exit(1)
        if not tailnet:
            err("TAILSCALE_TAILNET not set (e.g. 'githubusercontent-com/foo' or '-' for default)")
            sys.exit(1)
        self.api_key = api_key
        self.tailnet = tailnet
        self.headers = {
            "Authorization": f"Bearer {api_key}",
        }

    def _path(self, path: str) -> str:
        return f"{API_BASE}/tailnet/{self.tailnet}{path}"

    # ----- Auth keys -----
    def authkey_create(
        self,
        *,
        reusable: bool = True,
        ephemeral: bool = False,
        preauthorized: bool = False,
        tags: list[str] | None = None,
        expiry_seconds: int | None = 86400,  # 1 day default
        description: str = "",
    ) -> dict:
        body = {
            "capabilities": {
                "devices": {
                    "create": {
                        "reusable": reusable,
                        "ephemeral": ephemeral,
                        "preauthorized": preauthorized,
                        "tags": tags or [],
                        "expires": expiry_seconds,
                    }
                }
            }
        }
        if description:
            body["description"] = description
        return http_json("POST", self._path("/keys"), headers=self.headers, json_body=body)

    def authkey_list(self) -> list[dict]:
        # Tailscale API doesn't have a list endpoint; we list devices with their
        # auth info instead. For audit, this is what we have.
        # However, you can see auth keys in admin console.
        warn("Tailscale API doesn't expose a 'list auth keys' endpoint")
        warn("Use `tsctl device list --key-expiry <N>` to audit active devices")
        return []

    # ----- Devices -----
    def device_list(self, *, tag: str | None = None) -> list[dict]:
        params = []
        if tag:
            # Tailscale filters: fields=tag,tag:X (use query params)
            params.append(f"fields=tag")
            # We'll filter client-side because tag filter syntax varies
        url = self._path("/devices") + ("?" + "&".join(params) if params else "")
        data = http_json("GET", url, headers=self.headers)
        devices = data.get("devices", [])
        if tag:
            devices = [d for d in devices if tag in (d.get("tags") or [])]
        return devices

    def device_delete(self, device_id: str) -> None:
        http_json("DELETE", f"{API_BASE}/device/{device_id}", headers=self.headers)

    def device_expire(self, device_id: str, expiry_seconds: int = 0) -> None:
        """Immediately expire (expiry_seconds=0)."""
        body = {"expirySeconds": expiry_seconds}
        http_json("POST", f"{API_BASE}/device/{device_id}/expire",
                  headers=self.headers, json_body=body)

    def device_set_tags(self, device_id: str, tags: list[str]) -> None:
        body = {"tags": tags}
        http_json("POST", f"{API_BASE}/device/{device_id}/tags",
                  headers=self.headers, json_body=body)

    # ----- Policy -----
    def policy_get(self) -> dict:
        # Returns HuJSON as text + parsed
        _, body = http_json.__wrapped__ if hasattr(http_json, "__wrapped__") else (None, None)
        # http_json returns parsed JSON; for policy we need raw HuJSON
        import urllib.request
        req = urllib.request.Request(
            self._path("/acl"),
            headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())

    def policy_set(self, hujson_path: str) -> None:
        body = Path(hujson_path).read_text()
        req = urllib.request.Request(
            self._path("/acl"),
            data=body.encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/hujson",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            ok(f"policy applied ({resp.status})")

    # ----- Users -----
    def user_list(self) -> list[dict]:
        # Returns {"users": [...]} — extract the list
        result = http_json("GET", self._path("/users"), headers=self.headers)
        if isinstance(result, dict) and "users" in result:
            return result["users"]
        return result if isinstance(result, list) else []

    # ----- DNS -----
    def dns_list(self) -> list[dict]:
        # Returns {"dns": [...]} or {"nameservers": [...]} depending on endpoint
        result = http_json("GET", self._path("/dns/nameservers"), headers=self.headers)
        if isinstance(result, dict):
            for key in ("nameservers", "dns", "results"):
                if key in result:
                    return result[key] or []
        return result if isinstance(result, list) else []

    # ----- Webhooks -----
    def webhooks_list(self) -> list[dict]:
        # Returns {"webhooks": [...]} or {"webhooks": null}
        result = http_json("GET", self._path("/webhooks"), headers=self.headers)
        if isinstance(result, dict) and "webhooks" in result:
            return result["webhooks"] or []
        return result if isinstance(result, list) else []


# ---------- Commands ----------

def cmd_login_info(client: TailscaleClient, args):
    """Verify API connection and show tailnet info."""
    header("Tailscale SaaS — connection check")
    print(f"  API base:    {API_BASE}")
    print(f"  Tailnet:     {client.tailnet}")
    print(f"  API key:     {client.api_key[:16]}...")

    try:
        users = client.user_list()
        # API can return list of strings (user IDs) or list of dicts
        if isinstance(users, list) and users and isinstance(users[0], str):
            ok(f"connected — {len(users)} user(s)")
            subheader("Users (IDs):")
            for u in users:
                print(f"  - {u}")
        else:
            ok(f"connected — {len(users)} user(s)")
            if users:
                subheader("Users:")
                rows = [[u.get("id"), u.get("displayName"), u.get("loginName"), u.get("role")]
                        for u in users]
                table(["ID", "Name", "Login", "Role"], rows)
    except HTTPError as e:
        err(f"connection failed: {e}")
        sys.exit(1)


def cmd_authkey_create(client: TailscaleClient, args):
    header("Create auth key")
    tags = []
    if args.tag:
        tags = [t.strip() for t in args.tag.split(",") if t.strip()]
    elif args.tags:
        tags = args.tags

    expiry_seconds = None
    if args.days:
        expiry_seconds = args.days * 86400
    elif args.hours:
        expiry_seconds = args.hours * 3600

    desc = args.description or f"created by tsctl ({','.join(tags) if tags else 'no-tag'})"

    info(f"tags:         {tags or '(none — user-owned)'}")
    info(f"reusable:     {args.reusable}")
    info(f"ephemeral:    {args.ephemeral}")
    info(f"preauthorized:{args.preauthorized}")
    info(f"expires in:   {expiry_seconds}s" if expiry_seconds else "expires in: never")

    resp = client.authkey_create(
        reusable=args.reusable,
        ephemeral=args.ephemeral,
        preauthorized=args.preauthorized,
        tags=tags,
        expiry_seconds=expiry_seconds,
        description=desc,
    )

    key = resp.get("key", "")
    key_id = resp.get("id", "")
    ok(f"created key {key_id}")
    print()
    cprint(f"  {key}", C.BOLD + C.G)
    print()
    info("paste this in your .env as TS_AUTHKEY_<TAG>")
    info("(key is shown once; store it now)")


def cmd_authkey_list(client: TailscaleClient, args):
    header("Auth keys")
    info("Tailscale API doesn't expose a 'list keys' endpoint")
    info("Showing active devices with auth key expiry instead:")
    print()
    cmd_device_list(client, argparse.Namespace(tag=None, show_key_age=True))


def cmd_device_list(client: TailscaleClient, args):
    header("Devices")
    devices = client.device_list(tag=args.tag if hasattr(args, "tag") else None)
    if not devices:
        info("(no devices)")
        return

    rows = []
    colors = []
    for d in devices:
        is_online = d.get("online", False)
        online_str = "online" if is_online else "offline"
        online_color = C.G if is_online else C.DIM

        last_seen = d.get("lastSeen")
        expires = d.get("expires")

        rows.append([
            d.get("id", "")[:12],
            d.get("hostname", "?"),
            d.get("name", "-")[:30],
            d.get("user", "-"),
            ", ".join(d.get("tags") or []) or "(user-owned)",
            online_str,
            fmt_age(last_seen),
            fmt_expiry(expires),
        ])
        colors.append([None, None, None, None, None, online_color, None, None])

    table(["ID", "Hostname", "Name", "Owner", "Tags", "Status", "Last seen", "Expires"], rows, colors)

    print()
    info(f"total: {len(devices)} devices")


def cmd_device_delete(client: TailscaleClient, args):
    if not args.yes:
        warn(f"about to delete device {args.device_id}")
        if input("  confirm? [y/N] ").strip().lower() != "y":
            info("cancelled")
            return
    client.device_delete(args.device_id)
    ok(f"deleted {args.device_id}")


def cmd_device_expire(client: TailscaleClient, args):
    client.device_expire(args.device_id, expiry_seconds=0)
    ok(f"expired {args.device_id} (next poll: ~30s)")


def cmd_device_set_tags(client: TailscaleClient, args):
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    client.device_set_tags(args.device_id, tags)
    ok(f"set tags on {args.device_id}: {tags}")


def cmd_policy_get(client: TailscaleClient, args):
    header("Current ACL policy (HuJSON)")
    policy = client.policy_get()
    if args.format == "json":
        print(json.dumps(policy, indent=2))
    else:
        # Print as HuJSON-ish: dump with JSON, Tailscale accepts JSON too
        print(json.dumps(policy, indent=2))


def cmd_policy_set(client: TailscaleClient, args):
    header(f"Apply policy from {args.file}")
    if not Path(args.file).exists():
        err(f"file not found: {args.file}")
        sys.exit(1)
    client.policy_set(args.file)
    ok("policy applied — new effective in ~10s for connected clients")


def cmd_user_list(client: TailscaleClient, args):
    header("Users")
    users = client.user_list()
    rows = [[u.get("id"), u.get("displayName"), u.get("loginName"), u.get("role")]
            for u in users]
    table(["ID", "Name", "Login", "Role"], rows)
    print()
    info(f"total: {len(users)} user(s)")


def cmd_dns_list(client: TailscaleClient, args):
    header("DNS nameservers")
    nameservers = client.dns_list()
    if not nameservers:
        info("(no custom nameservers — using defaults)")
        return
    if isinstance(nameservers, list) and nameservers and isinstance(nameservers[0], str):
        info("(returned as list of IPs/FQDNs)")
        for ns in nameservers:
            print(f"  - {ns}")
    else:
        rows = [[ns.get("id"), ns.get("name"), ns.get("type")]
                for ns in nameservers]
        table(["ID", "Name", "Type"], rows)


def cmd_webhooks_list(client: TailscaleClient, args):
    header("Webhooks")
    webhooks = client.webhooks_list()
    # API can return list of strings or list of dicts
    if isinstance(webhooks, list) and webhooks and isinstance(webhooks[0], str):
        info("(webhooks returned as list of IDs, detail endpoint needed for full info)")
        for w in webhooks:
            print(f"  - {w}")
    elif isinstance(webhooks, list):
        rows = [[w.get("id"), w.get("url"), w.get("provider")]
                for w in webhooks]
        table(["ID", "URL", "Provider"], rows)
    else:
        info(f"unexpected response type: {type(webhooks).__name__}")
        print(webhooks)


# ---------- Main ----------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tsctl",
        description="admin CLI for Tailscale SaaS (https://api.tailscale.com/api/v2)",
    )
    parser.add_argument("--tailnet", help="Tailnet name (override .env)")
    parser.add_argument("--api-key", help="API key (override .env)")

    sub = parser.add_subparsers(dest="command", required=True)

    # login-info
    sub.add_parser("login-info", help="check API connection").set_defaults(func=cmd_login_info)

    # authkey
    p_authkey = sub.add_parser("authkey", help="manage auth keys")
    authkey_sub = p_authkey.add_subparsers(dest="authkey_cmd", required=True)
    p_akc = authkey_sub.add_parser("create", help="create new auth key")
    p_akc.add_argument("--tag", help="comma-separated tags (e.g. 'tag:admin-portal')")
    p_akc.add_argument("--tags", nargs="*", help="tags as multiple args")
    p_akc.add_argument("--reusable", action="store_true", default=True,
                       help="key can be used multiple times (default: true)")
    p_akc.add_argument("--single-use", dest="reusable", action="store_false",
                       help="key can only be used once")
    p_akc.add_argument("--ephemeral", action="store_true",
                       help="device will be removed when it goes offline")
    p_akc.add_argument("--preauthorized", action="store_true",
                       help="skip admin approval when device uses this key")
    p_akc.add_argument("--days", type=int, help="expiry in days (default: 1)")
    p_akc.add_argument("--hours", type=int, help="expiry in hours")
    p_akc.add_argument("--description", help="description for the key")
    p_akc.set_defaults(func=cmd_authkey_create)

    authkey_sub.add_parser("list").set_defaults(func=cmd_authkey_list)

    # device
    p_dev = sub.add_parser("device", help="manage devices")
    dev_sub = p_dev.add_subparsers(dest="dev_cmd", required=True)
    p_dl = dev_sub.add_parser("list", help="list devices")
    p_dl.add_argument("--tag", help="filter by tag")
    p_dl.set_defaults(func=cmd_device_list)

    p_dd = dev_sub.add_parser("delete", help="delete device")
    p_dd.add_argument("device_id", help="device ID to delete")
    p_dd.add_argument("--yes", "-y", action="store_true", help="skip confirmation")
    p_dd.set_defaults(func=cmd_device_delete)

    p_de = dev_sub.add_parser("expire", help="expire device immediately")
    p_de.add_argument("device_id", help="device ID to expire")
    p_de.set_defaults(func=cmd_device_expire)

    p_dt = dev_sub.add_parser("set-tags", help="set device tags")
    p_dt.add_argument("device_id", help="device ID")
    p_dt.add_argument("tags", help="comma-separated tags (e.g. 'tag:eng,tag:prod')")
    p_dt.set_defaults(func=cmd_device_set_tags)

    # policy
    p_pol = sub.add_parser("policy", help="manage ACL policy")
    pol_sub = p_pol.add_subparsers(dest="pol_cmd", required=True)
    p_pg = pol_sub.add_parser("get", help="get current policy")
    p_pg.add_argument("--format", choices=["json", "hujson"], default="json")
    p_pg.set_defaults(func=cmd_policy_get)
    p_ps = pol_sub.add_parser("set", help="apply policy from HuJSON file")
    p_ps.add_argument("file", help="path to .hujson file")
    p_ps.set_defaults(func=cmd_policy_set)

    # user
    p_user = sub.add_parser("user", help="manage users")
    p_user_sub = p_user.add_subparsers(dest="user_cmd", required=True)
    p_user_sub.add_parser("list").set_defaults(func=cmd_user_list)

    # dns
    p_dns = sub.add_parser("dns", help="manage DNS")
    p_dns_sub = p_dns.add_subparsers(dest="dns_cmd", required=True)
    p_dns_sub.add_parser("list").set_defaults(func=cmd_dns_list)

    # webhooks
    p_wh = sub.add_parser("webhooks", help="manage webhooks")
    p_wh_sub = p_wh.add_subparsers(dest="wh_cmd", required=True)
    p_wh_sub.add_parser("list").set_defaults(func=cmd_webhooks_list)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Resolve client
    config = load_config()
    api_key = args.api_key or config.get("TAILSCALE_API_KEY", "")
    tailnet = args.tailnet or config.get("TAILSCALE_TAILNET", "-")
    client = TailscaleClient(api_key, tailnet)

    # Dispatch
    if hasattr(args, "func"):
        args.func(client, args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
