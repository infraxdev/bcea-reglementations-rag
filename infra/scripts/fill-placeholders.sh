#!/usr/bin/env bash
# Pulls infra/terraform/environments/<env>'s outputs and substitutes them for the
# matching REPLACE_WITH_TERRAFORM_OUTPUT_* placeholders across infra/kubernetes/.
# Most of these values (bucket names, table/queue names, role ARNs) aren't secrets —
# safe to commit once filled in, which is the intended workflow: run this, review the
# diff, commit it, let Argo CD take over from there. Values this script can't know
# (REPLACE_WITH_GIT_REPO_URL, REPLACE_WITH_ACM_CERTIFICATE_ARN, REPLACE_WITH_SLACK_
# WEBHOOK_SECRET, REPLACE_ME passwords) are left for a human — see `make placeholders`.
set -euo pipefail

ENV="${1:?Usage: fill-placeholders.sh <dev|staging|prod>}"
cd "$(dirname "$0")/../terraform/environments/$ENV"

out() { terraform output -raw "$1" 2>/dev/null || true; }
out_json() { terraform output -json "$1" 2>/dev/null || echo '{}'; }

K8S_DIR="$(dirname "$0")/../../kubernetes"

replace() {
  local placeholder="$1" value="$2"
  [ -z "$value" ] && { echo "skip: $placeholder (terraform output empty)"; return; }
  grep -rl "$placeholder" "$K8S_DIR" 2>/dev/null | while IFS= read -r f; do
    sed -i '' "s|$placeholder|$value|g" "$f"
  done
  echo "filled: $placeholder"
}

replace "REPLACE_WITH_TERRAFORM_OUTPUT_cluster_endpoint" "$(out cluster_endpoint)"
replace "REPLACE_WITH_TERRAFORM_OUTPUT_vpc_id" "$(out vpc_id || true)"
replace "REPLACE_WITH_TERRAFORM_OUTPUT_app_bucket_name" "$(out app_bucket_name)"
replace "REPLACE_WITH_TERRAFORM_OUTPUT_qdrant_snapshots_bucket_name" "$(out qdrant_snapshots_bucket_name || true)"
replace "REPLACE_WITH_TERRAFORM_OUTPUT_karpenter_queue_name" "$(out karpenter_queue_name)"
replace "REPLACE_WITH_TERRAFORM_OUTPUT_karpenter_node_iam_role_name" "$(out karpenter_node_iam_role_name)"
replace "REPLACE_WITH_TERRAFORM_OUTPUT_karpenter_iam_role_arn" "$(out karpenter_iam_role_arn || true)"
replace "REPLACE_WITH_TERRAFORM_OUTPUT_waf_web_acl_arn" "$(out waf_web_acl_arn)"
replace "REPLACE_WITH_TERRAFORM_OUTPUT_jobs_table_name" "$(out jobs_table_name || true)"
replace "REPLACE_WITH_TERRAFORM_OUTPUT_job_progress_table_name" "$(out job_progress_table_name || true)"

for role in api worker qdrant_backup external_secrets loki tempo lb_controller keda; do
  value="$(out_json irsa_role_arns | python3 -c "import sys, json; print(json.load(sys.stdin).get('$role', ''))" 2>/dev/null || true)"
  replace "REPLACE_WITH_TERRAFORM_OUTPUT_irsa_role_arns.$role" "$value"
done

for q in crawl ingest; do
  value="$(out_json queue_urls | python3 -c "import sys, json; print(json.load(sys.stdin).get('$q', ''))" 2>/dev/null || true)"
  replace "REPLACE_WITH_TERRAFORM_OUTPUT_queue_urls.$q" "$value"
done

echo ""
echo "Remaining placeholders (need a human — git remote, domain, Slack webhook, passwords):"
grep -rn "REPLACE_WITH_\|REPLACE_ME" "$K8S_DIR" || echo "  none"
