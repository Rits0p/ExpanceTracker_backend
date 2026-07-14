# AGENTS.md - ExpenseTracker Backend

## Purpose

ExpenseTracker is a Django 5 application for personal expense management. It serves both server-rendered pages and a Django REST Framework API, with cookie-based JWT authentication, expense analytics and reports, recurring-expense generation, and a Groq-powered assistant.

## Technology and local conventions

- Python 3.12; Django 5.1+; Django REST Framework 3.15+.
- SQLite is the local default. Docker deployments use MySQL 8.4 when `USE_MYSQL=True`.
- Static assets are served with WhiteNoise; production uses Gunicorn behind Nginx.
- Ruff is configured in `pyproject.toml` with a 120-character line limit. Bandit configuration is also there.
- Third-party integrations include SimpleJWT, drf-spectacular, django-filter, Pillow, ReportLab, and Groq's OpenAI-compatible chat endpoint.

## Repository layout

```text
api/
  models.py                    # Domain models
  serializers.py               # DRF serializers and camelCase API mapping
  services.py                  # Recurring-expense business logic
  authentication.py            # JWT cookie helpers and authentication class
  middleware.py                # CSRF cookie and per-IP rate limiting
  signals.py                   # Defaults created for newly registered users
  urls.py                      # /api/v1/ routes
  chats_urls.py                # Chat routes, mounted at /api/chats/ and /api/v1/chats/
  views/                       # Auth, expenses, analytics, reports, AI, chats, recurring expenses
  management/commands/         # seed_data and generate_recurring_expenses
  tests/                       # API and model tests
config/
  settings.py                  # App, security, database, REST, JWT, and API-doc settings
  urls.py                      # Root HTML, auth, health, docs, and API routes
templates/                     # Server-rendered pages and recurring-expense partials
static/                        # JavaScript, CSS, images, and recurring-expense assets
docker/                         # Entrypoint, Nginx, and MySQL setup
```

## Domain model

The application currently has nine core API models:

- `Category` - per-user categories, visual metadata, and monthly budget.
- `RecurringExpense` - a category-linked recurring template with scheduling state.
- `Expense` - a per-user transaction, optionally linked to a recurring template.
- `Budget` - a per-user monthly budget with daily, weekly, yearly, and warning values.
- `Report` - generated CSV/PDF report metadata and totals.
- `UserSettings` - one-to-one appearance, currency, and notification preferences.
- `AIChatMessage` - legacy persisted AI prompt/response history.
- `Chat` and `Message` - current persisted conversation and message history.

`signals.py` creates settings, Food/Travel/Other categories, and a zero-value current-month budget for new users (except during tests). Preserve this behavior unless the task explicitly changes onboarding defaults.

## Application architecture

- Keep views focused on request parsing, authorization, serializer validation, and response construction.
- Put reusable or transactional domain work in `api/services.py` or `api/utils.py`.
- Use serializers for API validation and transformations. Public API field names are generally camelCase; do not casually change an existing response shape.
- `ApiResponse` in `api/utils.py` is the standard response wrapper. Preserve its `success`, `message`, `data`, pagination, and error conventions.
- Scope every user-owned queryset to `request.user`. This applies to expenses, categories, budgets, reports, recurring expenses, chats, and messages.
- Use `select_related()` or `prefetch_related()` when dereferencing related records in list endpoints.

## API and routes

- REST routes are mounted below `/api/v1/`; route trailing slashes are intentionally inconsistent, so preserve the existing path style when extending a route group.
- Authentication routes live in `config/urls.py` under `/api/v1/auth/`.
- Main resource groups: expenses, categories, settings, budget, reports, analytics, AI assistant, and `recurring-expenses/` (a DRF ViewSet).
- Chats are available at both `/api/chats/` and `/api/v1/chats/` for compatibility.
- API schema and documentation: `/api/schema/`, `/api/docs/swagger/`, and `/api/docs/redoc/`.
- The unauthenticated health check is `/health`.

Use the established HTTP semantics: 200 for successful reads/updates, 201 for creation, 400 for validation/input errors, 401/403 for authentication/permission errors, 404 for missing scoped resources, 409 for conflicts such as duplicate categories, 429 for rate limiting, and 5xx only for unexpected service failures.

## Authentication and security

