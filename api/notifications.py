"""Firebase Cloud Messaging delivery and domain-notification helpers."""

import json
import logging
from decimal import Decimal
from itertools import islice
from pathlib import Path

from django.conf import settings
from django.db import IntegrityError
from django.db.models import Sum
from django.utils import timezone

from .models import Budget, Category, DeviceToken, Expense, NotificationEvent, UserSettings

logger = logging.getLogger(__name__)

FCM_PAYLOAD_MAX_BYTES = 4000
LARGE_EXPENSE_THRESHOLD_RATIO = 0.2  # 20% of monthly budget

PREFERENCE_BY_EVENT = {
    "budget_warning": "budget_alerts",
    "budget_exceeded": "budget_alerts",
    "category_budget_exceeded": "budget_alerts",
    "large_expense_created": "budget_alerts",
    "auth_new_device_login": "budget_alerts",
    "auth_password_changed": "budget_alerts",
    "auth_rate_limited": "budget_alerts",
    "auth_account_disabled": "budget_alerts",
    "account_created": "budget_alerts",
    "recurring_expense_generated": "recurring_reminders",
    "recurring_expense_ended": "recurring_reminders",
    "weekly_summary": "weekly_report",
    "monthly_summary": "weekly_report",
    "spending_trend_alert": "weekly_report",
    "daily_spending_tally": "weekly_report",
    "report_generated": "weekly_report",
    "ai_crud_performed": "weekly_report",
    "category_created": "weekly_report",
    "category_deleted": "weekly_report",
    "budget_set": "weekly_report",
    "budget_deleted": "weekly_report",
}


def _chunks(values, size):
    iterator = iter(values)
    while chunk := list(islice(iterator, size)):
        yield chunk


def _get_messaging():
    """Initialize Firebase using a file or inline JSON credential."""
    import firebase_admin
    from firebase_admin import credentials, messaging

    credential_source = None
    credential_path = getattr(settings, "FIREBASE_SERVICE_ACCOUNT_PATH", "")
    credential_json = getattr(settings, "FIREBASE_SERVICE_ACCOUNT_JSON", "")

    if credential_json:
        try:
            credential_source = json.loads(credential_json)
        except json.JSONDecodeError:
            logger.warning("FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON.")
    if not credential_source and credential_path:
        path = Path(credential_path)
        if not path.is_absolute():
            path = settings.BASE_DIR / path
        if path.is_file():
            try:
                with open(str(path)) as f:
                    credential_source = json.load(f)
            except (json.JSONDecodeError, OSError):
                logger.warning("Firebase service-account file is not readable.")
        else:
            logger.warning("Firebase service-account file does not exist at %s.", path)
    if not credential_source:
        return None

    try:
        try:
            firebase_admin.get_app()
        except ValueError:
            firebase_admin.initialize_app(credentials.Certificate(cert=credential_source))
        return messaging
    except Exception:
        logger.exception("Firebase Cloud Messaging initialization failed.")
        return None


