"""
Tests for health check endpoint and Django model validation.
"""
from decimal import Decimal
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from django.db import IntegrityError
from rest_framework.test import APIClient

from api.models import Category, Expense, Budget, Report


class HealthCheckTests(TestCase):
    """GET /health — server health check."""

    def setUp(self):
        self.client = APIClient()

    def test_health_check_returns_200(self):
        """Should return 200 OK."""
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)

    def test_health_check_response_format(self):
        """Should return status, timestamp, uptime."""
        response = self.client.get('/health')
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertIn('timestamp', data)
        self.assertIn('uptime', data)
        self.assertIsInstance(data['uptime'], (int, float))


# ═══════════════════════════════════════════
#  MODEL VALIDATION TESTS
# ═══════════════════════════════════════════

class CategoryModelTests(TestCase):
    """Category model validation."""

    def test_create_category(self):
        """Should create category with all fields."""
        cat = Category.objects.create(
            name='Food', icon='ph-hamburger', color='#10b981', monthly_budget=Decimal('500.00')
        )
        self.assertEqual(str(cat), 'ph-hamburger Food')

    def test_category_name_unique(self):
        """Should enforce unique name constraint."""
        Category.objects.create(name='Food')
        with self.assertRaises(IntegrityError):
            Category.objects.create(name='Food')

    def test_category_defaults(self):
        """Should use default values for icon, color, budget."""
        cat = Category.objects.create(name='Misc')
        self.assertEqual(cat.icon, 'ph-package')
        self.assertEqual(cat.color, '#10b981')
        self.assertEqual(cat.monthly_budget, 0)

    def test_category_ordering(self):
        """Should order by name by default."""
        Category.objects.create(name='Zeta')
        Category.objects.create(name='Alpha')
        cats = list(Category.objects.values_list('name', flat=True))
        self.assertEqual(cats, ['Alpha', 'Zeta'])


class ExpenseModelTests(TestCase):
    """Expense model validation."""

    def test_create_expense(self):
        """Should create expense with required fields."""
        exp = Expense.objects.create(
            title='Test', amount=Decimal('50.00'),
            category='Food', expense_date=timezone.now(),
        )
        self.assertIn('Test', str(exp))

    def test_expense_defaults(self):
        """Should use default values for optional fields."""
        exp = Expense.objects.create(
            title='Test', amount=Decimal('50.00'),
            category='Food', expense_date=timezone.now(),
        )
        self.assertEqual(exp.payment_method, 'Cash')
        self.assertEqual(exp.notes, '')
        self.assertFalse(exp.is_recurring)
        self.assertIsNone(exp.recurring_type)
        self.assertEqual(exp.tags, [])

    def test_expense_ordering(self):
        """Should order by expense_date descending."""
        now = timezone.now()
        Expense.objects.create(
            title='Old', amount=10, category='Food',
            expense_date=now - timedelta(days=5),
        )
        Expense.objects.create(
            title='New', amount=20, category='Food',
            expense_date=now,
        )
        first = Expense.objects.first()
        self.assertEqual(first.title, 'New')

    def test_expense_tags_json(self):
        """Should store tags as JSON array."""
        exp = Expense.objects.create(
            title='Tagged', amount=10, category='Food',
            expense_date=timezone.now(), tags=['a', 'b', 'c'],
        )
        exp.refresh_from_db()
        self.assertEqual(exp.tags, ['a', 'b', 'c'])


class BudgetModelTests(TestCase):
    """Budget model validation."""

    def test_create_budget(self):
        """Should create budget."""
        budget = Budget.objects.create(
            month=5, year=2026, total_monthly_budget=Decimal('2500.00'),
        )
        self.assertIn('2500', str(budget))

    def test_budget_unique_month_year(self):
        """Should enforce unique (year, month) constraint."""
        Budget.objects.create(month=5, year=2026, total_monthly_budget=2500)
        with self.assertRaises(IntegrityError):
            Budget.objects.create(month=5, year=2026, total_monthly_budget=3000)

    def test_budget_default_threshold(self):
        """Should default warning_threshold to 80."""
        budget = Budget.objects.create(
            month=6, year=2026, total_monthly_budget=1000,
        )
        self.assertEqual(budget.warning_threshold, 80)

    def test_budget_ordering(self):
        """Should order by year/month descending."""
        Budget.objects.create(month=1, year=2025, total_monthly_budget=1000)
        Budget.objects.create(month=12, year=2026, total_monthly_budget=2000)
        first = Budget.objects.first()
        self.assertEqual(first.year, 2026)


class ReportModelTests(TestCase):
    """Report model validation."""

    def test_create_report(self):
        """Should create report with summary data."""
        now = timezone.now()
        report = Report.objects.create(
            type='custom',
            start_date=now - timedelta(days=30),
            end_date=now,
            format='pdf',
            total_expense=Decimal('500.00'),
            total_income=Decimal('2000.00'),
            net_savings=Decimal('1500.00'),
        )
        self.assertIn('custom', str(report))

    def test_report_default_format(self):
        """Should default format to 'pdf'."""
        now = timezone.now()
        report = Report.objects.create(
            type='monthly',
            start_date=now - timedelta(days=30),
            end_date=now,
        )
        self.assertEqual(report.format, 'pdf')

    def test_report_ordering(self):
        """Should order by created_at descending."""
        now = timezone.now()
        Report.objects.create(
            type='custom', start_date=now - timedelta(days=60),
            end_date=now - timedelta(days=30), format='csv',
        )
        Report.objects.create(
            type='monthly', start_date=now - timedelta(days=30),
            end_date=now, format='pdf',
        )
        first = Report.objects.first()
        self.assertEqual(first.type, 'monthly')
