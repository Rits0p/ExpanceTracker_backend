"""
Business logic services for ExpenseIQ.
Keeps complex operations out of views and models.
"""
from datetime import datetime, date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import RecurringExpense, Expense


def _add_months(source_date, months):
    """Add N months to a date, handling month/year rollover and day clamping."""
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    day = min(
        source_date.day,
        [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
         31, 30, 31, 30, 31, 31, 30, 31, 30, 31, 30, 31][month - 1]
    )
    return source_date.replace(year=year, month=month, day=day)


def calculate_next_due_date(current_date, frequency):
    """Calculate the next due date based on frequency."""
    freq_map = {
        'daily': 1,
        'weekly': 7,
        'monthly': 1,
        'quarterly': 3,
        'yearly': 12,
    }
    months = freq_map.get(frequency, 0)
    if frequency in ('daily', 'weekly'):
        from datetime import timedelta
        return current_date + timedelta(days=months)
    return _add_months(current_date, months)


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
    ).select_related('category', 'user')

    if user is not None:
        queryset = queryset.filter(user=user)

    created = []

    with transaction.atomic():
        for re in queryset:
            # Skip if end_date is in the past
            if re.end_date and re.end_date < today:
                RecurringExpense.objects.filter(id=re.id).update(is_active=False)
                continue

            # Prevent duplicate generation for the same due date
            if Expense.objects.filter(
                user=re.user,
                recurring_expense=re,
                expense_date__date=re.next_due_date,
            ).exists():
                continue

            # Create the expense record
            expense_datetime = timezone.make_aware(
                datetime.combine(re.next_due_date, datetime.min.time())
            )
            expense = Expense.objects.create(
                user=re.user,
                title=re.title,
                amount=re.amount,
                category=re.category.name,
                expense_date=expense_datetime,
                notes=re.notes or '',
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
            else:
                RecurringExpense.objects.filter(id=re.id).update(
                    next_due_date=new_due_date,
                )

            created.append(expense)

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
    monthly_cost = Decimal('0.00')
    for re in active:
        amount = re.amount
        freq = re.frequency
        if freq == 'daily':
            monthly_cost += amount * Decimal('30')
        elif freq == 'weekly':
            monthly_cost += amount * Decimal('4.33')
        elif freq == 'monthly':
            monthly_cost += amount
        elif freq == 'quarterly':
            monthly_cost += amount / Decimal('3')
        elif freq == 'yearly':
            monthly_cost += amount / Decimal('12')

    # Upcoming: next 5 due dates (within next 30 days)
    upcoming = active.filter(
        next_due_date__gte=today,
        next_due_date__lte=today.replace(day=28) + timezone.timedelta(days=30),
    ).order_by('next_due_date')[:5]

    upcoming_payments = [
        {
            'id': re.id,
            'title': re.title,
            'amount': float(re.amount),
            'dueDate': re.next_due_date.isoformat(),
            'category': re.category.name,
            'frequency': re.get_frequency_display(),
        }
        for re in upcoming
    ]

    # Overdue: past due dates for active recurring expenses
    # (where no expense has been generated yet for that date)
    overdue = active.filter(next_due_date__lt=today)
    overdue_payments = [
        {
            'id': re.id,
            'title': re.title,
            'amount': float(re.amount),
            'dueDate': re.next_due_date.isoformat(),
            'category': re.category.name,
            'frequency': re.get_frequency_display(),
        }
        for re in overdue
    ]

    # Next due date overall
    next_due = active.filter(next_due_date__gte=today).order_by('next_due_date').first()

    return {
        'totalRecurring': total_recurring,
        'monthlyRecurringCost': round(float(monthly_cost), 2),
        'upcomingPayments': upcoming_payments,
        'overduePayments': overdue_payments,
        'nextDueDate': next_due.next_due_date.isoformat() if next_due else None,
    }
