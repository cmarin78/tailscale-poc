variable "aws_region" {
  type        = string
  description = "AWS region (for the provider config — values are mocked in MiniStack)"
  default     = "us-east-1"
}

variable "ministack_endpoint" {
  type        = string
  description = "MiniStack endpoint URL (Secrets Manager sim)"
  default     = "http://localhost:4566"
}

variable "primary_db_password" {
  type        = string
  description = "Primary DB password to seed in Secrets Manager"
  sensitive   = true
  default     = "helios-primary-poc-2026"
}

variable "warehouse_db_password" {
  type        = string
  description = "Warehouse DB password to seed in Secrets Manager"
  sensitive   = true
  default     = "helios-warehouse-poc-2026"
}

variable "tailscale_api_key" {
  type        = string
  description = "Tailscale API key for programmatic authkey generation"
  sensitive   = true
  default     = ""
}

variable "tailscale_tailnet" {
  type        = string
  description = "Tailnet identifier (e.g. githubusercontent-com/foo)"
  default     = ""
}
