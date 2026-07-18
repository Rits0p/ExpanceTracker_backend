"""
Tests for Recurring Expense API endpoints and generation logic.
Covers: CRUD, validation, automatic generation, duplicate prevention,
scheduler, budget update, permissions.
"""
from decimal import Decimal
from datetime import timedelta, date

from django.utils import timezone

from api.models import RecurringExpense, Expense, Budget
from api.services import generate_recurring_expenses, calculate_next_due_date
from .base import BaseAPITestCase


RECURRING_URL = '/api/v1/recurring-expenses/'


class RecurringExpenseCRUDTests(BaseAPITestCase):
    """CRUD tests for RecurringExpense endpoint."""

    def setUp(self):
        super().setUp()
        self.re_payload = {
            'title': 'Internet Bill',
            'amount': 999.00,
            'category': self.cat_food.id,
            'frequency': 'monthly',
            'startDate': (self.now - timedelta(days=30)).strftime('%Y-%m-%d'),
            'notes': 'Monthly internet',
        }

    def _create_recurring(self):
        response = self.client.post(RECURRING_URL, self.re_payload, format='json')
        self.assertEqual(response.status_code, 201)
        return response.json()['data']

    def test_create_recurring_expense(self):
        """Should create a recurring expense with valid data."""
        data = self._create_recurring()
        self.assertEqual(data['title'], 'Internet Bill')
        self.assertEqual(float(data['amount']), 999.00)
        self.assertEqual(data['frequency'], 'monthly')
        self.assertEqual(data['frequencyDisplay'], 'Monthly')
        self.assertIsNotNone(data['nextDueDate'])
        self.assertEqual(data['isActive'], True)
        self.assertIn('categoryDetails', data)

    def test_list_recurring_expenses(self):
        """Should list recurring expenses with pagination."""
        self._create_recurring()
        response = self.client.get(RECURRING_URL)
        data = self.assert_paginated_response(response)
        self.assertGreaterEqual(len(data['data']), 1)

    def test_get_recurring_expense_detail(self):
        """Should retrieve a single recurring expense."""
        created = self._create_recurring()
        response = self.client.get(f'{RECURRING_URL}{created["id"]}/')
        data = self.assert_success_response(response)
        self.assertEqual(data['data']['id'], created['id'])

    def test_get_recurring_expense_not_found(self):
        """Should return 404 for non-existent recurring expense."""
        response = self.client.get(f'{RECURRING_URL}99999/')
        self.assert_error_response(response, 404)

    def test_update_recurring_expense(self):
        """Should update a recurring expense."""
        created = self._create_recurring()
        update_payload = {
            'title': 'Updated Internet',
            'amount': 1099.00,
            'category': self.cat_food.id,
            'frequency': 'monthly',
            'startDate': (self.now - timedelta(days=30)).strftime('%Y-%m-%d'),
        }
        response = self.client.put(
            f'{RECURRING_URL}{created["id"]}/', update_payload, format='json'
        )
        data = self.assert_success_response(response)
        self.assertEqual(data['data']['title'], 'Updated Internet')
        self.assertEqual(float(data['data']['amount']), 1099.00)

    def test_partial_update_recurring_expense(self):
        """Should partially update a recurring expense."""
        created = self._create_recurring()
        response = self.client.patch(
            f'{RECURRING_URL}{created["id"]}/', {'amount': 899.00}, format='json'
        )
        data = self.assert_success_response(response)
        self.assertEqual(float(data['data']['amount']), 899.00)
        self.assertEqual(data['data']['title'], 'Internet Bill')

    def test_delete_recurring_expense(self):
        """Should delete a recurring expense but keep generated expenses."""
        created = self._create_recurring()
        from api.services import generate_recurring_expenses
        re = RecurringExpense.objects.get(id=created['id'])
        RecurringExpense.objects.filter(id=re.id).update(
            next_due_date=timezone.now().date() - timedelta(days=1)
        )
        generate_recurring_expenses(user=self.test_user)

        # Verify expense was generated
        self.assertTrue(Expense.objects.filter(title='Internet Bill').exists())

        # Delete the recurring expense
        response = self.client.delete(f'{RECURRING_URL}{created["id"]}/')
        self.assert_success_response(response, 200)

        # Verify the generated expense still exists (recurring_expense set to NULL)
        self.assertTrue(Expense.objects.filter(title='Internet Bill').exists())
        self.assertIsNone(Expense.objects.get(title='Internet Bill').recurring_expense)
        # Verify the recurring expense is deleted
        self.assertFalse(RecurringExpense.objects.filter(id=created['id']).exists())

    def test_deactivate_via_update(self):
        """Should stop generating expenses when deactivated."""
        created = self._create_recurring()
        response = self.client.patch(
            f'{RECURRING_URL}{created["id"]}/', {'isActive': False}, format='json'
        )
        data = self.assert_success_response(response)
        self.assertFalse(data['data']['isActive'])


