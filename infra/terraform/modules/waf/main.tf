# Regional WAFv2 Web ACL for the ALB in front of the API (docs/aws-architecture.md §2/
# §8). Not associated here — the AWS Load Balancer Controller does that itself when the
# Ingress carries this ACL's ARN via the alb.ingress.kubernetes.io/wafv2-acl-arn
# annotation (infra/kubernetes/apps/ingress/base/ingress.yaml), since the ALB itself
# doesn't exist until that Ingress is applied.

resource "aws_wafv2_web_acl" "api" {
  name        = "bceao-rag-${var.environment}"
  description = "WAF for the BCEAO RAG API ALB"
  scope       = "REGIONAL"

  default_action {
    allow {}
  }

  rule {
    name     = "aws-managed-common"
    priority = 0
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "aws-managed-common"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "rate-limit-per-ip"
    priority = 1
    action {
      block {}
    }
    statement {
      rate_based_statement {
        limit              = var.rate_limit_per_5min
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "rate-limit-per-ip"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "bceao-rag-${var.environment}"
    sampled_requests_enabled   = true
  }

  tags = var.tags
}
