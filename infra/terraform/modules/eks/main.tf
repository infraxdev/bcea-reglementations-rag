# Thin wrapper around the community eks module. Only a small `system` managed node
# group is created here — everything else (api/ingest-worker/qdrant/llm-gpu) is
# Karpenter-provisioned per docs/aws-architecture.md §2, because those pools need
# Spot/on-demand mixing and scale-to-zero that a static managed node group can't do as
# cleanly. The `system` group exists so cluster add-ons (CoreDNS, the LB controller,
# Karpenter's own controller pod) have somewhere to run before Karpenter itself is up.

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.31"

  cluster_name    = "bceao-rag-${var.environment}"
  cluster_version = var.cluster_version

  vpc_id                   = var.vpc_id
  subnet_ids               = var.private_subnet_ids
  control_plane_subnet_ids = var.private_subnet_ids

#   cluster_endpoint_public_access  = var.environment != "prod"
  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true

  cluster_endpoint_public_access_cidrs = var.cluster_public_access_cidrs

  cluster_addons = {
    coredns    = { most_recent = true }
    kube-proxy = { most_recent = true }
    vpc-cni    = { most_recent = true }
    aws-ebs-csi-driver = {
      most_recent              = true
      service_account_role_arn = module.ebs_csi_irsa.iam_role_arn
    }
  }

  eks_managed_node_groups = {
    system = {
      ami_type       = var.system_ami_type
      instance_types = var.system_instance_types
      min_size       = var.system_min_size
      max_size       = var.system_max_size
      desired_size   = var.system_desired_size
      labels = {
        "bceao.io/pool" = "system"
      }
      # No taint — CoreDNS, the LB controller, Karpenter's controller, and the
      # observability stack (docs/aws-architecture.md §7) all run here by default.
    }
  }

  # Karpenter-provisioned nodes need to join the cluster via this access entry (the
  # EKS API-based auth mode, not the legacy aws-auth ConfigMap).
  enable_cluster_creator_admin_permissions = true
  authentication_mode                      = "API_AND_CONFIG_MAP"

  tags = merge(var.tags, {
    "karpenter.sh/discovery" = "bceao-rag-${var.environment}"
  })
}

# IRSA role for the EBS CSI driver (Qdrant's PVC, Prometheus's PVC — anything backed by
# EBS gp3 per docs/aws-architecture.md §3/§7).
module "ebs_csi_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.44"

  role_name             = "bceao-rag-${var.environment}-ebs-csi"
  attach_ebs_csi_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:ebs-csi-controller-sa"]
    }
  }

  tags = var.tags
}

# Karpenter controller IAM role + the SQS queue it uses for Spot interruption
# notices — provisions the *controller*; the NodePools/NodeClasses it manages are
# applied as Kubernetes manifests (infra/kubernetes/addons/karpenter/nodepools/), not
# Terraform, since they're cluster-native CRDs that change far more often than the IAM
# boundary around them.
module "karpenter" {
  source  = "terraform-aws-modules/eks/aws//modules/karpenter"
  version = "~> 20.31"

  cluster_name          = module.eks.cluster_name
  enable_v1_permissions = true

  node_iam_role_additional_policies = {
    AmazonSSMManagedInstanceCore = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
  }

  tags = var.tags
}