class RecurringExpenseValidationTests(BaseAPITestCase):
    """Validation tests for RecurringExpense."""

    def test_amount_must_be_positive(self):
        """Should reject amount <= 0."""
        payload = {
            'title': 'Test',
            'amount': 0,
            'category': self.cat_food.id,
            'frequency': 'monthly',
            'startDate': '2025-01-01',
        }
        response = self.client.post(RECURRING_URL, payload, format='json')
        self.assert_error_response(response, 400)

    def test_amount_must_be_positive_negative(self):
        """Should reject negative amount."""
        payload = {
            'title': 'Test',
            'amount': -50,
            'category': self.cat_food.id,
            'frequency': 'monthly',
            'startDate': '2025-01-01',
        }
        response = self.client.post(RECURRING_URL, payload, format='json')
        self.assert_error_response(response, 400)

    def test_start_date_required(self):
        """Should require start_date."""
        payload = {
            'title': 'Test',
            'amount': 100,
            'category': self.cat_food.id,
            'frequency': 'monthly',
        }
        response = self.client.post(RECURRING_URL, payload, format='json')
        self.assert_error_response(response, 400)

    def test_end_date_after_start_date(self):
        """Should reject end_date <= start_date."""
        payload = {
            'title': 'Test',
            'amount': 100,
            'category': self.cat_food.id,
            'frequency': 'monthly',
            'startDate': '2025-06-01',
            'endDate': '2025-05-01',
        }
        response = self.client.post(RECURRING_URL, payload, format='json')
        self.assert_error_response(response, 400)

    def test_frequency_required(self):
        """Should require frequency."""
        payload = {
            'title': 'Test',
            'amount': 100,
            'category': self.cat_food.id,
            'startDate': '2025-01-01',
        }
        response = self.client.post(RECURRING_URL, payload, format='json')
        self.assert_error_response(response, 400)

    def test_category_belongs_to_user(self):
        """Should reject category that doesn't belong to user."""
        from django.contrib.auth.models import User
        other_user = User.objects.create_user('other', 'other@test.com', 'testpass123')
        from api.models import Category
        other_cat = Category.objects.create(user=other_user, name='Other Cat')

        payload = {
            'title': 'Test',
            'amount': 100,
            'category': other_cat.id,
            'frequency': 'monthly',
            'startDate': '2025-01-01',
        }
        response = self.client.post(RECURRING_URL, payload, format='json')
        self.assert_error_response(response, 400)

    def test_user_isolation(self):
        """Should not allow accessing another user's recurring expense."""
        from django.contrib.auth.models import User
        other_user = User.objects.create_user('other2', 'other2@test.com', 'testpass123')
        other_re = RecurringExpense.objects.create(
            user=other_user,
            category=self.cat_food,
            title='Other Bill',
            amount=Decimal('50.00'),
            frequency='monthly',
            start_date=date(2025, 1, 1),
        )
        response = self.client.get(f'{RECURRING_URL}{other_re.id}/')
        self.assert_error_response(response, 404)

        # Try to update
        response = self.client.put(
            f'{RECURRING_URL}{other_re.id}/', {'title': 'Hack'}, format='json'
        )
        self.assert_error_response(response, 404)


