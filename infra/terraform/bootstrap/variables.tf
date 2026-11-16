variable "account_name" {
  description = "Short name of the AWS account this bootstrap runs in (e.g. \"prod\", \"nonprod\") — suffixes the bucket/table names."
  type        = string
}

variable "region" {
  description = "AWS region to create the state bucket/lock table in. Must match every environment's backend.tf region."
  type        = string
  default     = "eu-west-3"
}
