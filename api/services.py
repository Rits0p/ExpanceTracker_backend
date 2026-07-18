"""
Business logic services for ExpenseIQ.
Keeps complex operations out of views and models.
"""

from datetime import datetime, date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import RecurringExpense, Expense
from .utils import calculate_next_due_date


def generate_recurring_expenses(user=None):
    """
    Generate Expense records for all active recurring expenses that are due.

    Checks all active recurring expenses where today >= next_due_date,
    creates an Expense for each, and updates the next_due_date.

    Skips dates that already have a generated expense to prevent duplicates.

    Args:
        user: Optional user to filter by. If None, processes all users.

    Returns:
        List of created Expense objects.
    """
    today = timezone.now().date()

    queryset = RecurringExpense.objects.filter(
        is_active=True,
        next_due_date__lte=today,
    ).select_related("category", "user")

    if user is not None:
        queryset = queryset.filter(user=user)

    created = []
    deactivated = []

    with transaction.atomic():
        for re in queryset:
            # Skip if end_date is in the past
            if re.end_date and re.end_date < today:
                RecurringExpense.objects.filter(id=re.id).update(is_active=False)
                deactivated.append(re)
                continue

            # Prevent duplicate generation for the same due date
            if Expense.objects.filter(
                user=re.user,
                recurring_expense=re,
                expense_date__date=re.next_due_date,
            ).exists():
                continue

            # Create the expense record
            expense_datetime = timezone.make_aware(datetime.combine(re.next_due_date, datetime.min.time()))
            expense = Expense.objects.create(
                user=re.user,
                title=re.title,
                amount=re.amount,
                category=re.category.name,
                expense_date=expense_datetime,
                notes=re.notes or "",
                recurring_expense=re,
            )

            # Calculate next due date
            new_due_date = calculate_next_due_date(re.next_due_date, re.frequency)

            # Deactivate if past end_date
            if re.end_date and new_due_date > re.end_date:
                RecurringExpense.objects.filter(id=re.id).update(
                    next_due_date=new_due_date,
                    is_active=False,
                )
                deactivated.append(re)
            else:
                RecurringExpense.objects.filter(id=re.id).update(
                    next_due_date=new_due_date,
                )

            created.append(expense)

    # Deliver only after the database transaction is committed, so a push never
    # describes an expense that later rolls back.
    if created or deactivated:
        from .notifications import send_push_notification, notify_recurring_expense_ended

        def dispatch_notifications():
            for expense in created:
                send_push_notification(
                    expense.user,
                    event_type="recurring_expense_generated",
                    title="Recurring expense added",
                    body=f"A recurring expense was added to your tracker: {expense.title}.",
                    url="/expenses/",
                    data={"expenseId": expense.id},
                )
            for re in deactivated:
                notify_recurring_expense_ended(re.user, re)

        transaction.on_commit(dispatch_notifications)

    return created


def get_recurring_dashboard_stats(user):
    """
    Get recurring expense statistics for the dashboard.

    Returns:
        Dict with totalRecurring, monthlyRecurringCost,
        upcomingPayments, overduePayments, nextDueDate.
    """
    today = timezone.now().date()
    start_of_month = today.replace(day=1)

    active = RecurringExpense.objects.filter(user=user, is_active=True)

    total_recurring = active.count()

    # Monthly recurring cost: normalize all frequencies to monthly
    monthly_cost = Decimal("0.00")
    for re in active:
        amount = re.amount
        freq = re.frequency
        if freq == "daily":
            monthly_cost += amount * Decimal("30")
        elif freq == "weekly":
            monthly_cost += amount * Decimal("4.33")
        elif freq == "monthly":
            monthly_cost += amount
        elif freq == "quarterly":
            monthly_cost += amount / Decimal("3")
        elif freq == "yearly":
            monthly_cost += amount / Decimal("12")

    # Upcoming: next 5 due dates (within next 30 days)
    upcoming = active.filter(
        next_due_date__gte=today,
        next_due_date__lte=today.replace(day=28) + timezone.timedelta(days=30),
    ).order_by("next_due_date")[:5]

    upcoming_payments = [
        {
            "id": re.id,
            "title": re.title,
            "amount": float(re.amount),
            "dueDate": re.next_due_date.isoformat(),
            "category": re.category.name,
            "frequency": re.get_frequency_display(),
        }
        for re in upcoming
    ]

    # Overdue: past due dates for active recurring expenses
    # (where no expense has been generated yet for that date)
    overdue = active.filter(next_due_date__lt=today)
    overdue_payments = [
        {
            "id": re.id,
            "title": re.title,
            "amount": float(re.amount),
            "dueDate": re.next_due_date.isoformat(),
            "category": re.category.name,
            "frequency": re.get_frequency_display(),
        }
        for re in overdue
    ]

    # Next due date overall
    next_due = active.filter(next_due_date__gte=today).order_by("next_due_date").first()

    return {
        "totalRecurring": total_recurring,
        "monthlyRecurringCost": round(float(monthly_cost), 2),
        "upcomingPayments": upcoming_payments,
        "overduePayments": overdue_payments,
        "nextDueDate": next_due.next_due_date.isoformat() if next_due else None,
    }


def generate_weekly_report(user):
    """
    Calculate weekly spending stats and dispatch a push notification summary to the user.
    """
    from django.utils import timezone
    from datetime import timedelta
    from django.db.models import Sum
    from .notifications import send_push_notification
    from .models import UserSettings

    # Define periods
    today = timezone.localtime(timezone.now())
    current_end = today
    current_start = today - timedelta(days=7)
    prev_end = current_start
    prev_start = current_start - timedelta(days=7)

    # Calculate current period total & count
    current_qs = user.expenses.filter(expense_date__gte=current_start, expense_date__lt=current_end)
    current_total = current_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    count = current_qs.count()

    # Calculate previous period total
    prev_total = user.expenses.filter(expense_date__gte=prev_start, expense_date__lt=prev_end).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")

    # Calculate growth %
    current_total = Decimal(current_total)
    prev_total = Decimal(prev_total)

    if prev_total > 0:
        growth_percent = ((current_total - prev_total) / prev_total) * 100
    else:
        growth_percent = Decimal("100.00") if current_total > 0 else Decimal("0.00")

    # Get currency symbol
    user_settings, _ = UserSettings.objects.get_or_create(user=user)
    sym = user_settings.currency_symbol or "$"

    growth_str = f"+{growth_percent:.1f}%" if growth_percent > 0 else f"{growth_percent:.1f}%"

    body = f"You spent {sym}{current_total:.2f} across {count} transaction(s) this week ({growth_str} vs last week)."

    # We send this notification. The preference check is done in send_push_notification.
    return send_push_notification(
        user,
        event_type="weekly_summary",
        title="Weekly Spending Summary",
        body=body,
        url="/reports/",
        data={
            "total": float(current_total),
            "count": count,
            "growth": float(growth_percent),
        },
    )


def cleanup_stale_device_tokens(days=30):
    """
    Remove DeviceToken records that have not been seen for more than the specified number of days.
    """
    from django.utils import timezone
    from datetime import timedelta
    from .models import DeviceToken

    cutoff = timezone.now() - timedelta(days=days)
    stale_tokens = DeviceToken.objects.filter(last_seen_at__lt=cutoff)
    count, _ = stale_tokens.delete()
    return count
