# Push Notification Events — ExpenseTracker Backend

## Overview

This document lists all events that should trigger push notifications for users, categorized by priority. These notifications help users stay informed about their financial activities, security events, and spending patterns.

---

## CRITICAL Priority (Immediate — seconds to 1 minute)

These events represent security threats, financial anomalies, or system failures requiring instant user awareness.

| # | Event Name | Trigger Condition | Push | In-App | Email |
|---|-----------|-------------------|------|--------|-------|
| 1 | `budget_exceeded` | After any expense creation, aggregate monthly spending exceeds `Budget.total_monthly_budget` (100%) | Yes | Yes | -- |
| 2 | `recurring_generation_failed` | `generate_recurring_expenses()` encounters exception processing a `RecurringExpense` template (DB error, category not found, transaction rollback) | Yes | Yes | -- |
| 3 | `auth_new_device_login` | Successful `JWTLoginView.post()` or `login_view()` from unrecognized IP address (compared against previously known IPs for user) | Yes | -- | Yes |
| 4 | `auth_password_changed` | Successful `JWTChangePasswordView.post()` or `password_reset_view()` after `user.set_password(); user.save()` | Yes | -- | Yes |
| 5 | `auth_rate_limited` | `RateLimitMiddleware._is_rate_limited()` blocks IP exceeding 10 requests/minute on auth endpoints (`/api/v1/auth/*`) for 5 minutes | Yes | -- | Yes |
| 6 | `auth_account_disabled` | `JWTLoginView.post()` detects `authenticated_user.is_active is False` (403 response) | Yes | -- | Yes |

---

## IMPORTANT Priority (Within minutes)

These events represent meaningful financial decisions or conditions that the user should be aware of promptly, but do not constitute emergencies.

| # | Event Name | Trigger Condition | Push | In-App | Email |
|---|-----------|-------------------|------|--------|-------|
| 7 | `budget_warning` | After expense creation, monthly spending reaches or exceeds `Budget.warning_threshold` (default 80%). Fire once per crossing only | Yes | Yes | -- |
| 8 | `category_budget_exceeded` | After expense creation, spending within specific category exceeds `Category.monthly_budget` | Yes | Yes | -- |
| 9 | `large_expense_created` | Expense created with `amount` exceeding configurable threshold (e.g., 20% of monthly budget or absolute dollar amount) | Yes | Yes | -- |
| 10 | `recurring_expense_generated` | `generate_recurring_expenses()` successfully creates `Expense` from `RecurringExpense` template. Gated by `UserSettings.recurring_reminders` preference | Opt-in | Yes | -- |
| 11 | `recurring_expense_overdue` | `get_recurring_dashboard_stats()` identifies overdue payments where `next_due_date < today` and no `Expense` generated for that date | Yes | Yes | -- |
| 12 | `recurring_expense_upcoming` | `RecurringExpense` with `is_active=True` has `next_due_date` within next 1-3 days. Gated by `UserSettings.recurring_reminders` preference | Opt-in | Yes | -- |
| 13 | `recurring_expense_ended` | `generate_recurring_expenses()` deactivates `RecurringExpense` (`is_active=False`) when `end_date` is reached or exceeded | Yes | Yes | -- |
| 14 | `report_generated` | `ReportCSVView.post()` or `ReportPDFView.post()` successfully creates `Report` record | -- | Yes | -- |
| 15 | `ai_crud_performed` | AI assistant `_execute_crud()` returns `ok=True` with `crud_type` in {created, updated, deleted} for any intent (expenses, budgets, categories) | -- | Yes | -- |
| 16 | `auth_token_refresh_failed` | `JWTRefreshView.post()` raises `TokenError` when `RefreshToken(refresh_token)` is invalid or expired | Yes | Yes | -- |
| 17 | `new_month_no_budget` | Start of new calendar month with no `Budget` record for user in current month/year | Yes | Yes | -- |
| 18 | `receipt_uploaded` | `ExpenseReceiptUploadView.post()` successfully saves `receipt_image` to `Expense` record | -- | Yes | -- |

---

## INFORMATIONAL Priority (Daily digest / Weekly / Monthly)

These events summarize patterns, provide insights, or deliver scheduled content that the user benefits from but does not need immediately.

| # | Event Name | Trigger Condition | Push | In-App | Email |
|---|-----------|-------------------|------|--------|-------|
| 19 | `weekly_summary` | Scheduled weekly (Sunday/Monday). Aggregates past 7 days: total, growth %, transaction count, daily trend. Gated by `UserSettings.weekly_report` preference | Yes | Yes | Yes |
| 20 | `monthly_summary` | Scheduled monthly (1st). Compiles: total expenses, top category, budget usage, savings rate, daily average, month-over-month growth, highest expense | Yes | Yes | Yes |
| 21 | `ai_insight` | AI assistant detects notable pattern (spending spike, unusual category distribution, high daily average streak) via `_build_user_context()` analysis | -- | Yes | -- |
| 22 | `recurring_monthly_summary` | Scheduled monthly (1st). Shows: total recurring count, monthly recurring cost, upcoming payments list | -- | Yes | Yes |
| 23 | `budget_vs_actual` | Scheduled monthly (1st). Compares `Budget.total_monthly_budget` against actual `Expense` totals with variance amount | -- | Yes | Yes |
| 24 | `category_breakdown` | Scheduled monthly (last day or 1st). Shows percentage and dollar breakdown by category with category-level budget usage | -- | Yes | Yes |
| 25 | `spending_trend_alert` | Scheduled weekly. Current month projected spending exceeds previous month by > 20% | Yes | Yes | -- |
| 26 | `daily_spending_tally` | Scheduled daily (end of day). Sums all expenses for current day with transaction count | -- | Yes | -- |

