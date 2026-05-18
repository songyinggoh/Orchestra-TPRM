PROJECT := advance-replica-496216-n6
REGION  := us-central1
IMAGE   := $(REGION)-docker.pkg.dev/$(PROJECT)/orchestra/tprm:latest

# Ensure Artifact Registry repo exists before pushing
repo:
	gcloud artifacts repositories create orchestra \
	  --repository-format=docker --location=$(REGION) \
	  --project=$(PROJECT) 2>/dev/null || true

# Build container image via Cloud Build (no local Docker daemon needed)
build: repo
	gcloud builds submit --project=$(PROJECT) --tag=$(IMAGE) --timeout=25m .

# Provision infra + deploy (runs build first)
deploy: build
	cd terraform && terraform init -upgrade && terraform apply -auto-approve

# Update Cloud Run to the latest image without re-running terraform
redeploy: build
	gcloud run deploy orchestra-tprm \
	  --project=$(PROJECT) --region=$(REGION) \
	  --image=$(IMAGE) --platform=managed

# Tear everything down
destroy:
	cd terraform && terraform destroy

# Print the live URL
url:
	@cd terraform && terraform output -raw url

.PHONY: install lint type-check test test-cov fmt clean build deploy redeploy destroy url

install:
	pip install -e ".[dev]"

lint:
	ruff check src/ tests/

fmt:
	ruff format src/ tests/
	ruff check --fix src/ tests/

type-check:
	mypy src/orchestra/

test:
	pytest tests/ -x -q

test-cov:
	pytest tests/ --cov=orchestra --cov-report=term-missing

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +
	rm -rf dist/ build/ *.egg-info
