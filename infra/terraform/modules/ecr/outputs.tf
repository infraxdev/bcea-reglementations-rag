output "repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "repository_name" {
  value = aws_ecr_repository.app.name
}

output "repository_arn" {
  value = aws_ecr_repository.app.arn
}

output "web_repository_url" {
  value = aws_ecr_repository.web.repository_url
}

output "web_repository_arn" {
  value = aws_ecr_repository.web.arn
}
