"""
Utility helpers for ExpenseIQ Django backend.
Matches the Node.js API response format.
"""
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import math
from datetime import datetime, timedelta
from django.utils import timezone


# ───── Custom Exception Handler ─────
def custom_exception_handler(exc, context):
    """
    Custom DRF exception handler that returns responses in the same
    {success, message, errors} format as the Node.js backend.
    """
    response = exception_handler(exc, context)

    if response is not None:
        custom_data = {
            'success': False,
            'message': str(exc.detail) if hasattr(exc, 'detail') else str(exc),
        }
        if hasattr(exc, 'detail') and isinstance(exc.detail, dict):
            custom_data['errors'] = exc.detail
            custom_data['message'] = 'Validation failed'
        elif hasattr(exc, 'detail') and isinstance(exc.detail, list):
            custom_data['errors'] = exc.detail
            custom_data['message'] = 'Validation failed'

        response.data = custom_data

    return response


# ───── Standard API Response Helpers ─────
class ApiResponse:
    """Mirrors the Node.js ApiResponse utility class."""

    @staticmethod
    def success(data=None, message='Success', status_code=200, meta=None):
        response = {'success': True, 'message': message, 'data': data}
        if meta:
            response['meta'] = meta
        return Response(response, status=status_code)

    @staticmethod
    def created(data=None, message='Created successfully'):
        return Response({'success': True, 'message': message, 'data': data}, status=status.HTTP_201_CREATED)

    @staticmethod
    def error(message='Internal server error', status_code=500, errors=None):
        response = {'success': False, 'message': message}
        if errors:
            response['errors'] = errors
        return Response(response, status=status_code)

    @staticmethod
    def paginated(data, page, limit, total, message='Success'):
        page = int(page)
        limit = int(limit)
        return Response({
            'success': True,
            'message': message,
            'data': data,
            'meta': {
                'page': page,
                'limit': limit,
                'total': total,
                'totalPages': math.ceil(total / limit) if limit > 0 else 0,
                'hasNextPage': page * limit < total,
                'hasPrevPage': page > 1,
            },
        })


# ───── Date Helpers (matching Node.js dateHelpers.js) ─────
def get_start_of_week(date=None):
    if date is None:
        date = timezone.now()
    # Monday = 0 in Python (ISO), but the Node.js code treats Monday as start of week
    days_since_monday = date.weekday()  # 0=Monday
    start = date - timedelta(days=days_since_monday)
    return start.replace(hour=0, minute=0, second=0, microsecond=0)


def get_end_of_week(date=None):
    start = get_start_of_week(date)
    end = start + timedelta(days=6)
    return end.replace(hour=23, minute=59, second=59, microsecond=999999)


def get_start_of_month(date=None):
    if date is None:
        date = timezone.now()
    return date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def get_end_of_month(date=None):
    if date is None:
        date = timezone.now()
    # Go to next month day 1, then subtract 1 day
    if date.month == 12:
        next_month = date.replace(year=date.year + 1, month=1, day=1)
    else:
        next_month = date.replace(month=date.month + 1, day=1)
    last_day = next_month - timedelta(days=1)
    return last_day.replace(hour=23, minute=59, second=59, microsecond=999999)


def get_previous_week_range():
    now = timezone.now()
    start = get_start_of_week(now) - timedelta(days=7)
    end = start + timedelta(days=6)
    end = end.replace(hour=23, minute=59, second=59, microsecond=999999)
    return start, end


def get_previous_month_range():
    now = timezone.now()
    first_of_this_month = now.replace(day=1)
    last_of_prev_month = first_of_this_month - timedelta(days=1)
    first_of_prev_month = last_of_prev_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = last_of_prev_month.replace(hour=23, minute=59, second=59, microsecond=999999)
    return first_of_prev_month, end


def get_last_n_months_labels(n=6):
    labels = []
    now = timezone.now()
    for i in range(n - 1, -1, -1):
        month = now.month - i
        year = now.year
        while month <= 0:
            month += 12
            year -= 1
        start = timezone.now().replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)
        if month == 12:
            end_date = start.replace(year=year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = start.replace(month=month + 1, day=1) - timedelta(days=1)
        end = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        label = start.strftime('%b %Y')
        labels.append({'label': label, 'start': start, 'end': end, 'month': month, 'year': year})
    return labels


def calc_growth(current, previous):
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100, 2)


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
        return current_date + timedelta(days=months)
    return _add_months(current_date, months)