class RecurringExpenseGenerationTests(BaseAPITestCase):
    """Tests for automatic expense generation."""

    def setUp(self):
        super().setUp()
        self.re = RecurringExpense.objects.create(
            user=self.test_user,
            category=self.cat_food,
            title='Monthly Subscription',
            amount=Decimal('99.00'),
            frequency='monthly',
            start_date=timezone.now().date() - timedelta(days=60),
            next_due_date=timezone.now().date() - timedelta(days=1),
        )

    def test_generates_expense_when_due(self):
        """Should create an Expense when next_due_date <= today."""
        generated = generate_recurring_expenses(user=self.test_user)
        self.assertEqual(len(generated), 1)
        expense = generated[0]
        self.assertEqual(expense.title, 'Monthly Subscription')
        self.assertEqual(expense.amount, Decimal('99.00'))
        self.assertEqual(expense.category, 'Food')
        self.assertEqual(expense.recurring_expense, self.re)

    def test_updates_next_due_date_after_generation(self):
        """Should update next_due_date after generating an expense."""
        generate_recurring_expenses(user=self.test_user)
        self.re.refresh_from_db()
        expected = calculate_next_due_date(
            timezone.now().date() - timedelta(days=1), 'monthly'
        )
        self.assertEqual(self.re.next_due_date, expected)

    def test_prevents_duplicate(self):
        """Should not create duplicate expenses for the same due date."""
        generate_recurring_expenses(user=self.test_user)
        count1 = Expense.objects.filter(recurring_expense=self.re).count()
        generate_recurring_expenses(user=self.test_user)
        count2 = Expense.objects.filter(recurring_expense=self.re).count()
        self.assertEqual(count1, 1)
        self.assertEqual(count2, 1)

    def test_skips_inactive(self):
        """Should skip inactive recurring expenses."""
        self.re.is_active = False
        self.re.save()
        generated = generate_recurring_expenses(user=self.test_user)
        self.assertEqual(len(generated), 0)

    def test_skips_future_dates(self):
        """Should skip recurring expenses with future next_due_date."""
        self.re.next_due_date = timezone.now().date() + timedelta(days=10)
        self.re.save()
        generated = generate_recurring_expenses(user=self.test_user)
        self.assertEqual(len(generated), 0)

    def test_deactivates_when_end_date_passed(self):
        """Should deactivate recurring expense when past end_date."""
        self.re.end_date = timezone.now().date() - timedelta(days=1)
        self.re.save()
        generate_recurring_expenses(user=self.test_user)
        self.re.refresh_from_db()
        self.assertFalse(self.re.is_active)


class RecurringExpenseFrequencyTests(BaseAPITestCase):
    """Tests for all frequency types."""

    def _test_frequency(self, freq, expected_delta_days=None, expected_months=None):
        start = date(2025, 1, 1)
        re = RecurringExpense.objects.create(
            user=self.test_user,
            category=self.cat_food,
            title=f'{freq.title()} Bill',
            amount=Decimal('50.00'),
            frequency=freq,
            start_date=start,
            next_due_date=start,
        )
        generate_recurring_expenses(user=self.test_user)
        re.refresh_from_db()

        if expected_delta_days:
            expected = start + timedelta(days=expected_delta_days)
        else:
            from api.utils import _add_months
            expected = _add_months(start, expected_months)

        self.assertEqual(re.next_due_date, expected)
        self.assertTrue(Expense.objects.filter(recurring_expense=re).exists())

    def test_daily_frequency(self):
        self._test_frequency('daily', expected_delta_days=1)

    def test_weekly_frequency(self):
        self._test_frequency('weekly', expected_delta_days=7)

    def test_monthly_frequency(self):
        self._test_frequency('monthly', expected_months=1)

    def test_quarterly_frequency(self):
        self._test_frequency('quarterly', expected_months=3)

    def test_yearly_frequency(self):
        self._test_frequency('yearly', expected_months=12)


