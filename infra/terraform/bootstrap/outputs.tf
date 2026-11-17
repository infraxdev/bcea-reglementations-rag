output "state_bucket" {
  value = aws_s3_bucket.tf_state.id
}

output "lock_table" {
  value = aws_dynamodb_table.tf_lock.name
}

# Set these as GitHub Actions *variables* (not secrets — a role ARN is not sensitive):
#   gh variable set AWS_CI_ROLE_ARN       --body "$(terraform output -raw github_ci_role_arn)"
#   gh variable set AWS_TF_PLAN_ROLE_ARN  --body "$(terraform output -raw github_tf_plan_role_arn)"
#   gh variable set AWS_TF_APPLY_ROLE_ARN --body "$(terraform output -raw github_tf_apply_role_arn)"
# If prod lives in its own account, add `--env prod` there so the prod Environment
# overrides the repo-level value.
output "github_ci_role_arn" {
  value = aws_iam_role.github_ci.arn
}

output "github_tf_plan_role_arn" {
  value = aws_iam_role.github_tf_plan.arn
}

output "github_tf_apply_role_arn" {
  value = aws_iam_role.github_tf_apply.arn
}
