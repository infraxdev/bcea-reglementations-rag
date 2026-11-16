variable "region" {
  type    = string
  default = "eu-west-3"
}

variable "vpc_cidr" {
  type    = string
  default = "10.10.0.0/16"
}

variable "azs" {
  type    = list(string)
  default = ["eu-west-3a", "eu-west-3b"]
}

variable "cluster_version" {
  type    = string
  default = "1.31"
}

variable "system_instance_types" {
  type    = list(string)
  default = ["m7g.medium"]
}
