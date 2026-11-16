variable "environment" {
  type = string
}

variable "log_retention_days" {
  description = "Loki S3 chunk retention (Grafana isn't the system of record for anything compliance-relevant — docs/aws-architecture.md §7)."
  type        = number
  default     = 30
}

variable "trace_retention_days" {
  type    = number
  default = 15
}

variable "tags" {
  type    = map(string)
  default = {}
}
