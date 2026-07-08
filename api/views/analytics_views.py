"""
Views for ExpenseIQ API — Analytics endpoints.
Mirrors: /api/v1/analytics/*
"""
from rest_framework.views import APIView
from django.db.models import Sum, Count, Avg
from django.db.models.functions import ExtractMonth, ExtractYear, ExtractWeekDay
from django.utils import timezone
from datetime import datetime, timedelta, timezone as dt_timezone

from ..models import Expense, Category
from ..utils import (
    ApiResponse,
    get_start_of_week, get_end_of_week,
    get_start_of_month, get_end_of_month,
    get_previous_week_range, get_previous_month_range,
    get_last_n_months_labels, calc_growth,
)


def _sum_expenses(user, start, end):
    """Sum expenses in a date range."""
    result = Expense.objects.filter(
        user=user, expense_date__gte=start, expense_date__lte=end
    ).aggregate(total=Sum('amount'), count=Count('id'))
    return {
        'total': float(result['total'] or 0),
        'count': result['count'] or 0,
    }


def _group_expenses_by_category(user, start, end):
    """Group expenses by category for a date range."""
    data = (
        Expense.objects
        .filter(user=user, expense_date__gte=start, expense_date__lte=end)
        .values('category')
        .annotate(
            total=Sum('amount'),
            count=Count('id'),
            avgAmount=Avg('amount'),
        )
        .order_by('-total')
    )
    return [
        {
            '_id': item['category'],
            'total': float(item['total'] or 0),
            'count': item['count'],
            'avgAmount': round(float(item['avgAmount'] or 0), 2),
        }
        for item in data
    ]


def _monthly_expense_trend(user, months=6):
    """Get monthly expense aggregation for the last N months."""
    start_date = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start_date = start_date - timedelta(days=months * 31)
    start_date = start_date.replace(day=1)

    data = (
        Expense.objects
        .filter(user=user, expense_date__gte=start_date)
        .annotate(
            month=ExtractMonth('expense_date'),
            year=ExtractYear('expense_date'),
        )
        .values('month', 'year')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('year', 'month')
    )
    return [
        {
            '_id': {'year': item['year'], 'month': item['month']},
            'total': float(item['total'] or 0),
            'count': item['count'],
        }
        for item in data
    ]


def _daily_trend_for_week(user, start, end):
    """Get daily expense totals for a week. Uses ExtractWeekDay (1=Sunday...7=Saturday in Django)."""
    data = (
        Expense.objects
        .filter(user=user, expense_date__gte=start, expense_date__lte=end)
        .annotate(dow=ExtractWeekDay('expense_date'))
        .values('dow')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('dow')
    )
    return [
        {
            '_id': item['dow'],
            'total': float(item['total'] or 0),
            'count': item['count'],
        }
        for item in data
    ]


# ═══════════════════════════════════════════
#  ANALYTICS VIEWS
# ═══════════════════════════════════════════

class AnalyticsKPIsView(APIView):
    """GET /api/v1/analytics/kpis — KPI dashboard data"""

    def get(self, request):
        now = timezone.now()
        
        start_date_str = request.query_params.get('startDate')
        end_date_str = request.query_params.get('endDate')
        
        if start_date_str and end_date_str:
            try:
                start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
                end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                month_start = start_date
                month_end = end_date
            except ValueError:
                month_start = get_start_of_month(now)
                month_end = get_end_of_month(now)
        else:
            month_start = get_start_of_month(now)
            month_end = get_end_of_month(now)
            
        week_start = get_start_of_week(now)
        week_end = get_end_of_week(now)
        all_time_start = datetime(2000, 1, 1, tzinfo=dt_timezone.utc)

        total_exp = _sum_expenses(request.user, all_time_start, now)
        monthly_exp = _sum_expenses(request.user, month_start, month_end)
        weekly_exp = _sum_expenses(request.user, week_start, week_end)
        category_data = _group_expenses_by_category(request.user, month_start, month_end)

        # Top expense this month
        top_expense = (
            Expense.objects
            .filter(user=request.user, expense_date__gte=month_start, expense_date__lte=month_end)
            .order_by('-amount')
            .first()
        )
        from ..serializers import ExpenseSerializer
        top_expense_data = ExpenseSerializer(top_expense).data if top_expense else None

        days_in_month = (month_end - month_start).days or 1
        daily_avg = round(monthly_exp['total'] / days_in_month, 2)
        top_category = category_data[0] if category_data else None

        return ApiResponse.success({
            'totalExpense': total_exp['total'],
            'monthlyExpense': monthly_exp['total'],
            'weeklyExpense': weekly_exp['total'],
            'dailyAverage': daily_avg,
            'topSpendingCategory': top_category['_id'] if top_category else 'N/A',
            'highestExpense': top_expense_data,
            'expenseDistribution': category_data,
        })


