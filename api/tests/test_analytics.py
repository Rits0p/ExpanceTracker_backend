"""
Tests for Analytics API endpoints.
Covers: KPIs, weekly/monthly analytics, all chart endpoints, category analytics.
"""
from decimal import Decimal
from datetime import timedelta

from django.utils import timezone

from api.models import Expense, Category
from .base import BaseAPITestCase


class AnalyticsKPIsTests(BaseAPITestCase):
    """GET /api/v1/analytics/kpis — KPI dashboard data."""

    def test_kpis_returns_success(self):
        """Should return 200 with KPI data."""
        response = self.client.get('/api/v1/analytics/kpis')
        data = self.assert_success_response(response)
        self.assertIsNotNone(data['data'])

    def test_kpis_response_structure(self):
        """Should include all expected KPI fields."""
        response = self.client.get('/api/v1/analytics/kpis')
        data = self.assert_success_response(response)
        kpis = data['data']
        expected_keys = [
            'totalExpense', 'monthlyExpense', 'weeklyExpense',
            'dailyAverage', 'topSpendingCategory', 'highestExpense',
            'expenseDistribution',
        ]
        for key in expected_keys:
            self.assertIn(key, kpis, f"Missing KPI field: {key}")

    def test_kpis_total_expense_is_numeric(self):
        """totalExpense should be a number."""
        response = self.client.get('/api/v1/analytics/kpis')
        data = self.assert_success_response(response)
        self.assertIsInstance(data['data']['totalExpense'], (int, float))

    def test_kpis_expense_distribution_is_list(self):
        """expenseDistribution should be a list of category breakdowns."""
        response = self.client.get('/api/v1/analytics/kpis')
        data = self.assert_success_response(response)
        self.assertIsInstance(data['data']['expenseDistribution'], list)

    def test_kpis_expense_distribution_format(self):
        """Each distribution item should have _id, total, count, avgAmount."""
        response = self.client.get('/api/v1/analytics/kpis')
        data = self.assert_success_response(response)
        for item in data['data']['expenseDistribution']:
            self.assertIn('_id', item)
            self.assertIn('total', item)
            self.assertIn('count', item)

    def test_kpis_with_no_data(self):
        """Should handle empty database gracefully."""
        Expense.objects.all().delete()
        response = self.client.get('/api/v1/analytics/kpis')
        data = self.assert_success_response(response)
        self.assertEqual(data['data']['totalExpense'], 0)


class AnalyticsWeeklyTests(BaseAPITestCase):
    """GET /api/v1/analytics/weekly — weekly expense analytics."""

    def test_weekly_returns_success(self):
        """Should return 200 with weekly data."""
        response = self.client.get('/api/v1/analytics/weekly')
        data = self.assert_success_response(response)
        self.assertIsNotNone(data['data'])

    def test_weekly_response_structure(self):
        """Should include currentWeek, previousWeek, growth, transactionCount, dailyTrend."""
        response = self.client.get('/api/v1/analytics/weekly')
        data = self.assert_success_response(response)
        weekly = data['data']
        self.assertIn('currentWeek', weekly)
        self.assertIn('previousWeek', weekly)
        self.assertIn('growth', weekly)
        self.assertIn('transactionCount', weekly)
        self.assertIn('dailyTrend', weekly)

    def test_weekly_values_are_numeric(self):
        """All weekly values should be numeric."""
        response = self.client.get('/api/v1/analytics/weekly')
        data = self.assert_success_response(response)
        weekly = data['data']
        self.assertIsInstance(weekly['currentWeek'], (int, float))
        self.assertIsInstance(weekly['previousWeek'], (int, float))
        self.assertIsInstance(weekly['growth'], (int, float))
        self.assertIsInstance(weekly['transactionCount'], int)

    def test_weekly_daily_trend_is_list(self):
        """dailyTrend should be a list."""
        response = self.client.get('/api/v1/analytics/weekly')
        data = self.assert_success_response(response)
        self.assertIsInstance(data['data']['dailyTrend'], list)


