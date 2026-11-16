variable "environment" {
  description = "dev | staging | prod — suffixes every resource name."
  type        = string
}

variable "vpc_cidr" {
  description = "VPC CIDR block (/16). Subnets are carved out of it automatically."
  type        = string
  default     = "10.0.0.0/16"
}

variable "azs" {
  description = "Availability zones to spread subnets across. 3 for prod, 2 is fine for dev/staging (docs/aws-architecture.md §1)."
  type        = list(string)
}

variable "ha_nat" {
  description = "true = one NAT Gateway per AZ (prod HA). false = a single shared NAT Gateway (cheaper, dev/staging)."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Common tags applied to every resource this module creates."
  type        = map(string)
  default     = {}
}