def send_push_notification(user, *, event_type, title, body, url="/", data=None):
    """Send one non-sensitive notification to all of a user's current devices."""
    logger.info("send_push_notification: user=%s event=%s title=%s", user.id, event_type, title)
    preference = PREFERENCE_BY_EVENT.get(event_type)
    user_settings, _ = UserSettings.objects.get_or_create(user=user)
    if preference and not getattr(user_settings, preference):
        logger.info("Skipped notification for user=%s: preference_disabled (%s)", user.id, preference)
        return {"sent": 0, "skipped": "preference_disabled"}

    messaging = _get_messaging()
    if messaging is None:
        return {"sent": 0, "skipped": "firebase_not_configured"}

    devices = list(DeviceToken.objects.filter(user=user).values("token", "id"))
    if not devices:
        return {"sent": 0, "skipped": "no_devices"}

    tokens = [d["token"] for d in devices]
    device_ids = [d["id"] for d in devices]

    payload = {"eventType": event_type, "url": url}
    payload.update({str(key): str(value) for key, value in (data or {}).items()})
    payload_bytes = len(json.dumps(payload).encode("utf-8"))
    if payload_bytes > FCM_PAYLOAD_MAX_BYTES:
        logger.warning(
            "FCM payload %d bytes exceeds %d limit for user id=%s; truncating.",
            payload_bytes, FCM_PAYLOAD_MAX_BYTES, user.id,
        )
        payload = {k: v for k, v in list(payload.items())[:5]}
    sent = 0
    invalid_tokens = []
    seen_ids = []

    for token_batch in _chunks(tokens, 500):
        message_kwargs = {
            "tokens": token_batch,
            "notification": messaging.Notification(title=title, body=body),
            "data": payload,
        }
        if url.startswith("https://"):
            message_kwargs["webpush"] = messaging.WebpushConfig(
                fcm_options=messaging.WebpushFCMOptions(link=url),
            )
        message = messaging.MulticastMessage(**message_kwargs)
        try:
            result = messaging.send_each_for_multicast(message)
        except Exception as e:
            logger.exception("FCM delivery failed for user id=%s: %s", user.id, str(e))
            continue

        sent += result.success_count
        for token, response in zip(token_batch, result.responses):
            if response.success:
                continue
            error_code = getattr(response.exception, "code", "") if response.exception else ""
            normalized_code = str(error_code).lower().replace("_", "-").replace(" ", "-")
            if normalized_code in {
                "registration-token-not-registered",
                "invalid-argument",
                "not-found",
                "unregistered",
            }:
                invalid_tokens.append(token)
                logger.warning(
                    "FCM token invalid/unregistered for user id=%s. Removing token. Error: %s",
                    user.id,
                    response.exception or error_code,
                )
            else:
                logger.warning(
                    "FCM delivery failed for user id=%s: %s (exception: %s)",
                    user.id,
                    error_code or "unknown",
                    response.exception,
                )

    invalid_set = set(invalid_tokens)
    for token, did in zip(tokens, device_ids):
        if token not in invalid_set:
            seen_ids.append(did)

    if seen_ids:
        DeviceToken.objects.filter(id__in=seen_ids).update(last_seen_at=timezone.now())

    if invalid_tokens:
        DeviceToken.objects.filter(token__in=invalid_tokens).delete()
    return {"sent": sent, "removed": len(invalid_tokens)}


def send_once(user, *, event_type, deduplication_key, title, body, url="/", data=None):
    """Deliver an event once per user and deduplication key."""
    try:
        NotificationEvent.objects.create(
            user=user,
            event_type=event_type,
            deduplication_key=deduplication_key,
            payload=data or {},
        )
    except IntegrityError:
        return {"sent": 0, "skipped": "already_sent"}
    return send_push_notification(
        user,
        event_type=event_type,
        title=title,
        body=body,
        url=url,
        data=data,
    )


def _get_currency_symbol(user):
    user_settings = UserSettings.objects.filter(user=user).first()
    return user_settings.currency_symbol if user_settings else "$"


