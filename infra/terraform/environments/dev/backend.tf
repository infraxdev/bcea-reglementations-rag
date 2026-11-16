# Created by infra/terraform/bootstrap/ — run once per account before this environment
# is ever applied. dev+staging share the nonprod account/bucket in the common case;
# swap the bucket name if you've split them further.
terraform {
  backend "local" {
    bucket         = "bceao-rag-tfstate-nonprod"
    key            = "dev/terraform.tfstate"
    region         = "eu-west-3"
    dynamodb_table = "bceao-rag-tfstate-lock-nonprod"
    encrypt        = true
  }
}
