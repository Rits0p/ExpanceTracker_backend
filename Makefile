.PHONY: docs build up down dev logs shell migrate createsuperuser ps clean

# ── Documentation ─────────────────────────────────────────────────────────────
docs:
	python manage.py spectacular --color --file schema.yml

# ── Docker: Production ────────────────────────────────────────────────────────
build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

# ── Docker: Development (hot-reload) ─────────────────────────────────────────
dev:
	docker compose -f docker-compose.dev.yml up

dev-build:
	docker compose -f docker-compose.dev.yml up --build

dev-down:
	docker compose -f docker-compose.dev.yml down

# ── Helpers ───────────────────────────────────────────────────────────────────
logs:
	docker compose logs -f web

logs-db:
	docker compose logs -f db

ps:
	docker compose ps

# Open a shell inside the running web container
shell:
	docker compose exec web bash

# Run Django migrations inside the container
migrate:
	docker compose exec web python manage.py migrate

# Create a Django superuser inside the container
createsuperuser:
	docker compose exec web python manage.py createsuperuser

# Remove all containers, volumes, and images for a clean slate
clean:
	docker compose down -v --rmi local
	docker compose -f docker-compose.dev.yml down -v --rmi local

# ── Local Development Tools ───────────────────────────────────────────────────
test:
	python manage.py test

lint:
	ruff check .

format:
	ruff format .

security-check:
	bandit -c pyproject.toml -r .
