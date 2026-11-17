# Common tasks. Run `make help` to list them.

COMPOSE = docker compose
BACKEND = cd backend && uv run
FRONTEND = cd frontend && npm

.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

env: ## Create .env from .env.example if missing
	@test -f .env || cp .env.example .env

up: env ## Build and start the whole stack
	$(COMPOSE) up --build -d
	@echo "Frontend: http://localhost:$$(grep ^FRONTEND_PORT .env | cut -d= -f2)"
	@echo "API:      http://localhost:$$(grep ^BACKEND_PORT .env | cut -d= -f2)/api/"

down: ## Stop the stack
	$(COMPOSE) down

destroy: ## Stop the stack and delete its data
	$(COMPOSE) down -v

logs: ## Follow the logs
	$(COMPOSE) logs -f

ps: ## Show the services
	$(COMPOSE) ps

db: env ## Start only the database (for running the backend locally)
	$(COMPOSE) up -d db

install: ## Install backend and frontend dependencies
	cd backend && uv sync
	$(FRONTEND) install

migrate: ## Apply the database migrations
	$(BACKEND) python manage.py migrate

checklists: ## Load the checklists shipped with the project
	$(BACKEND) python manage.py load_checklists

backend-dev: ## Run the Django development server
	$(BACKEND) python manage.py runserver 0.0.0.0:$${BACKEND_PORT:-8010}

frontend-dev: ## Run the Angular development server
	$(FRONTEND) start

test: ## Run the backend tests (durable resume test needs TEST_DATABASE_URL)
	$(BACKEND) pytest

test-all: db ## Run every backend test, including the PostgreSQL restart test
	cd backend && TEST_DATABASE_URL=$$(grep ^DATABASE_URL ../.env | cut -d= -f2-) uv run pytest

lint: ## Lint and format check
	$(BACKEND) ruff format --check .
	$(BACKEND) ruff check .

format: ## Format the backend code
	$(BACKEND) ruff format .
	$(BACKEND) ruff check --fix .

review: ## Run a review from the command line: make review APP=backend/examples/incomplete_application
	$(BACKEND) python -m scripts.run_review $(abspath $(APP))

eval: ## Run the evaluation set with the configured model
	$(BACKEND) python -m evaluation.run

shell: ## Open a Django shell
	$(BACKEND) python manage.py shell

studio: ## Serve the graph for LangGraph Studio on port 2024
	$(BACKEND) langgraph dev --port 2024

.PHONY: help env up down destroy logs ps db install migrate checklists backend-dev frontend-dev test test-all lint format review eval shell studio