def notify_budget_status(user, expense):
    """Notify when spending crosses any budget threshold (monthly, daily, weekly, yearly)."""
    expense_date = timezone.localtime(expense.expense_date)
    budget = Budget.objects.filter(
        user=user,
        month=expense_date.month,
        year=expense_date.year,
    ).first()
    if not budget or budget.total_monthly_budget <= 0:
        return {"sent": 0, "skipped": "no_budget"}

    sym = _get_currency_symbol(user)
    today = expense_date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_key = f"{expense_date.year}-{expense_date.month:02d}-{expense_date.day:02d}"

    from datetime import timedelta

    # ── Daily budget check ──
    if budget.daily_budget > 0:
        daily_total = user.expenses.filter(expense_date__gte=today).aggregate(
            total=Sum("amount")
        )["total"] or 0
        if daily_total >= budget.daily_budget:
            return send_once(
                user,
                event_type="budget_exceeded",
                deduplication_key=f"{day_key}-daily",
                title="Daily budget exceeded",
                body=f"Your daily budget of {sym}{budget.daily_budget} has been exceeded.",
                url="/budget/",
                data={"type": "daily", "spent": float(daily_total), "budget": float(budget.daily_budget)},
            )
        daily_usage = (daily_total / budget.daily_budget) * 100
        if daily_usage >= budget.warning_threshold:
            return send_once(
                user,
                event_type="budget_warning",
                deduplication_key=f"{day_key}-daily-warning",
                title="Daily budget warning",
                body=f"Daily spending is at {daily_usage:.0f}% of budget ({sym}{daily_total:.2f}).",
                url="/budget/",
                data={"type": "daily", "spent": float(daily_total), "budget": float(budget.daily_budget)},
            )

    # ── Weekly budget check ──
    if budget.weekly_budget > 0:
        week_start = today - timedelta(days=today.weekday())
        week_total = user.expenses.filter(expense_date__gte=week_start).aggregate(
            total=Sum("amount")
        )["total"] or 0
        week_key = f"{week_start.isoformat()}"
        if week_total >= budget.weekly_budget:
            return send_once(
                user,
                event_type="budget_exceeded",
                deduplication_key=f"{week_key}-weekly",
                title="Weekly budget exceeded",
                body=f"Your weekly budget of {sym}{budget.weekly_budget} has been exceeded.",
                url="/budget/",
                data={"type": "weekly", "spent": float(week_total), "budget": float(budget.weekly_budget)},
            )
        week_usage = (week_total / budget.weekly_budget) * 100
        if week_usage >= budget.warning_threshold:
            return send_once(
                user,
                event_type="budget_warning",
                deduplication_key=f"{week_key}-weekly-warning",
                title="Weekly budget warning",
                body=f"Weekly spending is at {week_usage:.0f}% of budget ({sym}{week_total:.2f}).",
                url="/budget/",
                data={"type": "weekly", "spent": float(week_total), "budget": float(budget.weekly_budget)},
            )

    # ── Yearly budget check ──
    if budget.yearly_budget > 0:
        year_start = today.replace(month=1, day=1)
        year_total = user.expenses.filter(expense_date__gte=year_start).aggregate(
            total=Sum("amount")
        )["total"] or 0
        year_key = f"{year_start.year}"
        if year_total >= budget.yearly_budget:
            return send_once(
                user,
                event_type="budget_exceeded",
                deduplication_key=f"{year_key}-yearly",
                title="Yearly budget exceeded",
                body=f"Your yearly budget of {sym}{budget.yearly_budget} has been exceeded.",
                url="/budget/",
                data={"type": "yearly", "spent": float(year_total), "budget": float(budget.yearly_budget)},
            )
        year_usage = (year_total / budget.yearly_budget) * 100
        if year_usage >= budget.warning_threshold:
            return send_once(
                user,
                event_type="budget_warning",
                deduplication_key=f"{year_key}-yearly-warning",
                title="Yearly budget warning",
                body=f"Yearly spending is at {year_usage:.0f}% of budget ({sym}{year_total:.2f}).",
                url="/budget/",
                data={"type": "yearly", "spent": float(year_total), "budget": float(budget.yearly_budget)},
            )

    # ── Monthly budget check ──
    month_start = today.replace(day=1)
    total = user.expenses.filter(expense_date__gte=month_start).aggregate(total=Sum("amount"))["total"] or 0
    usage = (total / budget.total_monthly_budget) * 100
    if usage >= 100:
        return send_once(
            user,
            event_type="budget_exceeded",
            deduplication_key=day_key,
            title="Monthly budget exceeded",
            body=f"Your monthly budget of {sym}{budget.total_monthly_budget} has been exceeded.",
            url="/budget/",
            data={"type": "monthly", "spent": float(total), "budget": float(budget.total_monthly_budget)},
        )
    if usage >= budget.warning_threshold:
        return send_once(
            user,
            event_type="budget_warning",
            deduplication_key=day_key,
            title="Budget warning",
            body=f"Monthly spending is at {usage:.0f}% of budget ({sym}{total:.2f}).",
            url="/budget/",
            data={"type": "monthly", "spent": float(total), "budget": float(budget.total_monthly_budget)},
        )
    return {"sent": 0, "skipped": "below_threshold"}


def notify_category_budget_exceeded(user, expense):
    """Notify if expense pushes category spending over its monthly budget."""
    expense_date = timezone.localtime(expense.expense_date)
    month_start = expense_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    cat_obj = Category.objects.filter(user=user, name=expense.category).first()
    if not cat_obj or cat_obj.monthly_budget <= 0:
        return {"sent": 0, "skipped": "no_category_budget"}
    total = Expense.objects.filter(
        user=user, category=expense.category, expense_date__gte=month_start
    ).aggregate(total=Sum("amount"))["total"] or 0
    if total <= cat_obj.monthly_budget:
        return {"sent": 0, "skipped": "under_category_budget"}
    day_key = f"{expense_date.year}-{expense_date.month:02d}-{expense_date.day:02d}"
    sym = _get_currency_symbol(user)
    cat_key = f"{day_key}-{expense.category}"
    return send_once(
        user,
        event_type="category_budget_exceeded",
        deduplication_key=cat_key,
        title="Category budget exceeded",
        body=f"Your monthly budget for \"{expense.category}\" ({sym}{total:.2f}) has been exceeded.",
        url="/budget/",
        data={"category": expense.category, "total": round(float(total), 2)},
    )


