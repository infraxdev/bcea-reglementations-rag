variable "account_name" {
  description = "Short name of the AWS account this bootstrap runs in (e.g. \"prod\", \"nonprod\") — suffixes the bucket/table names."
  type        = string
}

variable "region" {
  description = "AWS region to create the state bucket/lock table in. Must match every environment's backend.tf region."
  type        = string
  default     = "eu-west-3"
}

variable "github_repository" {
  description = "GitHub repository (\"<org>/<repo>\") whose Actions workflows may assume the CI roles."
  type        = string
  default     = "infraxdev/bcea-reglementations-rag"
}

variable "github_environments" {
  description = "GitHub Environments whose jobs may assume the ci and tf-apply roles from this account. Narrow it per account (e.g. [\"prod\"] in the prod account)."
  type        = list(string)
  default     = ["dev", "staging", "prod"]
}

variable "create_github_oidc_provider" {
  description = "Create the account-wide GitHub OIDC provider. Set to false if the account already has one for token.actions.githubusercontent.com."
  type        = bool
  default     = true
}

variable "ecr_repository_names" {
  description = "ECR repositories the ci role may push to / pull from. Must match infra/terraform/modules/ecr."
  type        = list(string)
  default     = ["bceao-rag", "bceao-rag-web"]
}
