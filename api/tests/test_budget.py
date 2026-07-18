"""
Tests for Budget API endpoints.
Covers: set/update budget, get with spending info, list all, warnings.
"""
from decimal import Decimal
from datetime import timedelta

from django.utils import timezone

from api.models import Budget, Expense
from .base import BaseAPITestCase


class BudgetSetTests(BaseAPITestCase):
    """POST /api/v1/budget — set/update monthly budget."""

    def test_set_budget_new(self):
        """Should create a new budget for a month."""
        payload = {
            'month': 1,
            'year': 2027,
            'totalMonthlyBudget': '3000.00',
            'dailyBudget': '150.00',
            'weeklyBudget': '950.00',
            'yearlyBudget': '35000.00',
            'warningThreshold': 75,
        }
        response = self.client.post('/api/v1/budget', payload, format='json')
        data = self.assert_success_response(response)
        self.assertEqual(data['message'], 'Budget set successfully')
        self.assertEqual(data['data']['month'], 1)
        self.assertEqual(data['data']['year'], 2027)
        self.assertEqual(data['data']['totalMonthlyBudget'], 3000.00)
        self.assertEqual(data['data']['dailyBudget'], 150.00)
        self.assertEqual(data['data']['weeklyBudget'], 950.00)
        self.assertEqual(data['data']['yearlyBudget'], 35000.00)
        self.assertEqual(data['data']['warningThreshold'], 75)

    def test_set_budget_updates_existing(self):
        """Should update existing budget via upsert and preserve other budgets if not sent."""
        now = self.now
        # First set all budgets
        payload = {
            'month': now.month,
            'year': now.year,
            'totalMonthlyBudget': '3500.00',
            'dailyBudget': '120.00',
            'weeklyBudget': '800.00',
            'yearlyBudget': '40000.00',
            'warningThreshold': 90,
        }
        response = self.client.post('/api/v1/budget', payload, format='json')
        data = self.assert_success_response(response)
        
        # Now partially update only monthly budget
        partial_payload = {
            'month': now.month,
            'year': now.year,
            'totalMonthlyBudget': '3800.00',
        }
        response = self.client.post('/api/v1/budget', partial_payload, format='json')
        data = self.assert_success_response(response)
        
        self.assertEqual(data['data']['totalMonthlyBudget'], 3800.00)
        # Should preserve daily, weekly, and yearly budgets from previous set
        self.assertEqual(data['data']['dailyBudget'], 120.00)
        self.assertEqual(data['data']['weeklyBudget'], 800.00)
        self.assertEqual(data['data']['yearlyBudget'], 40000.00)
        self.assertEqual(data['data']['warningThreshold'], 90)
        
        # Should not create a new budget
        self.assertEqual(
            Budget.objects.filter(month=now.month, year=now.year).count(), 1
        )

    def test_set_budget_default_warning_threshold(self):
        """Should use default warning threshold of 80."""
        payload = {
            'month': 6,
            'year': 2027,
            'totalMonthlyBudget': '2000.00',
        }
        response = self.client.post('/api/v1/budget', payload, format='json')
        data = self.assert_success_response(response)
        self.assertEqual(data['data']['warningThreshold'], 80)

    def test_set_budget_missing_required_fields(self):
        """Should return 400 when required fields are missing."""
        payload = {'month': 5}
        response = self.client.post('/api/v1/budget', payload, format='json')
        self.assert_error_response(response, 400)

    def test_set_budget_response_format(self):
        """Should include _id alias."""
        now = self.now
        payload = {
            'month': now.month,
            'year': now.year,
            'totalMonthlyBudget': '2500.00',
        }
        response = self.client.post('/api/v1/budget', payload, format='json')
        data = self.assert_success_response(response)
        self.assertIn('_id', data['data'])
        self.assertEqual(data['data']['_id'], str(data['data']['id']))


