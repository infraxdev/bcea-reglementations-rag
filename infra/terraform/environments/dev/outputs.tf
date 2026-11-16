output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "ecr_repository_url" {
  value = module.ecr.repository_url
}

output "web_ecr_repository_url" {
  value = module.ecr.web_repository_url
}

output "app_bucket_name" {
  value = module.storage.app_bucket_name
}

output "queue_urls" {
  value = module.queues.queue_urls
}

output "irsa_role_arns" {
  value = {
    api              = module.irsa_api.role_arn
    worker           = module.irsa_worker.role_arn
    qdrant_backup    = module.irsa_qdrant_backup.role_arn
    external_secrets = module.irsa_external_secrets.role_arn
    loki             = module.irsa_loki.role_arn
    tempo            = module.irsa_tempo.role_arn
    lb_controller    = module.irsa_lb_controller.iam_role_arn
    keda             = module.irsa_keda.role_arn
  }
}

output "karpenter_queue_name" {
  value = module.eks.karpenter_queue_name
}

output "karpenter_node_iam_role_name" {
  value = module.eks.karpenter_node_iam_role_name
}

output "waf_web_acl_arn" {
  value = module.waf.web_acl_arn
}

output "vpc_id" {
  value = module.vpc.vpc_id
}

output "qdrant_snapshots_bucket_name" {
  value = module.storage.qdrant_snapshots_bucket_name
}

output "karpenter_iam_role_arn" {
  value = module.eks.karpenter_iam_role_arn
}

output "jobs_table_name" {
  value = module.data.jobs_table_name
}

output "job_progress_table_name" {
  value = module.data.job_progress_table_name
}
