# Thin wrapper around the community vpc module rather than hand-rolled subnet/route
# resources — docs/aws-architecture.md §1: public subnets for ALB/NAT only, private
# subnets for everything else (EKS nodes, Qdrant, Ollama), VPC endpoints for
# S3/ECR/STS/Secrets Manager/CloudWatch Logs/SQS/DynamoDB so that traffic never needs to
# leave the VPC through NAT just to reach other AWS services.

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.8"

  name = "bceao-rag-${var.environment}"
  cidr = var.vpc_cidr

  azs             = var.azs
  private_subnets = [for i, az in var.azs : cidrsubnet(var.vpc_cidr, 4, i)]
  public_subnets  = [for i, az in var.azs : cidrsubnet(var.vpc_cidr, 4, i + 8)]

  enable_nat_gateway = true
  # One NAT per AZ in prod for HA; a single shared NAT elsewhere to cut cost
  # (docs/aws-architecture.md §1).
  single_nat_gateway     = !var.ha_nat
  one_nat_gateway_per_az = var.ha_nat

  enable_dns_hostnames = true
  enable_dns_support   = true

  # Required tags for the EKS/Karpenter/AWS Load Balancer Controller auto-discovery
  # used by the eks module.
  public_subnet_tags = {
    "kubernetes.io/role/elb"                             = "1"
    "kubernetes.io/cluster/bceao-rag-${var.environment}" = "shared"
  }
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb"                    = "1"
    "kubernetes.io/cluster/bceao-rag-${var.environment}" = "shared"
    "karpenter.sh/discovery"                             = "bceao-rag-${var.environment}"
  }

  tags = var.tags
}

# Interface endpoints for the AWS APIs the cluster talks to constantly — keeps that
# traffic off NAT (cost) and off the public internet (security), per
# docs/aws-architecture.md §1.
module "vpc_endpoints" {
  source  = "terraform-aws-modules/vpc/aws//modules/vpc-endpoints"
  version = "~> 5.8"

  vpc_id = module.vpc.vpc_id

  endpoints = {
    s3 = {
      service         = "s3"
      service_type    = "Gateway"
      route_table_ids = module.vpc.private_route_table_ids
    }
    dynamodb = {
      service         = "dynamodb"
      service_type    = "Gateway"
      route_table_ids = module.vpc.private_route_table_ids
    }
    ecr_api = {
      service             = "ecr.api"
      service_type        = "Interface"
      private_dns_enabled = true
      subnet_ids          = module.vpc.private_subnets
      security_group_ids  = [aws_security_group.vpc_endpoints.id]
    }
    ecr_dkr = {
      service             = "ecr.dkr"
      service_type        = "Interface"
      private_dns_enabled = true
      subnet_ids          = module.vpc.private_subnets
      security_group_ids  = [aws_security_group.vpc_endpoints.id]
    }
    sts = {
      service             = "sts"
      service_type        = "Interface"
      private_dns_enabled = true
      subnet_ids          = module.vpc.private_subnets
      security_group_ids  = [aws_security_group.vpc_endpoints.id]
    }
    secretsmanager = {
      service             = "secretsmanager"
      service_type        = "Interface"
      private_dns_enabled = true
      subnet_ids          = module.vpc.private_subnets
      security_group_ids  = [aws_security_group.vpc_endpoints.id]
    }
    logs = {
      service             = "logs"
      service_type        = "Interface"
      private_dns_enabled = true
      subnet_ids          = module.vpc.private_subnets
      security_group_ids  = [aws_security_group.vpc_endpoints.id]
    }
    sqs = {
      service             = "sqs"
      service_type        = "Interface"
      private_dns_enabled = true
      subnet_ids          = module.vpc.private_subnets
      security_group_ids  = [aws_security_group.vpc_endpoints.id]
    }
  }

  tags = var.tags
}

resource "aws_security_group" "vpc_endpoints" {
  name        = "bceao-rag-${var.environment}-vpce"
  description = "Allows HTTPS from inside the VPC to interface VPC endpoints"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "HTTPS from the VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = var.tags
}
