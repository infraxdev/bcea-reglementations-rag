# Convenience wrappers — nothing here that CI doesn't also do directly (see
# .github/workflows/). ENV defaults to dev; override with `make plan ENV=prod`.

ENV ?= dev
TF_DIR := terraform/environments/$(ENV)

.PHONY: bootstrap init plan apply fmt validate kubeconfig placeholders

bootstrap: ## One-time: create the Terraform remote-state backend for an account (make bootstrap ACCOUNT=nonprod)
	cd terraform/bootstrap && terraform init && terraform apply -var="account_name=$(ACCOUNT)"

init: ## terraform init for $(ENV)
	cd $(TF_DIR) && terraform init

plan: init ## terraform plan for $(ENV)
	cd $(TF_DIR) && terraform plan

apply: init ## terraform apply for $(ENV)
	cd $(TF_DIR) && terraform apply

fmt: ## terraform fmt across every module/environment
	cd terraform && terraform fmt -recursive

validate: init ## terraform validate for $(ENV)
	cd $(TF_DIR) && terraform validate

kubeconfig: ## Point kubectl at $(ENV)'s cluster
	aws eks update-kubeconfig --name bceao-rag-$(ENV) --region eu-west-3

placeholders: ## List every REPLACE_WITH_* / REPLACE_ME left to fill in
	grep -rn "REPLACE_WITH_\|REPLACE_ME" .. --include="*.yaml" --include="*.yml" --include="*.tf" --include="Dockerfile" || echo "None left."
