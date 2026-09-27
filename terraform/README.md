# Helios POC — Terraform

This module seeds the secrets that `identity-bridge` and `warehouse-job` consume at runtime. It replicates the "secrets from client (Terraform) → vault → application" pattern that would be used in production with real AWS Secrets Manager.

## Usage

```bash
cd terraform
terraform init
cp terraform.tfvars.example terraform.tfvars
$EDITOR terraform.tfvars  # paste the Tailscale API key
terraform apply -auto-approve
```

## Expected output

```
secret_arn    = "arn:aws:secretsmanager:us-east-1:000000000000:secret:helios/poc/secrets"
secret_name   = "helios/poc/secrets"
```

## Secret structure

`helios/poc/secrets` contains a JSON bundle:

```json
{
  "primary_db":   { "host": "primary-db",   "port": 5432, "dbname": "helios",            "username": "helios", "password": "..." },
  "warehouse_db": { "host": "warehouse-db", "port": 5432, "dbname": "helios_warehouse",  "username": "helios", "password": "..." },
  "tailnet":      { "api_key": "tskey-...",  "tailnet": "githubusercontent-com/..." }
}
```

Each app consumes only the sub-block it needs:
- `identity-bridge` → `primary_db` (secret key configurable via `PRIMARY_DB_SECRET_KEY`)
- `warehouse-job` → `primary_db` + `warehouse_db`
- `tailnet-bootstrap.sh` (not included in this POC, see roadmap) → `tailnet.api_key`

## In prod

1. Replace `provider "aws"` with one pointing to real AWS (without `endpoints { secretsmanager = ... }`).
2. Move the secrets out of `terraform.tfstate` (use data sources or AWS Secrets Manager as source of truth).
3. Add automatic rotation with `aws_secretsmanager_secret_rotation`.
4. Version this module in git and apply it with Atlantis / Spacelift / Terraform Cloud to avoid manual `terraform apply`.
