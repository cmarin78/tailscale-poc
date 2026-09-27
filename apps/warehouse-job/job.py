#!/usr/bin/env python3
"""Helios warehouse-job — ETL from primary-db to warehouse-db.

Runs once (or on schedule). Reads invoices from primary-db, writes aggregates
to warehouse-db. Only this job can talk to both DBs — by design.

Pattern: the job fetches DB credentials from Secrets Manager (MiniStack) at
runtime. In prod, secrets rotate every N days; the job picks up new creds
on the next run.
"""

import json
import os
import struct
import socket
import sys
import time

import boto3
import psycopg

SECRET_ID = os.environ.get("SECRETS_MANAGER_SECRET_ID", "helios/poc/secrets")


def _default_gateway_ip():
    """Same trick as identity-bridge — the sidecar has the real network."""
    with open("/proc/net/route") as f:
        for line in f.readlines()[1:]:
            fields = line.split()
            if fields[1] == "00000000" and int(fields[3], 16) & 2:
                return socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))
    return "127.0.0.1"


def _get_secret(key: str) -> dict:
    """Fetch a DB block from MiniStack (Secrets Manager sim)."""
    client = boto3.client(
        "secretsmanager",
        endpoint_url=os.environ.get(
            "MINISTACK_ENDPOINT", f"http://{_default_gateway_ip()}:4566"
        ),
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
    )
    raw = client.get_secret_value(SecretId=SECRET_ID)["SecretString"]
    return json.loads(raw)[key]


def _dsn(d: dict) -> str:
    return (
        f"host={d['host']} port={d['port']} dbname={d['dbname']} "
        f"user={d['username']} password={d['password']}"
    )


def run():
    primary = _get_secret("primary_db")
    warehouse = _get_secret("warehouse_db")

    print(f"[{time.strftime('%H:%M:%S')}] fetching from primary-db {primary['host']}:{primary['port']}")
    with psycopg.connect(_dsn(primary), connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, customer_id, amount_cents, status, created_at FROM helios.invoices"
            )
            rows = cur.fetchall()

    print(f"[{time.strftime('%H:%M:%S')}] fetched {len(rows)} invoices, writing aggregates to warehouse")

    # Aggregate by customer
    agg = {}
    for inv_id, cust_id, amount, status, created_at in rows:
        agg.setdefault(cust_id, {"total_cents": 0, "paid_cents": 0, "count": 0})
        agg[cust_id]["total_cents"] += amount
        agg[cust_id]["count"] += 1
        if status == "paid":
            agg[cust_id]["paid_cents"] += amount

    with psycopg.connect(_dsn(warehouse), connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS helios_dw.invoice_aggregates (
                    customer_id TEXT PRIMARY KEY,
                    total_cents BIGINT,
                    paid_cents BIGINT,
                    invoice_count INT,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            for cust_id, data in agg.items():
                cur.execute("""
                    INSERT INTO helios_dw.invoice_aggregates
                        (customer_id, total_cents, paid_cents, invoice_count, updated_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (customer_id) DO UPDATE SET
                        total_cents = EXCLUDED.total_cents,
                        paid_cents = EXCLUDED.paid_cents,
                        invoice_count = EXCLUDED.invoice_count,
                        updated_at = NOW()
                """, (cust_id, data["total_cents"], data["paid_cents"], data["count"]))
            conn.commit()

    print(f"[{time.strftime('%H:%M:%S')}] wrote {len(agg)} aggregates to warehouse-db")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
