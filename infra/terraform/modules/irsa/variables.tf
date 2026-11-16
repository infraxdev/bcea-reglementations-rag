variable "role_name" {
  type = string
}

variable "oidc_provider_arn" {
  description = "From the eks module's oidc_provider_arn output."
  type        = string
}

variable "namespace" {
  description = "Kubernetes namespace the ServiceAccount lives in."
  type        = string
}

variable "service_account_name" {
  type = string
}

variable "attach_policy_arns" {
  description = "AWS-managed or customer-managed policy ARNs to attach directly."
  type        = list(string)
  default     = []
}

variable "create_inline_policy" {
  description = "Whether to create an inline IAM role policy"
  type        = bool
  default     = false
}

variable "inline_policy_json" {
  description = "Optional inline policy document (JSON string, e.g. from data.aws_iam_policy_document.*.json) for resource-scoped permissions no managed policy covers."
  type        = string
  default     = null
}

variable "tags" {
  type    = map(string)
  default = {}
}
