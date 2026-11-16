output "queue_urls" {
  value = { for k, q in aws_sqs_queue.jobs : k => q.id }
}

output "queue_arns" {
  value = { for k, q in aws_sqs_queue.jobs : k => q.arn }
}

output "dlq_urls" {
  value = { for k, q in aws_sqs_queue.dlq : k => q.id }
}

output "dlq_arns" {
  value = { for k, q in aws_sqs_queue.dlq : k => q.arn }
}
