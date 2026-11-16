# Generic IRSA role factory — called once per workload that needs AWS credentials
# (api, worker, loki, tempo) per docs/aws-architecture.md §4: "pods assume a scoped IAM
# role for S3/DynamoDB/SQS access... no static AWS keys anywhere in the system." The
# app code already supports this for free — app/config.py's S3 settings fall back to
# boto3's default credential chain (which picks up IRSA) whenever S3_ACCESS_KEY/
# S3_SECRET_KEY are left unset.

module "irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.44"

  role_name = var.role_name

  oidc_providers = {
    main = {
      provider_arn               = var.oidc_provider_arn
      namespace_service_accounts = ["${var.namespace}:${var.service_account_name}"]
    }
  }

  # The upstream module wants role_policy_arns keyed by an arbitrary map key, not a
  # plain list — the ARN itself is a fine key since it's already unique.
  role_policy_arns = { for arn in var.attach_policy_arns : arn => arn }

  tags = var.tags
}

# Inline policy for anything not covered by an AWS-managed policy ARN (e.g. "this role
# may only touch these specific S3/DynamoDB/SQS resources", which no managed policy
# expresses).
resource "aws_iam_role_policy" "inline" {
  count  = var.create_inline_policy ? 1 : 0
  name   = "${var.role_name}-inline"
  role   = module.irsa.iam_role_name
  policy = var.inline_policy_json
}