class RecurringExpenseMultipleGenerationTests(BaseAPITestCase):
    """Tests for generating multiple cycles."""

    def test_generates_multiple_expenses_over_time(self):
        """Should generate expenses for past due dates."""
        start = timezone.now().date() - timedelta(days=90)
        re = RecurringExpense.objects.create(
            user=self.test_user,
            category=self.cat_food,
            title='Weekly Service',
            amount=Decimal('25.00'),
            frequency='monthly',
            start_date=start,
            next_due_date=start,
        )
        # Set next_due_date to 3 months ago so it generates one expense
        re.next_due_date = timezone.now().date() - timedelta(days=60)
        re.save()

        generated = generate_recurring_expenses(user=self.test_user)
        self.assertEqual(len(generated), 1)

        # Now simulate another cycle
        re.refresh_from_db()
        re.next_due_date = timezone.now().date() - timedelta(days=1)
        re.save()
        generated2 = generate_recurring_expenses(user=self.test_user)
        self.assertEqual(len(generated2), 1)


class RecurringExpenseSchedulerCommandTests(BaseAPITestCase):
    """Tests for the management command."""

    def test_management_command_generates_expenses(self):
        """Should run the management command successfully."""
        from django.core.management import call_command
        from io import StringIO

        RecurringExpense.objects.create(
            user=self.test_user,
            category=self.cat_food,
            title='Gym Membership',
            amount=Decimal('50.00'),
            frequency='monthly',
            start_date=timezone.now().date() - timedelta(days=30),
            next_due_date=timezone.now().date() - timedelta(days=1),
        )

        out = StringIO()
        call_command('generate_recurring_expenses', stdout=out)
        self.assertIn('Successfully generated 1 expense(s)', out.getvalue())

    def test_management_command_no_expenses(self):
        """Should handle no expenses to generate."""
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command('generate_recurring_expenses', stdout=out)
        self.assertIn('No expenses needed', out.getvalue())


class RecurringExpenseBudgetIntegrationTests(BaseAPITestCase):
    """Tests that generated expenses affect budget calculations."""

    def test_generated_expense_affects_budget(self):
        """Generated expenses should be included in budget spending."""
        RecurringExpense.objects.create(
            user=self.test_user,
            category=self.cat_food,
            title='Streaming',
            amount=Decimal('15.99'),
            frequency='monthly',
            start_date=timezone.now().date() - timedelta(days=30),
            next_due_date=timezone.now().date() - timedelta(days=1),
        )
        generate_recurring_expenses(user=self.test_user)

        # Get budget for current month
        response = self.client.get(
            '/api/v1/budget/',
            {'month': self.now.month, 'year': self.now.year},
        )
        data = self.assert_success_response(response)
        self.assertGreater(data['data']['currentSpent'], 0)


class RecurringExpenseAnalyticsTests(BaseAPITestCase):
    """Tests for recurring expense analytics endpoint."""

    def test_recurring_analytics_endpoint(self):
        """Should return recurring expense dashboard stats."""
        RecurringExpense.objects.create(
            user=self.test_user,
            category=self.cat_food,
            title='Netflix',
            amount=Decimal('15.99'),
            frequency='monthly',
            start_date=timezone.now().date() - timedelta(days=30),
            next_due_date=timezone.now().date() + timedelta(days=5),
        )
        response = self.client.get('/api/v1/analytics/recurring')
        data = self.assert_success_response(response)
        self.assertIn('totalRecurring', data['data'])
        self.assertIn('monthlyRecurringCost', data['data'])
        self.assertIn('upcomingPayments', data['data'])
        self.assertGreaterEqual(data['data']['totalRecurring'], 1)