class AnalyticsWeeklyView(APIView):
    """GET /api/v1/analytics/weekly — weekly expense analytics"""

    def get(self, request):
        now = timezone.now()
        this_week_start = get_start_of_week(now)
        this_week_end = get_end_of_week(now)
        prev_start, prev_end = get_previous_week_range()

        current = _sum_expenses(request.user, this_week_start, this_week_end)
        previous = _sum_expenses(request.user, prev_start, prev_end)
        daily_trend = _daily_trend_for_week(request.user, this_week_start, this_week_end)

        return ApiResponse.success({
            'currentWeek': current['total'],
            'previousWeek': previous['total'],
            'growth': calc_growth(current['total'], previous['total']),
            'transactionCount': current['count'],
            'dailyTrend': daily_trend,
        })


class AnalyticsMonthlyView(APIView):
    """GET /api/v1/analytics/monthly — monthly expense analytics"""

    def get(self, request):
        now = timezone.now()
        this_month_start = get_start_of_month(now)
        this_month_end = get_end_of_month(now)
        prev_start, prev_end = get_previous_month_range()

        current = _sum_expenses(request.user, this_month_start, this_month_end)
        previous = _sum_expenses(request.user, prev_start, prev_end)
        trend = _monthly_expense_trend(request.user, 6)

        return ApiResponse.success({
            'currentMonth': current['total'],
            'previousMonth': previous['total'],
            'growth': calc_growth(current['total'], previous['total']),
            'transactionCount': current['count'],
            'monthlyTrend': trend,
        })


class AnalyticsMonthlyBarChartView(APIView):
    """GET /api/v1/analytics/charts/monthly-bar"""

    def get(self, request):
        trend = _monthly_expense_trend(request.user, 6)
        labels = get_last_n_months_labels(6)

        data = []
        for label_info in labels:
            match = next(
                (t for t in trend
                 if t['_id']['month'] == label_info['month']
                 and t['_id']['year'] == label_info['year']),
                None
            )
            data.append({
                'label': label_info['label'],
                'total': match['total'] if match else 0,
                'count': match['count'] if match else 0,
            })

        return ApiResponse.success(data)


class AnalyticsWeeklyLineChartView(APIView):
    """GET /api/v1/analytics/charts/weekly-line"""

    def get(self, request):
        now = timezone.now()
        prev_start, prev_end = get_previous_week_range()
        this_week = _daily_trend_for_week(request.user, get_start_of_week(now), get_end_of_week(now))
        last_week = _daily_trend_for_week(request.user, prev_start, prev_end)

        # Django ExtractWeekDay: 1=Sunday, 2=Monday, ..., 7=Saturday
        days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
        data = []
        for i, day in enumerate(days):
            dow = i + 1  # 1=Sun, 2=Mon, etc.
            tw = next((d for d in this_week if d['_id'] == dow), None)
            lw = next((d for d in last_week if d['_id'] == dow), None)
            data.append({
                'day': day,
                'thisWeek': tw['total'] if tw else 0,
                'lastWeek': lw['total'] if lw else 0,
            })

        return ApiResponse.success(data)


class AnalyticsCategoryPieChartView(APIView):
    """GET /api/v1/analytics/charts/category-pie"""

    def get(self, request):
        now = timezone.now()
        start_date_str = request.query_params.get('startDate')
        end_date_str = request.query_params.get('endDate')
        
        if start_date_str and end_date_str:
            try:
                start = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
                end = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
            except ValueError:
                start = get_start_of_month(now)
                end = get_end_of_month(now)
        else:
            start = get_start_of_month(now)
            end = get_end_of_month(now)
            
        data = _group_expenses_by_category(request.user, start, end)
        return ApiResponse.success(data)


class AnalyticsCategoryView(APIView):
    """GET /api/v1/analytics/categories — category analytics with budget usage"""

    def get(self, request):
        now = timezone.now()
        start_date_str = request.query_params.get('startDate')
        end_date_str = request.query_params.get('endDate')
        
        if start_date_str and end_date_str:
            try:
                month_start = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
                month_end = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
            except ValueError:
                month_start = get_start_of_month(now)
                month_end = get_end_of_month(now)
        else:
            month_start = get_start_of_month(now)
            month_end = get_end_of_month(now)
            
        data = _group_expenses_by_category(request.user, month_start, month_end)

        # Enrich with category budget info
        categories = {c.name: c for c in Category.objects.filter(user=request.user)}

        enriched = []
        for d in data:
            cat = categories.get(d['_id'], None)
            budget = float(cat.monthly_budget) if cat else 0
            enriched.append({
                'category': d['_id'],
                'spent': d['total'],
                'count': d['count'],
                'avgAmount': d['avgAmount'],
                'budget': budget,
                'usagePercent': round((d['total'] / budget * 100), 2) if budget > 0 else 0,
                'exceeded': budget > 0 and d['total'] > budget,
                'icon': cat.icon if cat else 'ph-package',
                'color': cat.color if cat else '#888',
            })

        return ApiResponse.success(enriched)
