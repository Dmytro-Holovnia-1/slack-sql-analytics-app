DC := docker compose
PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip
PRE_COMMIT ?= .venv/bin/pre-commit

.PHONY: help setup run smoke-startup db-up db-down db-seed db-bootstrap test check generate-csv eval-setup eval-run

help:
	@echo "Usage: make <target>"
	@echo "  setup    Build images and configure git hooks"
	@echo "  run      Run the Slack bot app"
	@echo "  smoke-startup  Run the startup smoke test"
	@echo "  db-up    Start the PostgreSQL service"
	@echo "  db-down  Stop the PostgreSQL service"
	@echo "  db-seed  Seed PostgreSQL with deterministic demo data"
	@echo "  db-bootstrap  Start PostgreSQL and load deterministic demo data"
	@echo "  test     Run the smoke test suite"
	@echo "  check    Run all checks (tests, lint, type check)"
	@echo "  generate-csv  Generate the seed data CSV file"
	@echo "  eval-setup    Create/Update LangSmith evaluation dataset"
	@echo "  eval-run      Run LangGraph evaluation on the dataset"
	@echo "  stress    Run the stress test suite with optional concurrency (default: 40) e.g. 'make stress c=50'"

setup-dev:
	$(PIP) install -r requirements-dev.txt
	$(PRE_COMMIT) install

setup:
	$(DC) build
	$(MAKE) setup-dev

run:
	$(DC) up --build

smoke-startup:
	$(PYTHON) -m pytest tests/test_app_startup.py -q

db-up:
	$(DC) up -d postgres

db-down:
	$(DC) stop postgres

db-seed:
	@echo "Waiting for PostgreSQL to be ready..."
	@until docker compose exec -T postgres pg_isready -U $${POSTGRES_USER:-rounds_admin} -d $${POSTGRES_DB:-rounds_analytics} > /dev/null 2>&1; do \
		echo "PostgreSQL is unavailable - sleeping..."; \
		sleep 1; \
	done
	@echo "PostgreSQL is up and running"
	POSTGRES_HOST=localhost $(PYTHON) init_db/seed_data.py

db-bootstrap:
	$(MAKE) db-up
	$(MAKE) db-seed

test:
	$(PYTHON) -m pytest tests -q

check:
	$(MAKE) test
	$(PYTHON) -m ruff check app tests
	$(PYTHON) -m mypy app tests --show-error-codes --ignore-missing-imports

generate-csv:
	$(PYTHON) init_db/generate_csv.py

eval-setup:
	$(PYTHON) -m tests.evaluation.create_dataset

eval-run:
	$(PYTHON) -m tests.evaluation.run_evaluation

c ?= 40

stress:
	$(PYTHON) -m tests.stress_test --concurrency $(c)
