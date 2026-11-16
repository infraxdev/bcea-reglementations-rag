# Secrets Manager entries for the values app/config.py reads as env vars but that must
# never live in a ConfigMap or tfvars file (docs/aws-architecture.md §4). Terraform only
# creates the *secret container* here — the actual value is populated out-of-band
# (console, `aws secretsmanager put-secret-value`, or a separate restricted pipeline)
# so it never appears in Terraform state or a PR diff. The External Secrets Operator
# then syncs these into a native k8s Secret that the API/worker Deployments mount as
# the exact env var names app/config.py already expects.

resource "aws_secretsmanager_secret" "this" {
  for_each = toset(var.secret_names)

  name                    = "bceao-rag/${var.environment}/${each.value}"
  recovery_window_in_days = var.recovery_window_days

  tags = var.tags
}

# Placeholder version so the secret isn't left with zero versions (which breaks the
# External Secrets Operator's read until a human fills in the real value). Rotate this
# out of band immediately after `terraform apply`.
resource "aws_secretsmanager_secret_version" "placeholder" {
  for_each = aws_secretsmanager_secret.this

  secret_id     = each.value.id
  secret_string = "REPLACE_ME"

  lifecycle {
    ignore_changes = [secret_string]
  }
}
