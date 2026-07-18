"""Firebase Cloud Messaging delivery and domain-notification helpers."""

import logging
from itertools import islice
from pathlib import Path

from django.conf import settings
from django.db import IntegrityError
from django.db.models import Sum
from django.utils import timezone

from .models import Budget, DeviceToken, NotificationEvent, UserSettings

logger = logging.getLogger(__name__)


PREFERENCE_BY_EVENT = {
    "budget_warning": "budget_alerts",
    "budget_exceeded": "budget_alerts",
    "recurring_expense_generated": "recurring_reminders",
    "weekly_summary": "weekly_report",
}


def _chunks(values, size):
    iterator = iter(values)
    while chunk := list(islice(iterator, size)):
        yield chunk


def _get_messaging():
    """Initialize Firebase only when a notification is actually sent."""
    credential_path = getattr(settings, "FIREBASE_SERVICE_ACCOUNT_PATH", "")
    if not credential_path:
        return None

    path = Path(credential_path)
    if not path.is_absolute():
        path = settings.BASE_DIR / path
    if not path.is_file():
        logger.warning("Firebase service-account file is not available.")
        return None

    try:
        import firebase_admin
        from firebase_admin import credentials, messaging

        try:
            firebase_admin.get_app()
        except ValueError:
            firebase_admin.initialize_app(credentials.Certificate(str(path)))
        return messaging
    except Exception:
        logger.exception("Firebase Cloud Messaging initialization failed.")
        return None


def send_push_notification(user, *, event_type, title, body, url="/", data=None):
    """Send one non-sensitive notification to all of a user's current devices."""
    preference = PREFERENCE_BY_EVENT.get(event_type)
    user_settings, _ = UserSettings.objects.get_or_create(user=user)
    if preference and not getattr(user_settings, preference):
        return {"sent": 0, "skipped": "preference_disabled"}

    messaging = _get_messaging()
    if messaging is None:
        return {"sent": 0, "skipped": "firebase_not_configured"}

    tokens = list(DeviceToken.objects.filter(user=user).values_list("token", flat=True))
    if not tokens:
        return {"sent": 0, "skipped": "no_devices"}

    payload = {"eventType": event_type, "url": url}
    payload.update({str(key): str(value) for key, value in (data or {}).items()})
    sent = 0
    invalid_tokens = []

    for token_batch in _chunks(tokens, 500):
        message_kwargs = {
            "tokens": token_batch,
            "notification": messaging.Notification(title=title, body=body),
            "data": payload,
        }
        # FCM requires WebpushConfig links to be absolute HTTPS URLs. Local
        # development uses relative paths, so omit the optional click link.
        if url.startswith("https://"):
            message_kwargs["webpush"] = messaging.WebpushConfig(
                fcm_options=messaging.WebpushFCMOptions(link=url),
            )
        message = messaging.MulticastMessage(
            **message_kwargs,
        )
        try:
            result = messaging.send_each_for_multicast(message)
        except Exception as e:
            logger.exception("FCM delivery failed for user id=%s: %s", user.id, str(e))
            print(f"ERROR: FCM delivery failed for user id={user.id}: {e}")
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
                print(
                    f"WARNING: FCM token invalid for user id={user.id}. Removing token. Error: {response.exception or error_code}"
                )
            else:
                logger.warning(
                    "FCM delivery failed for user id=%s: %s (exception: %s)",
                    user.id,
                    error_code or "unknown",
                    response.exception,
                )
                print(
                    f"ERROR: FCM delivery failed for user id={user.id}: {error_code or 'unknown'} - {response.exception}"
                )

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


def notify_budget_status(user, expense):
    """Notify once when current-month spending crosses warning or total budget."""
    expense_date = timezone.localtime(expense.expense_date)
    budget = Budget.objects.filter(
        user=user,
        month=expense_date.month,
        year=expense_date.year,
    ).first()
    if not budget or budget.total_monthly_budget <= 0:
        return {"sent": 0, "skipped": "no_budget"}

    month_start = expense_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = user.expenses.filter(expense_date__gte=month_start).aggregate(total=Sum("amount"))["total"] or 0
    usage = (total / budget.total_monthly_budget) * 100
    day_key = f"{expense_date.year}-{expense_date.month:02d}-{expense_date.day:02d}"
    if usage >= 100:
        return send_once(
            user,
            event_type="budget_exceeded",
            deduplication_key=day_key,
            title="Monthly budget exceeded",
            body="Your monthly expense budget has been exceeded.",
            url="/budget/",
            data={"usage": round(float(usage), 2)},
        )
    if usage >= budget.warning_threshold:
        return send_once(
            user,
            event_type="budget_warning",
            deduplication_key=day_key,
            title="Budget warning",
            body="Your monthly spending has reached its warning threshold.",
            url="/budget/",
            data={"usage": round(float(usage), 2)},
        )
    return {"sent": 0, "skipped": "below_threshold"}
