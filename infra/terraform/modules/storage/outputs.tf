output "app_bucket_name" {
  value = aws_s3_bucket.app.id
}

output "app_bucket_arn" {
  value = aws_s3_bucket.app.arn
}

output "qdrant_snapshots_bucket_name" {
  value = aws_s3_bucket.qdrant_snapshots.id
}

output "qdrant_snapshots_bucket_arn" {
  value = aws_s3_bucket.qdrant_snapshots.arn
}

output "loki_bucket_name" {
  value = aws_s3_bucket.loki.id
}

output "loki_bucket_arn" {
  value = aws_s3_bucket.loki.arn
}

output "tempo_bucket_name" {
  value = aws_s3_bucket.tempo.id
}

output "tempo_bucket_arn" {
  value = aws_s3_bucket.tempo.arn
}

output "kms_key_arn" {
  value = aws_kms_key.this.arn
}
