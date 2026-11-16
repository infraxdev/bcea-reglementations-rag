variable "region" {
  type    = string
  default = "eu-west-3"
}

variable "vpc_cidr" {
  type    = string
  default = "10.30.0.0/16"
}

variable "azs" {
  type    = list(string)
  default = ["eu-west-3a", "eu-west-3b", "eu-west-3c"]
}

variable "cluster_version" {
  type    = string
  default = "1.31"
}

variable "system_ami_type" {
  type    = string
  default = "AL2023_x86_64_STANDARD"
}

variable "system_instance_types" {
  type    = list(string)
  default = ["m7g.large"]
}
