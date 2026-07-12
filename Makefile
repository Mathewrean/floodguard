PYTHON ?= python3.11
VENV_DIR ?= floodguard-env
VENV_PYTHON := $(VENV_DIR)/bin/python
VENV_PIP := $(VENV_DIR)/bin/pip

.PHONY: help install migrate run test lint format security-check docker-build docker-up docker-down clean

help:  ## Show this help message
	@echo 'FloodGuard Makefile Commands:'
	@echo ''
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install Python dependencies in virtual environment
	$(PYTHON) -m venv $(VENV_DIR)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -r requirements.txt
	@echo "Dependencies installed. Activate with: source $(VENV_DIR)/bin/activate"

migrate:  ## Apply database migrations
	$(VENV_PYTHON) manage.py migrate

collectstatic:  ## Collect static files
	$(VENV_PYTHON) manage.py collectstatic --noinput

createsuperuser:  ## Create Django superuser (interactive)
	$(VENV_PYTHON) manage.py createsuperuser

seed-demo:  ## Seed demo data for development
	$(VENV_PYTHON) manage.py seed_demo_data

run:  ## Run the Django development server
	$(VENV_PYTHON) manage.py runserver 0.0.0.0:8000

run-all:  ## Run the Django development server
	$(VENV_PYTHON) manage.py runserver 0.0.0.0:8000

celery-worker:  ## Start Celery worker
	$(VENV_DIR)/bin/celery -A floodguard worker -l info

celery-beat:  ## Start Celery beat scheduler
	$(VENV_DIR)/bin/celery -A floodguard beat -l info

redis-start:  ## Start Redis server (if not running)
	@echo "Starting Redis server..."
	redis-server --daemonize yes
	@sleep 1
	@echo "Redis started on port 6379"

test:  ## Run test suite with coverage
	$(VENV_DIR)/bin/pytest --cov=core --cov-report=html --cov-report=term

test-unit:  ## Run unit tests only
	$(VENV_DIR)/bin/pytest tests/unit/

test-integration:  ## Run integration tests only
	$(VENV_DIR)/bin/pytest tests/integration/

test-e2e:  ## Run end-to-end tests only
	$(VENV_DIR)/bin/pytest tests/e2e/

lint:  ## Run code linting (flake8)
	$(VENV_DIR)/bin/flake8 core --max-line-length=100

format:  ## Auto-format code (black)
	$(VENV_DIR)/bin/black core tests --line-length 100

security-check:  ## Run security checks (bandit)
	$(VENV_DIR)/bin/bandit -r core -ll

docker-build:  ## Build Docker images
	docker-compose build

docker-up:  ## Start all Docker services
	docker-compose up -d
	@echo "Services starting... Check logs with: docker-compose logs -f"

docker-down:  ## Stop all Docker services
	docker-compose down

docker-logs:  ## View Docker logs
	docker-compose logs -f

docker-clean:  ## Remove Docker volumes and rebuild clean
	docker-compose down -v
	docker-compose build --no-cache
	docker-compose up -d

clean:  ## Clean Python cache files and temporary files
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf staticfiles
	rm -rf media
	@echo "Cleaned build artifacts"

update-readme:  ## Regenerate README.md from project structure
	$(VENV_PYTHON) scripts/generate_readme.py --output README.md

pre-commit-install:  ## Install pre-commit hook
	pre-commit install

ci-test:  ## Run CI pipeline test suite (headless)
	$(VENV_DIR)/bin/pytest --cov=core --cov-report=xml
