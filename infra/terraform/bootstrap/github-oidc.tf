# GitHub Actions -> AWS via OIDC federation: no static access keys in CI.
#
# Lives in bootstrap (not in an environment) for the same chicken-and-egg reason as the
# state bucket: terraform.yaml needs these roles to exist before it can run at all, so a
# human applies them once per account.
#
# Three roles, split by blast radius. The `sub` claim GitHub puts in the token depends
# on how the job is triggered, and that is what each trust policy pins:
#
#   role          used by                              trusted `sub`              permissions
#   ------------  -----------------------------------  -------------------------  ---------------------
#   ci            cd.yaml, cd-web.yaml, promote.yaml   main branch, environments  push/pull the 2 ECR repos
#   tf-plan       terraform.yaml `plan` (PRs)          pull_request               read-only + state lock
#   tf-apply      terraform.yaml `apply` (push main)   environments               AdministratorAccess
#
# tf-apply is only assumable from jobs that declare `environment: <name>`, so the GitHub
# Environment protection rules (required reviewers on prod) gate the admin role. A PR
# can never reach it: PR jobs get `sub = repo:<org>/<repo>:pull_request`.

data "aws_caller_identity" "current" {}

locals {
  github_oidc_url = "token.actions.githubusercontent.com"

  github_oidc_provider_arn = (
    var.create_github_oidc_provider
    ? aws_iam_openid_connect_provider.github[0].arn
    : "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/${local.github_oidc_url}"
  )

  github_sub_prefix       = "repo:${var.github_repository}"
  github_sub_main         = "${local.github_sub_prefix}:ref:refs/heads/main"
  github_sub_pull_request = "${local.github_sub_prefix}:pull_request"
  github_sub_environments = [
    for env in var.github_environments : "${local.github_sub_prefix}:environment:${env}"
  ]

  ecr_repository_arns = [
    for name in var.ecr_repository_names :
    "arn:aws:ecr:${var.region}:${data.aws_caller_identity.current.account_id}:repository/${name}"
  ]
}

# One provider per AWS account. If the account already has one for GitHub (another
# project created it), set create_github_oidc_provider = false to reuse it.
resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_oidc_provider ? 1 : 0

  url            = "https://${local.github_oidc_url}"
  client_id_list = ["sts.amazonaws.com"]

  # AWS no longer validates these for GitHub's IdP, but older 5.x providers still
  # require the argument.
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]
}

# --- Trust policies ---

data "aws_iam_policy_document" "github_trust" {
  for_each = {
    ci       = concat([local.github_sub_main], local.github_sub_environments)
    tf-plan  = [local.github_sub_pull_request]
    tf-apply = local.github_sub_environments
  }

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.github_oidc_url}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.github_oidc_url}:sub"
      values   = each.value
    }
  }
}

# --- ci: build + push images, read them back for promotion ---

resource "aws_iam_role" "github_ci" {
  name               = "bceao-rag-github-ci"
  assume_role_policy = data.aws_iam_policy_document.github_trust["ci"].json
}

data "aws_iam_policy_document" "github_ci" {
  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"] # this action does not support resource-level scoping
  }

  statement {
    sid = "EcrPushPull"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:DescribeImages",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = local.ecr_repository_arns
  }
}

resource "aws_iam_role_policy" "github_ci" {
  name   = "ecr-push"
  role   = aws_iam_role.github_ci.id
  policy = data.aws_iam_policy_document.github_ci.json
}

# --- tf-plan: read-only, plus just enough to take the state lock ---

resource "aws_iam_role" "github_tf_plan" {
  name               = "bceao-rag-github-tf-plan"
  assume_role_policy = data.aws_iam_policy_document.github_trust["tf-plan"].json
}

resource "aws_iam_role_policy_attachment" "github_tf_plan_readonly" {
  role       = aws_iam_role.github_tf_plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

data "aws_iam_policy_document" "github_tf_plan_state" {
  statement {
    sid       = "StateLock"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem"]
    resources = [aws_dynamodb_table.tf_lock.arn]
  }
}

resource "aws_iam_role_policy" "github_tf_plan_state" {
  name   = "tfstate-lock"
  role   = aws_iam_role.github_tf_plan.id
  policy = data.aws_iam_policy_document.github_tf_plan_state.json
}

# --- tf-apply: creates VPC/EKS/IAM/..., so effectively admin; gated by environments ---

resource "aws_iam_role" "github_tf_apply" {
  name               = "bceao-rag-github-tf-apply"
  assume_role_policy = data.aws_iam_policy_document.github_trust["tf-apply"].json
}

resource "aws_iam_role_policy_attachment" "github_tf_apply_admin" {
  role       = aws_iam_role.github_tf_apply.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}