---

## Summary Table

| # | Event Name | Trigger Source | Priority | Push | In-App | Email |
|---|-----------|---------------|----------|------|--------|-------|
| 1 | `budget_exceeded` | Expense creation | Critical | Yes | Yes | -- |
| 2 | `recurring_generation_failed` | Background task | Critical | Yes | Yes | -- |
| 3 | `auth_new_device_login` | Login endpoint | Critical | Yes | -- | Yes |
| 4 | `auth_password_changed` | Password endpoints | Critical | Yes | -- | Yes |
| 5 | `auth_rate_limited` | Rate middleware | Critical | Yes | -- | Yes |
| 6 | `auth_account_disabled` | Login endpoint | Critical | Yes | -- | Yes |
| 7 | `budget_warning` | Expense creation | Important | Yes | Yes | -- |
| 8 | `category_budget_exceeded` | Expense creation | Important | Yes | Yes | -- |
| 9 | `large_expense_created` | Expense creation | Important | Yes | Yes | -- |
| 10 | `recurring_expense_generated` | Background task | Important | Opt-in | Yes | -- |
| 11 | `recurring_expense_overdue` | Background task | Important | Yes | Yes | -- |
| 12 | `recurring_expense_upcoming` | Scheduled check | Important | Opt-in | Yes | -- |
| 13 | `recurring_expense_ended` | Background task | Important | Yes | Yes | -- |
| 14 | `report_generated` | Report endpoints | Important | -- | Yes | -- |
| 15 | `ai_crud_performed` | AI assistant | Important | -- | Yes | -- |
| 16 | `auth_token_refresh_failed` | Token refresh | Important | Yes | Yes | -- |
| 17 | `new_month_no_budget` | Scheduled task | Important | Yes | Yes | -- |
| 18 | `receipt_uploaded` | Receipt endpoint | Important | -- | Yes | -- |
| 19 | `weekly_summary` | Scheduled (weekly) | Info | Yes | Yes | Yes |
| 20 | `monthly_summary` | Scheduled (monthly) | Info | Yes | Yes | Yes |
| 21 | `ai_insight` | AI analysis | Info | -- | Yes | -- |
| 22 | `recurring_monthly_summary` | Scheduled (monthly) | Info | -- | Yes | Yes |
| 23 | `budget_vs_actual` | Scheduled (monthly) | Info | -- | Yes | Yes |
| 24 | `category_breakdown` | Scheduled (monthly) | Info | -- | Yes | Yes |
| 25 | `spending_trend_alert` | Scheduled (weekly) | Info | Yes | Yes | -- |
| 26 | `daily_spending_tally` | Scheduled (daily) | Info | -- | Yes | -- |

---

## Key Integration Points

These are the locations in the codebase where notification dispatch logic should be inserted:

### Expense Creation
- **`api/views/__init__.py`** — `ExpenseListCreateView.post()` after `serializer.save(user=request.user)`
- **`api/services.py`** — `generate_recurring_expenses()` after `Expense.objects.create()` inside the loop

### Authentication
- **`api/views/auth_views.py`** — `JWTLoginView.post()` after successful authentication
- **`api/views/auth_views.py`** — `JWTChangePasswordView.post()` after `user.save()`
- **`api/middleware.py`** — `RateLimitMiddleware._is_rate_limited()` when `block_key` is set

### Budget & Analytics
- **`api/views/general_views.py`** — `BudgetWarningsView.get()` for warning threshold logic reference

### AI Assistant
- **`api/views/ai_views.py`** — `_execute_crud()` after all CRUD intent paths

### Reports
- **`api/views/general_views.py`** — `ReportCSVView.post()` and `ReportPDFView.post()` after `Report.objects.create()`

### User Settings
- **`api/models.py`** — `UserSettings` notification preferences (`budget_alerts`, `weekly_report`, `recurring_reminders`, `auto_backup`)

---

## Required Infrastructure

### Existing
- `UserSettings` notification preferences (not yet wired to dispatch)
- `generate_recurring_expenses` management command (pattern for scheduled work)

### Required
- **Notification Model** — Store notification records (type, message, read status, timestamps)
- **Notification Service** — Dispatch logic for push, in-app, and email channels
- **Celery Beat** — Scheduled tasks for events 17, 19-26
- **WebSocket/Push Service** — Real-time delivery for critical and important events
- **Email Service** — Transactional email for security alerts and digests

---

## User Preference Gating

All notifications should respect these `UserSettings` flags before sending:

| Setting | Default | Controls |
|---------|---------|----------|
| `budget_alerts` | True | Events 1, 7, 8 |
| `weekly_report` | True | Events 19, 20, 25 |
| `recurring_reminders` | False | Events 10, 11, 12, 22 |
| `auto_backup` | False | Future backup notifications |
