"""
Helios POC — shared admin CLI utilities (Tailscale SaaS and Headscale).

This module provides the common utilities:
  - Config loading from .env
  - Colorized logging
  - Table output for lists
  - Simple HTTP client

Usage:
    from lib.common import load_config, cprint, table
"""
import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from datetime import datetime


# ---------- ANSI colors ----------
class C:
    R = "\033[91m"  # red
    G = "\033[92m"  # green
    Y = "\033[93m"  # yellow
    B = "\033[94m"  # blue
    M = "\033[95m"  # magenta
    CY = "\033[96m"  # cyan
    W = "\033[97m"  # white
    DIM = "\033[2m"
    BOLD = "\033[1m"
    END = "\033[0m"


def cprint(msg: str, color: str = "") -> None:
    if color and sys.stdout.isatty():
        print(f"{color}{msg}{C.END}")
    else:
        print(msg)


def info(msg: str) -> None:
    cprint(f"  {msg}", C.DIM)


def ok(msg: str) -> None:
    cprint(f"✓ {msg}", C.G)


def warn(msg: str) -> None:
    cprint(f"⚠ {msg}", C.Y)


def err(msg: str) -> None:
    cprint(f"✗ {msg}", C.R)


def header(msg: str) -> None:
    cprint(msg, C.BOLD + C.CY)


def subheader(msg: str) -> None:
    cprint(msg, C.BOLD)


# ---------- Config loading ----------
def load_config(env_file: str | None = None) -> dict:
    """Load config from .env (search upward to the script's directory)."""
    config = {}
    if env_file is None:
        # Look for .env in cwd or parents
        candidates = [Path.cwd() / ".env"]
        for p in [Path.cwd(), *Path.cwd().parents]:
            if (p / ".env").exists():
                candidates.insert(0, p / ".env")
                break
        env_file = candidates[0]

    env_path = Path(env_file)
    if env_path.exists():
        info(f"loading config from {env_path}")
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                # Don't overwrite shell env vars
                config[k] = os.environ.get(k, v)
    else:
        warn(f"no .env found at {env_path}; relying on shell env")

    # Fill in from actual shell env
    for k in list(os.environ):
        config[k] = os.environ[k]

    return config


# ---------- Output formatting ----------
def table(headers: list[str], rows: list[list[str]], col_colors: list[str] | None = None) -> None:
    """Render a simple table. col_colors is optional for coloring specific columns."""
    if not rows:
        info("(empty)")
        return

    # Compute column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    # Header
    header_line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    cprint(header_line, C.BOLD)
    cprint("  ".join("-" * w for w in widths), C.DIM)

    # Rows
    for row in rows:
        formatted_cells = []
        for i, (cell, w) in enumerate(zip(row, widths)):
            s = str(cell).ljust(w)
            if col_colors and i < len(col_colors) and col_colors[i] and sys.stdout.isatty():
                s = f"{col_colors[i]}{s}{C.END}"
            formatted_cells.append(s)
        print("  ".join(formatted_cells))


def fmt_age(iso_or_ts) -> str:
    """Format an ISO or epoch timestamp as a human age (e.g., '5m ago')."""
    if not iso_or_ts:
        return "-"
    try:
        if isinstance(iso_or_ts, str):
            ts = datetime.fromisoformat(iso_or_ts.replace("Z", "+00:00")).timestamp()
        else:
            ts = float(iso_or_ts)
        delta = datetime.now().timestamp() - ts
        if delta < 60:
            return f"{int(delta)}s ago"
        if delta < 3600:
            return f"{int(delta/60)}m ago"
        if delta < 86400:
            return f"{int(delta/3600)}h ago"
        return f"{int(delta/86400)}d ago"
    except (ValueError, TypeError):
        return str(iso_or_ts)


def fmt_bool(b) -> str:
    if b is True:
        return f"{C.G}true{C.END}" if sys.stdout.isatty() else "true"
    if b is False:
        return f"{C.R}false{C.END}" if sys.stdout.isatty() else "false"
    return "-"


def fmt_expiry(expires) -> str:
    """Format an expiry timestamp."""
    if not expires or expires == "Never" or expires == "0001-01-01T00:00:00Z":
        return "never"
    return fmt_age(expires) if expires < datetime.now().isoformat() + "Z" else f"expires {fmt_age(expires)}"


# ---------- HTTP client ----------
class HTTPError(Exception):
    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body[:200]}")


def http_request(
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    body: bytes | None = None,
    timeout: int = 30,
) -> tuple[int, bytes]:
    """Simple wrapper around urllib.request."""
    req = urllib.request.Request(url, data=body, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def http_json(method, url, *, headers=None, json_body=None, timeout=30):
    """HTTP request that serializes/deserializes JSON."""
    body = None
    h = dict(headers or {})
    if json_body is not None:
        body = json.dumps(json_body).encode()
        h.setdefault("Content-Type", "application/json")
    h.setdefault("Accept", "application/json")
    status, resp = http_request(method, url, headers=h, body=body, timeout=timeout)
    if status >= 400:
        raise HTTPError(status, resp.decode(errors="replace"))
    if not resp:
        return None
    return json.loads(resp.decode())
