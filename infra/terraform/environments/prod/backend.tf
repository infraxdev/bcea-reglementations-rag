# Created by infra/terraform/bootstrap/ — prod gets its own AWS account entirely
# (docs/aws-architecture.md §1), so its own state bucket.
terraform {
  backend "s3" {
    bucket         = "bceao-rag-tfstate-prod"
    key            = "prod/terraform.tfstate"
    region         = "eu-west-3"
    dynamodb_table = "bceao-rag-tfstate-lock-prod"
    encrypt        = true
  }
}
