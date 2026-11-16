# Two repositories, both tagged by git SHA from CI:
# - bceao-rag:     the single Python image serving both the api and worker Deployments
#                  (repo root Dockerfile; .github/workflows/cd.yaml).
# - bceao-rag-web: the static frontend served by nginx (web/Dockerfile;
#                  .github/workflows/cd-web.yaml). It's a separate build on a separate
#                  release cadence, so it gets its own repo and lifecycle policy.

resource "aws_ecr_repository" "app" {
  name                 = "bceao-rag"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep the last ${var.keep_last_n} images; expire the rest"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = var.keep_last_n
        }
        action = { type = "expire" }
      }
    ]
  })
}

resource "aws_ecr_repository" "web" {
  name                 = "bceao-rag-web"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "web" {
  repository = aws_ecr_repository.web.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep the last ${var.keep_last_n} images; expire the rest"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = var.keep_last_n
        }
        action = { type = "expire" }
      }
    ]
  })
}