def notify_large_expense(user, expense):
    """Notify if expense amount exceeds a large threshold relative to monthly budget."""
    now = timezone.localtime()
    budget = Budget.objects.filter(
        user=user, month=now.month, year=now.year
    ).first()
    threshold = 0
    if budget and budget.total_monthly_budget > 0:
        threshold = budget.total_monthly_budget * Decimal(str(LARGE_EXPENSE_THRESHOLD_RATIO))
    else:
        threshold = Decimal("500.00")
    if expense.amount >= threshold:
        sym = _get_currency_symbol(user)
        return send_once(
            user,
            event_type="large_expense_created",
            deduplication_key=f"{now.year}-{now.month:02d}-{now.day:02d}-{expense.id}",
            title="Large expense detected",
            body=f"A large expense of {sym}{expense.amount} was added: {expense.title}.",
            url="/expenses/",
            data={"expenseId": expense.id, "amount": float(expense.amount)},
        )
    return {"sent": 0, "skipped": "amount_below_threshold"}


def notify_recurring_expense_ended(user, re):
    """Notify when a recurring expense has ended."""
    return send_push_notification(
        user,
        event_type="recurring_expense_ended",
        title="Recurring expense ended",
        body=f"Your recurring expense \"{re.title}\" has ended.",
        url="/recurring-expenses/",
        data={"recurringExpenseId": re.id},
    )


def notify_auth_event(user, event_type, title, body, url="/"):
    """Send an auth-related notification (login, password change, etc)."""
    return send_once(
        user,
        event_type=event_type,
        deduplication_key=f"{timezone.localtime().strftime('%Y-%m-%d-%H-%M')}",
        title=title,
        body=body,
        url=url,
    )


def notify_report_generated(user, report_type, start_date, end_date):
    """Notify when a report is generated."""
    from datetime import datetime
    if isinstance(start_date, datetime):
        start_str = start_date.strftime("%Y-%m-%d")
    else:
        start_str = str(start_date)
    if isinstance(end_date, datetime):
        end_str = end_date.strftime("%Y-%m-%d")
    else:
        end_str = str(end_date)
    return send_once(
        user,
        event_type="report_generated",
        deduplication_key=f"{start_str}_{end_str}",
        title=f"{report_type.title()} report generated",
        body=f"Your {report_type} report ({start_str} – {end_str}) is ready.",
        url="/reports/",
        data={"reportType": report_type, "startDate": start_str, "endDate": end_str},
    )


def notify_ai_crud_performed(user, crud_type, description):
    """Notify when AI performs a CRUD operation."""
    if crud_type == "none":
        return {"sent": 0, "skipped": "no_crud"}
    import hashlib
    dedup_key = hashlib.sha256((crud_type + description).encode()).hexdigest()
    return send_once(
        user,
        event_type="ai_crud_performed",
        deduplication_key=dedup_key,
        title="AI assistant updated your data",
        body=description,
        url="/ai-assistant/",
        data={"crudType": crud_type},
    )


def notify_category_created(user, cat_name):
    """Notify when a new category is created."""
    return send_push_notification(
        user,
        event_type="category_created",
        title="Category created",
        body=f"Category \"{cat_name}\" has been created.",
        url="/settings/",
    )


def notify_category_deleted(user, cat_name):
    """Notify when a category is deleted."""
    return send_push_notification(
        user,
        event_type="category_deleted",
        title="Category deleted",
        body=f"Category \"{cat_name}\" has been deleted.",
        url="/settings/",
    )


def notify_budget_set(user, month, year, total):
    """Notify when a budget is set or updated."""
    month_names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    sym = _get_currency_symbol(user)
    return send_push_notification(
        user,
        event_type="budget_set",
        title="Budget saved",
        body=f"Budget for {month_names[month]}-{year} set to {sym}{total}.",
        url="/budget/",
    )