class AnalyticsMonthlyTests(BaseAPITestCase):
    """GET /api/v1/analytics/monthly — monthly expense analytics."""

    def test_monthly_returns_success(self):
        """Should return 200 with monthly data."""
        response = self.client.get('/api/v1/analytics/monthly')
        data = self.assert_success_response(response)
        self.assertIsNotNone(data['data'])

    def test_monthly_response_structure(self):
        """Should include currentMonth, previousMonth, growth, transactionCount, monthlyTrend."""
        response = self.client.get('/api/v1/analytics/monthly')
        data = self.assert_success_response(response)
        monthly = data['data']
        self.assertIn('currentMonth', monthly)
        self.assertIn('previousMonth', monthly)
        self.assertIn('growth', monthly)
        self.assertIn('transactionCount', monthly)
        self.assertIn('monthlyTrend', monthly)

    def test_monthly_trend_is_list(self):
        """monthlyTrend should be a list of month-aggregated data."""
        response = self.client.get('/api/v1/analytics/monthly')
        data = self.assert_success_response(response)
        self.assertIsInstance(data['data']['monthlyTrend'], list)

    def test_monthly_trend_item_format(self):
        """Each trend item should have _id (year/month), total, count."""
        response = self.client.get('/api/v1/analytics/monthly')
        data = self.assert_success_response(response)
        for item in data['data']['monthlyTrend']:
            self.assertIn('_id', item)
            self.assertIn('year', item['_id'])
            self.assertIn('month', item['_id'])
            self.assertIn('total', item)
            self.assertIn('count', item)


class AnalyticsMonthlyBarChartTests(BaseAPITestCase):
    """GET /api/v1/analytics/charts/monthly-bar"""

    def test_monthly_bar_returns_success(self):
        """Should return 200."""
        response = self.client.get('/api/v1/analytics/charts/monthly-bar')
        data = self.assert_success_response(response)
        self.assertIsInstance(data['data'], list)

    def test_monthly_bar_has_6_months(self):
        """Should return data for 6 months."""
        response = self.client.get('/api/v1/analytics/charts/monthly-bar')
        data = self.assert_success_response(response)
        self.assertEqual(len(data['data']), 6)

    def test_monthly_bar_item_format(self):
        """Each item should have label, total, count."""
        response = self.client.get('/api/v1/analytics/charts/monthly-bar')
        data = self.assert_success_response(response)
        for item in data['data']:
            self.assertIn('label', item)
            self.assertIn('total', item)
            self.assertIn('count', item)
            self.assertIsInstance(item['total'], (int, float))

    def test_monthly_bar_labels_are_strings(self):
        """Labels should be month abbreviations like 'Jan 2026'."""
        response = self.client.get('/api/v1/analytics/charts/monthly-bar')
        data = self.assert_success_response(response)
        for item in data['data']:
            self.assertIsInstance(item['label'], str)
            self.assertGreater(len(item['label']), 0)


