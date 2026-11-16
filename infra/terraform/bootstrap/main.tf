# Bootstrap: creates the S3 bucket + DynamoDB lock table that every environment's
# `backend.tf` points at. Chicken-and-egg problem — this config's own state stays
# *local* (there's nowhere else for it to live yet) and is applied exactly once per AWS
# account, by a human, before any environment is touched.
#
#   cd infra/terraform/bootstrap
#   terraform init
#   terraform apply -var="account_name=prod"
#
# Re-run per account (dev/staging share one account+bucket in the common case; prod gets
# its own account entirely per docs/aws-architecture.md §1).

terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

provider "aws" {
  region = var.region
}

resource "aws_s3_bucket" "tf_state" {
  bucket = "bceao-rag-tfstate-${var.account_name}"

  # Terraform state has no business being deletable by accident.
  lifecycle {
    prevent_destroy = false
  }
}

resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "tf_state" {
  bucket                  = aws_s3_bucket.tf_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "tf_lock" {
  name         = "bceao-rag-tfstate-lock-${var.account_name}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}