def notify_budget_deleted(user, month, year):
    """Notify when a budget is deleted."""
    month_names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return send_push_notification(
        user,
        event_type="budget_deleted",
        title="Budget deleted",
        body=f"Budget for {month_names[month]}-{year} has been removed.",
        url="/budget/",
    )


# Summaries
def generate_daily_spending_tally(user):
    """Send a daily spending tally notification."""
    from datetime import timedelta
    today = timezone.localtime(timezone.now())
    start = today.replace(hour=0, minute=0, second=0, microsecond=0)
    day_key = f"{start.year}-{start.month:02d}-{start.day:02d}"
    total = Expense.objects.filter(
        user=user, expense_date__gte=start
    ).aggregate(total=Sum("amount"))["total"] or 0
    count = Expense.objects.filter(
        user=user, expense_date__gte=start
    ).count()
    if total == 0:
        return {"sent": 0, "skipped": "no_expenses_today"}
    user_settings, _ = UserSettings.objects.get_or_create(user=user)
    sym = user_settings.currency_symbol or "$"
    return send_once(
        user,
        event_type="daily_spending_tally",
        deduplication_key=day_key,
        title="Daily spending tally",
        body=f"Today spent: {sym}{total:.2f} across {count} transaction(s).",
        url="/expenses/",
        data={"total": float(total), "count": count},
    )


def generate_monthly_summary(user):
    """Send a monthly spending summary."""
    now = timezone.localtime(timezone.now())
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    end = (start + timedelta(days=32)).replace(day=1)
    total = Expense.objects.filter(
        user=user, expense_date__gte=start, expense_date__lt=end
    ).aggregate(total=Sum("amount"))["total"] or 0
    count = Expense.objects.filter(
        user=user, expense_date__gte=start, expense_date__lt=end
    ).count()
    category_qs = Expense.objects.filter(
        user=user, expense_date__gte=start, expense_date__lt=end
    ).values("category").annotate(total=Sum("amount")).order_by("-total")
    top_cat = category_qs.first()
    top_cat_name = top_cat["category"] if top_cat else "N/A"
    top_cat_total = top_cat["total"] if top_cat else 0
    user_settings, _ = UserSettings.objects.get_or_create(user=user)
    sym = user_settings.currency_symbol or "$"
    body = f"{sym}{total:.2f} spent across {count} transaction(s). Top category: {top_cat_name} ({sym}{top_cat_total:.0f})."
    return send_push_notification(
        user,
        event_type="monthly_summary",
        title="Monthly spending summary",
        body=body,
        url="/expenses/",
        data={
            "total": float(total),
            "count": count,
            "topCategory": top_cat_name,
            "topCategoryTotal": float(top_cat_total),
        },
    )


def generate_spending_trend_alert(user):
    """Send a spending trend alert if current month projected > previous month by > 20%."""
    now = timezone.localtime(timezone.now())
    m, y = now.month, now.year
    from datetime import timedelta
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    days_passed = now.day
    days_in_month = 30
    cur_total = Expense.objects.filter(
        user=user, expense_date__gte=start
    ).aggregate(total=Sum("amount"))["total"] or 0
    if days_passed == 0:
        return {"sent": 0, "skipped": "first_day"}
    projected = (cur_total / days_passed) * days_in_month
    lm, ly = (m - 1, y) if m > 1 else (12, y - 1)
    prev_start = (start - timedelta(days=start.day)).replace(day=1)
    prev_total = Expense.objects.filter(
        user=user, expense_date__gte=prev_start, expense_date__lt=start
    ).aggregate(total=Sum("amount"))["total"] or 0
    if prev_total == 0:
        return {"sent": 0, "skipped": "no_previous_month_data"}
    growth = (projected / prev_total - 1) * 100
    if growth <= 20:
        return {"sent": 0, "skipped": "below_trend_threshold"}
    return send_once(
        user,
        event_type="spending_trend_alert",
        deduplication_key=f"{y}-{m:02d}",
        title="Spending trend alert",
        body=f"Your projected monthly spend is {growth:.0f}% higher than last month.",
        url="/analytics/",
        data={"projected": round(float(projected), 2), "growthPercent": round(float(growth), 2)},
    )
