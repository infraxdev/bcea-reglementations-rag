# S3 buckets per docs/aws-architecture.md §3: the app's raw/processed crawl data (the
# crawler already supports storage_backend="s3" natively — app/crawler/storage/s3.py —
# so pointing it here is a config change, not a code change), nightly Qdrant snapshots,
# and the Loki/Tempo object-storage backends from §7.

resource "aws_kms_key" "this" {
  description             = "bceao-rag ${var.environment} — S3/Secrets/EBS encryption key"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

resource "aws_kms_alias" "this" {
  name          = "alias/bceao-rag-${var.environment}"
  target_key_id = aws_kms_key.this.key_id
}

# --- App bucket: raw/ + processed/ prefixes, matching S3_PREFIX in .env.example -----

resource "aws_s3_bucket" "app" {
  bucket = "bceao-rag-${var.environment}"
  tags   = var.tags
}

resource "aws_s3_bucket_versioning" "app" {
  bucket = aws_s3_bucket.app.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "app" {
  bucket = aws_s3_bucket.app.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.this.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "app" {
  bucket = aws_s3_bucket.app.id

  rule {
    id     = "raw-to-glacier-ir"
    status = "Enabled"
    filter {
      prefix = "raw/"
    }
    transition {
      days          = 90
      storage_class = "GLACIER_IR"
    }
  }

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

resource "aws_s3_bucket_public_access_block" "app" {
  bucket                  = aws_s3_bucket.app.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# --- Qdrant snapshots -----------------------------------------------------------

resource "aws_s3_bucket" "qdrant_snapshots" {
  bucket = "bceao-rag-qdrant-snapshots-${var.environment}"
  tags   = var.tags
}

resource "aws_s3_bucket_versioning" "qdrant_snapshots" {
  bucket = aws_s3_bucket.qdrant_snapshots.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "qdrant_snapshots" {
  bucket = aws_s3_bucket.qdrant_snapshots.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.this.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "qdrant_snapshots" {
  bucket                  = aws_s3_bucket.qdrant_snapshots.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# --- Observability backends: Loki (logs) + Tempo (traces), docs/aws-architecture.md §7 -

resource "aws_s3_bucket" "loki" {
  bucket = "bceao-rag-loki-${var.environment}"
  tags   = var.tags
}

resource "aws_s3_bucket_server_side_encryption_configuration" "loki" {
  bucket = aws_s3_bucket.loki.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.this.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "loki" {
  bucket = aws_s3_bucket.loki.id
  rule {
    id     = "expire-old-chunks"
    status = "Enabled"
    filter {}
    expiration {
      days = var.log_retention_days
    }
  }
}

resource "aws_s3_bucket_public_access_block" "loki" {
  bucket                  = aws_s3_bucket.loki.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket" "tempo" {
  bucket = "bceao-rag-tempo-${var.environment}"
  tags   = var.tags
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tempo" {
  bucket = aws_s3_bucket.tempo.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.this.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "tempo" {
  bucket = aws_s3_bucket.tempo.id
  rule {
    id     = "expire-old-traces"
    status = "Enabled"
    filter {}
    expiration {
      days = var.trace_retention_days
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tempo" {
  bucket                  = aws_s3_bucket.tempo.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
