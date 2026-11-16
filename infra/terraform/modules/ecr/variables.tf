variable "keep_last_n" {
  type    = number
  default = 30
}

variable "tags" {
  type    = map(string)
  default = {}
}
