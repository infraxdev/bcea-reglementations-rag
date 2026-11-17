locals {
  environment = "prod"
  common_tags = {
    Project     = "bceao-rag"
    Environment = local.environment
    ManagedBy   = "terraform"
  }
}

module "vpc" {
  source = "../../modules/vpc"

  environment = local.environment
  vpc_cidr    = var.vpc_cidr
  azs         = var.azs
  ha_nat      = true # one NAT Gateway per AZ — prod HA per docs/aws-architecture.md §1
  tags        = local.common_tags
}

module "eks" {
  source = "../../modules/eks"

  environment           = local.environment
  cluster_version       = var.cluster_version
  vpc_id                = module.vpc.vpc_id
  private_subnet_ids    = module.vpc.private_subnet_ids
  system_instance_types = var.system_instance_types
  system_min_size       = 2
  system_max_size       = 5
  system_desired_size   = 2
  tags                  = local.common_tags
}

module "storage" {
  source = "../../modules/storage"

  environment = local.environment
  tags        = local.common_tags
}

module "data" {
  source = "../../modules/data"

  environment = local.environment
  tags        = local.common_tags
}

module "queues" {
  source = "../../modules/queues"

  environment = local.environment
  tags        = local.common_tags
}

module "secrets" {
  source = "../../modules/secrets"

  environment           = local.environment
  secret_names          = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "QDRANT_API_KEY"]
  recovery_window_days  = 0
  tags                  = local.common_tags
}

module "ecr" {
  source = "../../modules/ecr"

  tags = local.common_tags
}

# --- IRSA roles: one per workload, least privilege, per docs/aws-architecture.md §4 ---

data "aws_iam_policy_document" "api" {
  statement {
    sid       = "AppBucketReadWrite"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:DeleteObject"]
    resources = [module.storage.app_bucket_arn, "${module.storage.app_bucket_arn}/*"]
  }
  statement {
    sid       = "JobStateTables"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query"]
    resources = [module.data.jobs_table_arn, module.data.job_progress_table_arn]
  }
  statement {
    sid       = "EnqueueJobs"
    actions   = ["sqs:SendMessage"]
    resources = values(module.queues.queue_arns)
  }
}

module "irsa_api" {
  source = "../../modules/irsa"

  role_name            = "bceao-rag-${local.environment}-api"
  oidc_provider_arn    = module.eks.oidc_provider_arn
  namespace            = "bceao-rag"
  service_account_name = "api"
  create_inline_policy = true
  inline_policy_json   = data.aws_iam_policy_document.api.json
  tags                 = local.common_tags
}

data "aws_iam_policy_document" "worker" {
  statement {
    sid     = "AppAndSnapshotBuckets"
    actions = ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:DeleteObject"]
    resources = [
      module.storage.app_bucket_arn, "${module.storage.app_bucket_arn}/*",
      module.storage.qdrant_snapshots_bucket_arn, "${module.storage.qdrant_snapshots_bucket_arn}/*",
    ]
  }
  statement {
    sid       = "JobStateTables"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query"]
    resources = [module.data.jobs_table_arn, module.data.job_progress_table_arn]
  }
  statement {
    sid       = "ConsumeJobs"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:ChangeMessageVisibility"]
    resources = values(module.queues.queue_arns)
  }
}

module "irsa_worker" {
  source = "../../modules/irsa"

  role_name            = "bceao-rag-${local.environment}-worker"
  oidc_provider_arn    = module.eks.oidc_provider_arn
  namespace            = "bceao-rag"
  service_account_name = "worker"
  inline_policy_json   = data.aws_iam_policy_document.worker.json
  tags                 = local.common_tags
}

data "aws_iam_policy_document" "qdrant_backup" {
  statement {
    sid       = "SnapshotBucket"
    actions   = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"]
    resources = [module.storage.qdrant_snapshots_bucket_arn, "${module.storage.qdrant_snapshots_bucket_arn}/*"]
  }
}

module "irsa_qdrant_backup" {
  source = "../../modules/irsa"

  role_name            = "bceao-rag-${local.environment}-qdrant-backup"
  oidc_provider_arn    = module.eks.oidc_provider_arn
  namespace            = "bceao-rag"
  service_account_name = "qdrant-backup"
  inline_policy_json   = data.aws_iam_policy_document.qdrant_backup.json
  tags                 = local.common_tags
}

data "aws_iam_policy_document" "external_secrets" {
  statement {
    sid       = "ReadAppSecrets"
    actions   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    resources = values(module.secrets.secret_arns)
  }
}

module "irsa_external_secrets" {
  source = "../../modules/irsa"

  role_name            = "bceao-rag-${local.environment}-external-secrets"
  oidc_provider_arn    = module.eks.oidc_provider_arn
  namespace            = "external-secrets"
  service_account_name = "external-secrets"
  inline_policy_json   = data.aws_iam_policy_document.external_secrets.json
  tags                 = local.common_tags
}

data "aws_iam_policy_document" "loki" {
  statement {
    sid       = "LokiBucket"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:DeleteObject"]
    resources = [module.storage.loki_bucket_arn, "${module.storage.loki_bucket_arn}/*"]
  }
}

module "irsa_loki" {
  source = "../../modules/irsa"

  role_name            = "bceao-rag-${local.environment}-loki"
  oidc_provider_arn    = module.eks.oidc_provider_arn
  namespace            = "observability"
  service_account_name = "loki"
  inline_policy_json   = data.aws_iam_policy_document.loki.json
  tags                 = local.common_tags
}

data "aws_iam_policy_document" "tempo" {
  statement {
    sid       = "TempoBucket"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:DeleteObject"]
    resources = [module.storage.tempo_bucket_arn, "${module.storage.tempo_bucket_arn}/*"]
  }
}

module "irsa_tempo" {
  source = "../../modules/irsa"

  role_name            = "bceao-rag-${local.environment}-tempo"
  oidc_provider_arn    = module.eks.oidc_provider_arn
  namespace            = "observability"
  service_account_name = "tempo"
  inline_policy_json   = data.aws_iam_policy_document.tempo.json
  tags                 = local.common_tags
}

# AWS Load Balancer Controller — provisions the ALB behind the Kubernetes Ingress
# (docs/aws-architecture.md §2). Its IAM policy is AWS's own large, frequently-updated
# JSON document, so this uses the community module's built-in flag for it rather than
# hand-copying that document into this repo.
module "irsa_lb_controller" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.44"

  role_name                              = "bceao-rag-${local.environment}-lb-controller"
  attach_load_balancer_controller_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:aws-load-balancer-controller"]
    }
  }

  tags = local.common_tags
}

# KEDA's AWS SQS scaler reads queue depth to size the worker Deployment
# (infra/kubernetes/apps/worker/base/scaledobject.yaml) — read-only, deliberately
# separate from the worker pods' own consumer role above.
data "aws_iam_policy_document" "keda" {
  statement {
    sid       = "ReadQueueDepth"
    actions   = ["sqs:GetQueueAttributes"]
    resources = values(module.queues.queue_arns)
  }
}

module "irsa_keda" {
  source = "../../modules/irsa"

  role_name            = "bceao-rag-${local.environment}-keda"
  oidc_provider_arn    = module.eks.oidc_provider_arn
  namespace            = "keda"
  service_account_name = "keda-operator"
  inline_policy_json   = data.aws_iam_policy_document.keda.json
  tags                 = local.common_tags
}

module "waf" {
  source = "../../modules/waf"

  environment = local.environment
  tags        = local.common_tags
}
