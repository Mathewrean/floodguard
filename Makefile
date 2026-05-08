.PHONY: help install migrate run test lint format security-check docker-build docker-up docker-down clean

help:  ## Show this help message
	@echo 'FloodGuard Makefile Commands:'
	@echo ''
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install Python dependencies in virtual environment
	python -m venv floodguard_env
	. floodguard_env/bin/activate && pip install --upgrade pip
	. floodguard_env/bin/activate && pip install -r requirements.txt
	@echo "Dependencies installed. Activate with: source floodguard_env/bin/activate"

migrate:  ## Apply database migrations
	. floodguard_env/bin/activate && python manage.py migrate

collectstatic:  ## Collect static files
	. floodguard_env/bin/activate && python manage.py collectstatic --noinput

createsuperuser:  ## Create Django superuser (interactive)
	. floodguard_env/bin/activate && python manage.py createsuperuser

seed-demo:  ## Seed demo data for development
	. floodguard_env/bin/activate && python manage.py seed_demo_data

run:  ## Run Django development server
	. floodguard_env/bin/activate && python manage.py runserver

run-all:  ## Run all services (web, celery worker, celery beat) - requires separate terminals
	@echo "Start services in separate terminals:"
	@echo "  Terminal 1: make run"
	@echo "  Terminal 2: make celery-worker"
	@echo "  Terminal 3: make celery-beat"

celery-worker:  ## Start Celery worker
	. floodguard_env/bin/activate && celery -A floodguard worker -l info

celery-beat:  ## Start Celery beat scheduler
	. floodguard_env/bin/activate && celery -A floodguard beat -l info

redis-start:  ## Start Redis server (if not running)
	@echo "Starting Redis server..."
	redis-server --daemonize yes
	@sleep 1
	@echo "Redis started on port 6379"

test:  ## Run test suite with coverage
	. floodguard_env/bin/activate && pytest --cov=core --cov-report=html --cov-report=term

test-unit:  ## Run unit tests only
	. floodguard_env/bin/activate && pytest tests/unit/

test-integration:  ## Run integration tests only
	. floodguard_env/bin/activate && pytest tests/integration/

test-e2e:  ## Run end-to-end tests only
	. floodguard_env/bin/activate && pytest tests/e2e/

lint:  ## Run code linting (flake8)
	. floodguard_env/bin/activate && flake8 core --max-line-length=100

format:  ## Auto-format code (black)
	. floodguard_env/bin/activate && black core tests --line-length 100

security-check:  ## Run security checks (bandit)
	. floodguard_env/bin/activate && bandit -r core -ll

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
	. floodguard_env/bin/activate && python scripts/generate_readme.py --output README.md

pre-commit-install:  ## Install pre-commit hook
	pre-commit install

ci-test:  ## Run CI pipeline test suite (headless)
	. floodguard_env/bin/activate && pytest --cov=core --cov-report=xml
