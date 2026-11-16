variable "environment" {
  type = string
}

variable "cluster_version" {
  description = "Kubernetes version. Upgrade quarterly per docs/aws-architecture.md §2."
  type        = string
  default     = "1.31"
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "cluster_public_access_cidrs" {
  description = "CIDR blocks allowed to access the EKS cluster endpoint. Use this to restrict access to the cluster endpoint."
  type        = list(string)
  default     = ["x.x.x.x/32"]
}

variable "system_ami_type" {
  type    = string
  default = "AL2023_x86_64_STANDARD"
}

variable "system_instance_types" {
  type    = list(string)
  default = ["m7g.medium"]
}

variable "system_min_size" {
  type    = number
  default = 2
}

variable "system_max_size" {
  type    = number
  default = 4
}

variable "system_desired_size" {
  type    = number
  default = 2
}

variable "tags" {
  type    = map(string)
  default = {}
}
