region          = "eu-west-3"
vpc_cidr        = "10.30.0.0/16"
azs             = ["eu-west-3a", "eu-west-3b", "eu-west-3c"]
cluster_version = "1.31"

system_instance_types   = ["t3.medium", "m5.large"]
system_ami_type         = "AL2023_x86_64_STANDARD"