class BudgetGetTests(BaseAPITestCase):
    """GET /api/v1/budget/?month=&year= — get budget with spending info."""

    def test_get_budget_with_spending_info(self):
        """Should return budget with currentSpent, remainingAmount, usagePercent."""
        now = self.now
        response = self.client.get('/api/v1/budget/', {
            'month': now.month, 'year': now.year
        })
        data = self.assert_success_response(response)
        self.assertIn('currentSpent', data['data'])
        self.assertIn('remainingAmount', data['data'])
        self.assertIn('usagePercent', data['data'])
        self.assertIn('isWarning', data['data'])
        self.assertEqual(data['data']['totalMonthlyBudget'], 2500.00)

    def test_get_budget_without_trailing_slash(self):
        """Should succeed when accessing GET /api/v1/budget (without trailing slash)."""
        now = self.now
        response = self.client.get('/api/v1/budget', {
            'month': now.month, 'year': now.year
        })
        data = self.assert_success_response(response)
        self.assertEqual(data['data']['totalMonthlyBudget'], 2500.00)

    def test_get_budget_spending_calculation(self):
        """Spending should reflect actual expenses in the month."""
        now = self.now
        response = self.client.get('/api/v1/budget/', {
            'month': now.month, 'year': now.year
        })
        data = self.assert_success_response(response)
        # currentSpent should be >= 0
        self.assertGreaterEqual(data['data']['currentSpent'], 0)
        # remainingAmount = budget - spent
        expected_remaining = data['data']['totalMonthlyBudget'] - data['data']['currentSpent']
        self.assertAlmostEqual(data['data']['remainingAmount'], expected_remaining, places=2)

    def test_get_budget_not_found(self):
        """Should return 404 for non-existent budget."""
        response = self.client.get('/api/v1/budget/', {'month': 12, 'year': 1999})
        self.assert_error_response(response, 404)

    def test_get_budget_missing_params(self):
        """Should return 400 when month/year params are missing."""
        response = self.client.get('/api/v1/budget/')
        self.assert_error_response(response, 400)

    def test_get_budget_is_warning_flag(self):
        """isWarning should be True when usage exceeds threshold."""
        now = self.now
        # Create expenses that exceed 80% of $2500 = $2000
        Expense.objects.create(
            title='Big Purchase', amount=Decimal('2100.00'),
            category='Shopping', expense_date=now, payment_method='Cash',
        )
        response = self.client.get('/api/v1/budget/', {
            'month': now.month, 'year': now.year
        })
        data = self.assert_success_response(response)
        self.assertTrue(data['data']['isWarning'])


class BudgetGetAllTests(BaseAPITestCase):
    """GET /api/v1/budget/all — list all budgets."""

    def test_get_all_budgets(self):
        """Should return all budget records."""
        response = self.client.get('/api/v1/budget/all')
        data = self.assert_success_response(response)
        self.assertIsInstance(data['data'], list)
        self.assertGreaterEqual(len(data['data']), 1)

    def test_get_all_budgets_ordered(self):
        """Should return budgets ordered by year/month descending."""
        Budget.objects.create(month=1, year=2025, total_monthly_budget=1000)
        Budget.objects.create(month=12, year=2026, total_monthly_budget=2000)
        response = self.client.get('/api/v1/budget/all')
        data = self.assert_success_response(response)
        years = [b['year'] for b in data['data']]
        self.assertEqual(years, sorted(years, reverse=True))


class BudgetWarningsTests(BaseAPITestCase):
    """GET /api/v1/budget/warnings — current month warnings."""

    def test_warnings_returns_budget_status(self):
        """Should return warning status for current month."""
        response = self.client.get('/api/v1/budget/warnings')
        data = self.assert_success_response(response)
        self.assertIn('warning', data['data'])
        self.assertIn('usage', data['data'])
        self.assertIn('spent', data['data'])
        self.assertIn('budget', data['data'])
        self.assertIn('remaining', data['data'])
        self.assertIn('threshold', data['data'])

    def test_warnings_no_budget_set(self):
        """Should return warning=False when no budget exists for current month."""
        Budget.objects.all().delete()
        response = self.client.get('/api/v1/budget/warnings')
        data = self.assert_success_response(response)
        self.assertFalse(data['data']['warning'])
        self.assertIn('message', data['data'])

    def test_warnings_under_threshold(self):
        """Should report warning=False when spending is under threshold."""
        response = self.client.get('/api/v1/budget/warnings')
        data = self.assert_success_response(response)
        # With only small test expenses (~195), usage should be well under 80%
        self.assertLess(data['data']['usage'], 80)
        self.assertFalse(data['data']['warning'])

    def test_warnings_over_threshold(self):
        """Should report warning=True when spending exceeds threshold."""
        now = self.now
        Expense.objects.create(
            title='Emergency Purchase', amount=Decimal('2100.00'),
            category='Shopping', expense_date=now, payment_method='Cash',
        )
        response = self.client.get('/api/v1/budget/warnings')
        data = self.assert_success_response(response)
        self.assertTrue(data['data']['warning'])
        self.assertGreaterEqual(data['data']['usage'], 80)
