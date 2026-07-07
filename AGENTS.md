# AGENTS.md — ExpenseTracker Backend

## Project Overview

ExpenseTracker is a Django REST API for personal expense tracking with AI assistant integration. The backend provides dual authentication (session + JWT via HTTP-only cookies), supports MySQL/SQLite databases, and is containerized with Docker, Nginx, and Gunicorn. The API integrates with the Groq LLM for intelligent expense management assistance.

---

## Tech Stack

**Backend**
- Django 5.1
- Django REST Framework 3.15
- Python 3.x
- SimplelJWT (Authentication)
- drf-spectacular (OpenAPI)

**Database**
- MySQL 8.4 (production)
- SQLite (development)
- Migrations (7 versions)

**Deployment**
- Docker (multi-stage build)
- Nginx (reverse proxy)
- Gunicorn (WSGI server)
- Docker Compose (dev & production)

**External Services**
- Groq LLM (llama-3.3-70b-versatile) for AI assistant

---

## Architecture

Follow Django MVT (Model-View-Template) with REST principles.

```
api/
├── models.py          # Database models (6 models)
├── serializers.py     # DRF serializers (validation, camelCase aliases)
├── views/             # API views (organized by feature)
│   ├── auth_views.py
│   ├── ai_views.py
│   ├── analytics_views.py
│   ├── general_views.py
├── urls.py            # API routing
├── authentication.py  # Auth utilities & JWT handling
├── middleware.py      # Rate limiting, CORS
├── utils.py           # Helper functions
```

**Business Logic Rules**
- Keep views thin: validate input, call serializers, return responses
- Use serializers for validation and data transformation
- Place complex logic in utility functions or custom managers
- Avoid duplicate queries with `.select_related()` and `.prefetch_related()`

---

## Coding Standards

**Always**
- Use async views sparingly (celery for async tasks)
- Use `select_related()` for ForeignKey/OneToOne
- Use `prefetch_related()` for reverse ForeignKey/M2M
- Write docstrings for views and models
- Keep functions focused and small
- Use descriptive variable names
- Apply early returns
- Validate all user input in serializers

**Never**
- Store sensitive data in response bodies (use HttpOnly cookies)
- Hardcode secrets or credentials
- Ignore database errors
- Create N+1 query patterns
- Skip input validation
- Log passwords or tokens

---

## API Standards

**Success Response**
```json
{
  "success": true,
  "message": "Operation completed successfully",
  "data": {},
  "meta": {}
}
```

**Error Response**
```json
{
  "success": false,
  "message": "Validation failed",
  "errors": {}
}
```

**HTTP Status Codes**
- `200` — Success
- `201` — Created
- `400` — Bad Request
- `401` — Unauthorized
- `403` — Forbidden
- `404` — Not Found
- `429` — Rate Limited
- `500` — Server Error

**Endpoints Prefix:** `/api/v1/`

---

## Authentication

**Dual System**
- **Session Auth** — For template-rendered pages
- **JWT Auth** — For API requests via HTTP-only cookies

**Token Management**
- Access token in HttpOnly cookie
- Refresh token in HttpOnly cookie (separate)
- Tokens rotated on refresh endpoint
- Blacklist revoked tokens on logout

**Security**
- CSRF protection enabled
- Never store tokens in localStorage
- HttpOnly + Secure flags on cookies
- Token blacklist on authentication

---

## Database Rules

**Models (6 total)**
- `Category` — user, name, icon, color, monthly_budget (unique per user+name)
- `Expense` — user, title, amount, category, payment_method, receipt_image, expense_date, recurring fields, tags
- `Budget` — user, month, year, total_monthly_budget, daily/weekly/yearly_budget, warning_threshold
- `Report` — user, type, dates, format (pdf/csv), totals
- `UserSettings` — OneToOne with user, theme, sidebar_collapsed, compact_mode, animations, currency

**Always**
- Use Django ORM (avoid raw SQL)
- Index frequently queried fields
- Use `select_related()` and `prefetch_related()`
- Paginate large collections (DRF pagination)
- Apply database constraints at model level
- Add `created_at` and `updated_at` timestamps

**Avoid**
- N+1 queries
- Full table scans
- Missing indexes on foreign keys

---

## Security

**Input Validation**
- Validate all user input in serializers
- Sanitize file uploads (receipts)
- Use Django validators for common patterns

**Password Security**
- Hash with Django's `make_password()`
- Enforce strong password policies
- Implement rate limiting on auth endpoints

**Secrets Management**
- Use environment variables (never hardcode)
- Store in `.env` (gitignored)
- Never log passwords, tokens, or API keys

**CORS & CSRF**
- Configure CORS headers for frontend origins
- CSRF protection on session auth endpoints

---

## Error Handling

**Every Endpoint Should**
- Catch exceptions and log appropriately
- Return consistent error responses
- Include user-friendly error messages
- Provide error details for debugging (dev only)
- Handle validation errors gracefully

**Error Logging**
- Log unexpected errors with full traceback
- Include request context (user, endpoint, method)
- Never log sensitive data

---

## Logging

**Structured Logging**
- Use Python `logging` module
- Log at INFO, WARNING, ERROR levels
- Include request ID, user, endpoint, execution time

**Never Log**
- Passwords or authentication tokens
- Full request/response bodies with sensitive data
- Personal information (PII)

---

## Rate Limiting

**Custom Middleware**
- Global: 200 requests/minute
- Auth endpoints: 10 requests/minute
- Block duration: 5 minutes on exceed
- Response: `429 Too Many Requests`

---

## Testing

**Test Coverage (10 test files)**
- `test_auth.py` — Authentication, JWT, registration
- `test_expenses.py` — CRUD, filters, recurring
- `test_categories.py` — Category management
- `test_budget.py` — Budget setting, warnings
- `test_reports.py` — Report generation
- `test_analytics.py` — KPIs, charts
- `test_ai.py` — AI assistant integration
- `test_health_and_models.py` — Health check, model validation
- `base.py` — Test utilities and fixtures

**Consider**
- Invalid input (wrong types, negative values)
- Missing required fields
- Permission checks (user isolation)
- Edge cases (recurring dates, boundary conditions)
- Performance (query counts)

---

## Code Generation Rules

When writing code:

1. **Explain the approach** — Clarify the design and reasoning
2. **Generate complete code** — Production-ready, no placeholders
3. **Handle edge cases** — Null checks, boundary conditions, errors
4. **Include validation** — Serializers, model validators, permissions
5. **Avoid complexity** — Keep it simple, readable, maintainable
6. **Keep modular** — Reusable, testable components

---

## Refactoring Rules

When refactoring:
- **Preserve behavior** — All tests pass, no breaking changes
- **Improve readability** — Clear naming, reduced nesting
- **Reduce duplication** — Extract common logic
- **Improve performance** — Only with measurable improvement (profiling)

---

## Output Quality

Generate code that is:
- **Readable** — Clear intent, good naming, proper comments
- **Maintainable** — Modular, DRY, testable
- **Secure** — Input validation, no hardcoded secrets
- **Scalable** — Efficient queries, proper pagination
- **Production-Ready** — Error handling, logging, tests
