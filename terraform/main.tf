# Helios POC — Terraform siembrra secretos en MiniStack (sim. Secrets Manager)
# ===========================================================================
# Este módulo reemplaza lo que sería un módulo Terraform real apuntando a
# AWS Secrets Manager en producción. La única diferencia es el endpoint
# del provider; el resto de la lógica es idéntica.
#
# Uso:
#   1. cd terraform
#   2. terraform init
#   3. terraform apply -auto-approve
#   4. terraform output
#
# Lo que crea:
#   - Secret "helios/poc/secrets" con:
#     - primary_db:    {host, port, dbname, username, password}
#     - warehouse_db:  {host, port, dbname, username, password}
#     - tailnet:       {api_key}  # para generar authkeys programáticamente
# ===========================================================================

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region                      = var.aws_region
  access_key                  = "test"
  secret_key                  = "test"
  s3_use_path_style           = true
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    secretsmanager = var.ministack_endpoint
    sts            = var.ministack_endpoint
  }
}

# ---------------------------------------------------------------------------
# Secrets bundle
# ---------------------------------------------------------------------------

locals {
  secrets = {
    primary_db = {
      host     = "primary-db"
      port     = 5432
      dbname   = "helios"
      username = "helios"
      password = var.primary_db_password
    }
    warehouse_db = {
      host     = "warehouse-db"
      port     = 5432
      dbname   = "helios_warehouse"
      username = "helios"
      password = var.warehouse_db_password
    }
    tailnet = {
      api_key  = var.tailscale_api_key
      tailnet  = var.tailscale_tailnet
    }
  }
}

resource "aws_secretsmanager_secret" "helios_poc" {
  name        = "helios/poc/secrets"
  description = "Helios POC — DB credentials + tailnet API key"
}

resource "aws_secretsmanager_secret_version" "helios_poc" {
  secret_id = aws_secretsmanager_secret.helios_poc.id
  secret_string = jsonencode(local.secrets)
}

# ---------------------------------------------------------------------------
# Per-secret versions (granular rotation if MiniStack supports it)
# ---------------------------------------------------------------------------

resource "aws_secretsmanager_secret" "primary_db" {
  name        = "helios/poc/primary-db"
  description = "Primary DB creds — rotated independently of the bundle"
}

resource "aws_secretsmanager_secret_version" "primary_db" {
  secret_id     = aws_secretsmanager_secret.primary_db.id
  secret_string = jsonencode(local.secrets.primary_db)
}

resource "aws_secretsmanager_secret" "warehouse_db" {
  name        = "helios/poc/warehouse-db"
  description = "Warehouse DB creds"
}

resource "aws_secretsmanager_secret_version" "warehouse_db" {
  secret_id     = aws_secretsmanager_secret.warehouse_db.id
  secret_string = jsonencode(local.secrets.warehouse_db)
}
