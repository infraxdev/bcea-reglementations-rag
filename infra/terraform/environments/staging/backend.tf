# Created by infra/terraform/bootstrap/ — dev+staging share the nonprod account/bucket.
terraform {
  backend "local" {
    bucket         = "bceao-rag-tfstate-nonprod"
    key            = "staging/terraform.tfstate"
    region         = "eu-west-3"
    dynamodb_table = "bceao-rag-tfstate-lock-nonprod"
    encrypt        = true
  }
}
