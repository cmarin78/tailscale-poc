output "secret_arn" {
  description = "ARN of the bundle secret"
  value       = aws_secretsmanager_secret.helios_poc.arn
}

output "secret_name" {
  description = "Name of the bundle secret (use this in your apps)"
  value       = aws_secretsmanager_secret.helios_poc.name
}

output "primary_db_secret_name" {
  value = aws_secretsmanager_secret.primary_db.name
}

output "warehouse_db_secret_name" {
  value = aws_secretsmanager_secret.warehouse_db.name
}

# Helpful for debugging
output "endpoint" {
  value = var.ministack_endpoint
}