- The default API authentication class is `CookieJWTAuthentication`, which reads the `access_token` HttpOnly cookie and falls back to a Bearer header.
- JWT access tokens live for 15 minutes; refresh tokens live for 7 days, rotate on refresh, and are blacklisted after rotation. Use `set_token_cookies()` and `clear_token_cookies()` rather than hand-rolling cookie behavior.
- Session authentication remains enabled for Django admin and template-rendered pages. Protected HTML pages use `login_required`.
- CSRF cookies are issued by custom middleware. Browser mutations must remain CSRF-compatible.
- Never expose secrets, passwords, token values, user PII, or complete sensitive request bodies in responses or logs.
- Read secrets and deployment settings from environment variables. Key groups include `DJANGO_SECRET_KEY`, database settings, CORS origins, and `GROQ_*`; never commit populated `.env` files.
- Receipt uploads are limited by Django's configured 5 MiB in-memory upload threshold. Validate uploaded data via serializers/parsers before use.

## Rate limiting and errors

- `RateLimitMiddleware` applies per-IP limits: 200 requests/minute generally and 10/minute for `/api/v1/auth/`, blocking for five minutes when exceeded. `/api/v1/auth/me` is exempt.
- The REST framework also applies its configured anonymous throttle (default `100/hour`). Do not bypass either limiter without an explicit product requirement.
- Use the custom DRF exception handler and `ApiResponse` helpers for consistent failures. Log unexpected exceptions with context but without sensitive values.

## Recurring expenses

- `RecurringExpense` is the schedule/template; generated `Expense` rows link back through `recurring_expense`.
- `generate_recurring_expenses()` in `api/services.py` runs transactionally, only creates due active records, prevents duplicates for a due date, advances the next due date, and deactivates expired schedules.
- The management command is `python manage.py generate_recurring_expenses`, optionally with `--user <id>`. A scheduler may run it daily; keep it safe to run repeatedly.
- Supported recurrence frequencies are daily, weekly, monthly, quarterly, and yearly. Changes must keep serializer validation, scheduling calculations, analytics, and tests aligned.

## AI assistant and chats

- The assistant uses the Groq OpenAI-compatible endpoint configured with `GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_API_BASE_URL`, `GROQ_TEMPERATURE`, and `GROQ_MAX_TOKENS`.
- `ai_views.py` builds user-scoped financial context, parses the model's structured response, and executes an allowlisted set of CRUD intents. Keep model output untrusted: validate all parsed fields and preserve user scoping before writes.
- `chat_views.py` stores user/assistant messages in `Chat` and `Message`, updates `last_message`, and reuses the assistant helpers. Do not leak messages between users or chats.
- Tests mock the external Groq request. Do not require a live API key for test execution.

## Database and migrations

- Use the Django ORM; do not add raw SQL unless there is a reviewed, documented need.
- Add migrations for every schema change. Do not edit applied migration files or delete historical migrations.
- Preserve model-level constraints, indexes, and user isolation. Model queries should avoid N+1 access patterns.
- Monetary fields are `DecimalField`s. Keep calculations in `Decimal` until the API serialization boundary.

## Testing and quality checks

Run commands from this directory:

```bash
python manage.py test
ruff check .
ruff format --check .
bandit -c pyproject.toml -r .
python manage.py spectacular --file schema.yml
```

Target focused tests during development, for example:

```bash
python manage.py test api.tests.test_recurring_expenses
python manage.py test api.tests.test_auth
```

When changing an endpoint, cover success, invalid input, ownership/permission boundaries, and relevant empty or date-boundary cases. For query-heavy endpoints, also watch query counts and relation loading.

## Docker and operations

- Production compose runs MySQL, the Django/Gunicorn web service, and Nginx. Development compose runs MySQL and Django's auto-reloading server.
- Common commands: `make build`, `make up`, `make down`, `make dev`, `make migrate`, `make test`, `make lint`, and `make format`.
- `make clean` removes Docker containers, volumes, and images; never run it unless the user explicitly requests destructive cleanup.
- Docker's entrypoint runs migrations and collects static files. Keep deployment changes compatible with this lifecycle.

## Change checklist

Before handing off a change:

1. Confirm request/response compatibility, including existing camelCase aliases and pagination shapes.
2. Enforce authentication and per-user ownership on every affected read and mutation.
3. Validate inputs in serializers or forms; use transactions for multi-step writes.
4. Add or update migrations and tests when data behavior changes.
5. Run the smallest relevant test suite and the appropriate lint/format check.
6. Keep secrets out of code, output, fixtures, and logs.