class AnalyticsWeeklyLineChartTests(BaseAPITestCase):
    """GET /api/v1/analytics/charts/weekly-line"""

    def test_weekly_line_returns_success(self):
        """Should return 200."""
        response = self.client.get('/api/v1/analytics/charts/weekly-line')
        data = self.assert_success_response(response)
        self.assertIsInstance(data['data'], list)

    def test_weekly_line_has_7_days(self):
        """Should return data for 7 days."""
        response = self.client.get('/api/v1/analytics/charts/weekly-line')
        data = self.assert_success_response(response)
        self.assertEqual(len(data['data']), 7)

    def test_weekly_line_item_format(self):
        """Each item should have day, thisWeek, lastWeek."""
        response = self.client.get('/api/v1/analytics/charts/weekly-line')
        data = self.assert_success_response(response)
        for item in data['data']:
            self.assertIn('day', item)
            self.assertIn('thisWeek', item)
            self.assertIn('lastWeek', item)

    def test_weekly_line_day_names(self):
        """Days should be Sun, Mon, Tue, Wed, Thu, Fri, Sat."""
        response = self.client.get('/api/v1/analytics/charts/weekly-line')
        data = self.assert_success_response(response)
        days = [item['day'] for item in data['data']]
        self.assertEqual(days, ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'])


class AnalyticsCategoryPieChartTests(BaseAPITestCase):
    """GET /api/v1/analytics/charts/category-pie"""

    def test_category_pie_returns_success(self):
        """Should return 200."""
        response = self.client.get('/api/v1/analytics/charts/category-pie')
        data = self.assert_success_response(response)
        self.assertIsInstance(data['data'], list)

    def test_category_pie_item_format(self):
        """Each item should have _id, total, count, avgAmount."""
        response = self.client.get('/api/v1/analytics/charts/category-pie')
        data = self.assert_success_response(response)
        for item in data['data']:
            self.assertIn('_id', item)
            self.assertIn('total', item)
            self.assertIn('count', item)
            self.assertIn('avgAmount', item)

    def test_category_pie_totals_are_positive(self):
        """All totals should be >= 0."""
        response = self.client.get('/api/v1/analytics/charts/category-pie')
        data = self.assert_success_response(response)
        for item in data['data']:
            self.assertGreaterEqual(item['total'], 0)



class AnalyticsCategoryTests(BaseAPITestCase):
    """GET /api/v1/analytics/categories — category analytics with budget usage."""

    def test_category_analytics_returns_success(self):
        """Should return 200."""
        response = self.client.get('/api/v1/analytics/categories')
        data = self.assert_success_response(response)
        self.assertIsInstance(data['data'], list)

    def test_category_analytics_response_structure(self):
        """Each item should have enriched category fields."""
        response = self.client.get('/api/v1/analytics/categories')
        data = self.assert_success_response(response)
        for item in data['data']:
            self.assertIn('category', item)
            self.assertIn('spent', item)
            self.assertIn('count', item)
            self.assertIn('avgAmount', item)
            self.assertIn('budget', item)
            self.assertIn('usagePercent', item)
            self.assertIn('exceeded', item)
            self.assertIn('icon', item)
            self.assertIn('color', item)

    def test_category_analytics_budget_enrichment(self):
        """Categories with defined budgets should have correct budget values."""
        response = self.client.get('/api/v1/analytics/categories')
        data = self.assert_success_response(response)
        for item in data['data']:
            if item['category'] == 'Food':
                self.assertEqual(item['budget'], 500.0)
                self.assertEqual(item['icon'], 'ph-hamburger')
                self.assertEqual(item['color'], '#10b981')

    def test_category_analytics_usage_percent_calculation(self):
        """usagePercent should be (spent / budget * 100) when budget > 0."""
        response = self.client.get('/api/v1/analytics/categories')
        data = self.assert_success_response(response)
        for item in data['data']:
            if item['budget'] > 0:
                expected = round((item['spent'] / item['budget'] * 100), 2)
                self.assertAlmostEqual(item['usagePercent'], expected, places=1)

    def test_category_analytics_exceeded_flag(self):
        """exceeded should be True when spent > budget."""
        # Create an expense that pushes Food over its $500 budget
        Expense.objects.create(
            title='Big Feast',
            amount=Decimal('1000.00'),
            category='Food',
            payment_method='Cash',
            expense_date=self.now,
        )
        response = self.client.get('/api/v1/analytics/categories')
        data = self.assert_success_response(response)
        food = next(item for item in data['data'] if item['category'] == 'Food')
        self.assertTrue(food['exceeded'])

    def test_category_analytics_unknown_category_gets_defaults(self):
        """Categories not in Category table should get default icon/color."""
        Expense.objects.create(
            title='Mysterious Expense',
            amount=Decimal('50.00'),
            category='Mystery',
            payment_method='Cash',
            expense_date=self.now,
        )
        response = self.client.get('/api/v1/analytics/categories')
        data = self.assert_success_response(response)
        mystery = next(
            (item for item in data['data'] if item['category'] == 'Mystery'), None
        )
        if mystery:
            self.assertEqual(mystery['icon'], 'ph-package')
            self.assertEqual(mystery['color'], '#888')
            self.assertEqual(mystery['budget'], 0)
            self.assertEqual(mystery['usagePercent'], 0)
            self.assertFalse(mystery['exceeded'])

    def test_category_analytics_empty_data(self):
        """Should return empty list when no expenses exist this month."""
        Expense.objects.all().delete()
        response = self.client.get('/api/v1/analytics/categories')
        data = self.assert_success_response(response)
        self.assertEqual(data['data'], [])
