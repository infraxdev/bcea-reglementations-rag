variable "environment" {
  type = string
}

variable "secret_names" {
  description = "Names (not values) of the secrets to create — matches app/config.py's env vars, e.g. [\"OPENAI_API_KEY\", \"ANTHROPIC_API_KEY\", \"QDRANT_API_KEY\"]."
  type        = list(string)
}

variable "recovery_window_days" {
  type    = number
  default = 7
}

variable "tags" {
  type    = map(string)
  default = {}
}
