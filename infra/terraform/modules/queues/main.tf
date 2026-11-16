# SQS queues for Phase 1 of docs/aws-architecture.md §6 — `POST /crawl` and
# `POST /ingest/{job_id}` enqueue here instead of (or in addition to, during migration)
# running in-process; the `ingest-worker` Karpenter pool's pods long-poll these via
# KEDA's aws-sqs-queue scaler (infra/kubernetes/apps/worker/base/scaledobject.yaml).
#
# Visibility: app/worker.py extends a message's visibility on a heartbeat while its job
# runs, so the queue-level timeout only decides how soon a job held by a crashed worker
# is retried. Redelivery is safe: ingest skips files already moved into processed/, and
# a re-crawl just rewrites the same job's files.

locals {
  queues = {
    crawl  = var.crawl_visibility_timeout_seconds
    ingest = var.ingest_visibility_timeout_seconds
  }
}

resource "aws_sqs_queue" "dlq" {
  for_each = local.queues

  name                      = "bceao-rag-${var.environment}-${each.key}-jobs-dlq"
  message_retention_seconds = 1209600 # 14 days — enough runway to investigate a failed job
  sqs_managed_sse_enabled   = true

  tags = var.tags
}

resource "aws_sqs_queue" "jobs" {
  for_each = local.queues

  name                       = "bceao-rag-${var.environment}-${each.key}-jobs"
  visibility_timeout_seconds = each.value
  message_retention_seconds  = 345600 # 4 days
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = var.max_receive_count
  })

  tags = var.tags
}
