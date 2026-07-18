"""
Tests for Expense API endpoints.
Covers: CRUD, pagination, filtering, sorting, search, recurring, receipt upload.
"""
import tempfile
from decimal import Decimal
from datetime import timedelta
from PIL import Image
import io

from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

from api.models import Expense
from .base import BaseAPITestCase


class ExpenseListTests(BaseAPITestCase):
    """GET /api/v1/expenses/ — listing, pagination, filtering, sorting."""

    def test_list_expenses_returns_paginated_response(self):
        """Should return paginated expense list with meta."""
        response = self.client.get('/api/v1/expenses/')
        data = self.assert_paginated_response(response, expected_total=4)
        self.assertEqual(len(data['data']), 4)

    def test_list_expenses_pagination(self):
        """Should correctly paginate with page and limit params."""
        response = self.client.get('/api/v1/expenses/', {'page': 1, 'limit': 2})
        data = self.assert_paginated_response(response, expected_total=4)
        self.assertEqual(len(data['data']), 2)
        self.assertTrue(data['meta']['hasNextPage'])
        self.assertFalse(data['meta']['hasPrevPage'])

        # Page 2
        response = self.client.get('/api/v1/expenses/', {'page': 2, 'limit': 2})
        data = self.assert_paginated_response(response)
        self.assertEqual(len(data['data']), 2)
        self.assertFalse(data['meta']['hasNextPage'])
        self.assertTrue(data['meta']['hasPrevPage'])

    def test_list_expenses_filter_by_category(self):
        """Should filter expenses by category."""
        response = self.client.get('/api/v1/expenses/', {'category': 'Food'})
        data = self.assert_paginated_response(response, expected_total=2)
        for expense in data['data']:
            self.assertEqual(expense['category'], 'Food')

    def test_list_expenses_filter_by_payment_method(self):
        """Should filter expenses by payment method."""
        response = self.client.get('/api/v1/expenses/', {'paymentMethod': 'Credit Card'})
        data = self.assert_paginated_response(response)
        for expense in data['data']:
            self.assertEqual(expense['paymentMethod'], 'Credit Card')

    def test_list_expenses_filter_by_date_range(self):
        """Should filter expenses within a date range."""
        start = (self.now - timedelta(days=2)).strftime('%Y-%m-%d')
        end = self.now.strftime('%Y-%m-%d')
        response = self.client.get('/api/v1/expenses/', {'startDate': start, 'endDate': end})
        data = self.assert_paginated_response(response)
        self.assertGreater(len(data['data']), 0)

    def test_list_expenses_filter_by_amount_range(self):
        """Should filter expenses by min/max amount."""
        response = self.client.get('/api/v1/expenses/', {'minAmount': 30, 'maxAmount': 100})
        data = self.assert_paginated_response(response)
        for expense in data['data']:
            self.assertGreaterEqual(expense['amount'], 30)
            self.assertLessEqual(expense['amount'], 100)

    def test_list_expenses_filter_by_recurring(self):
        """Should filter recurring expenses."""
        response = self.client.get('/api/v1/expenses/', {'isRecurring': 'true'})
        data = self.assert_paginated_response(response, expected_total=1)
        self.assertTrue(data['data'][0]['isRecurring'])

    def test_list_expenses_search(self):
        """Should search expenses by title/description/notes."""
        response = self.client.get('/api/v1/expenses/', {'search': 'grocery'})
        data = self.assert_paginated_response(response)
        self.assertEqual(len(data['data']), 1)
        self.assertIn('Grocery', data['data'][0]['title'])

    def test_list_expenses_sort_by_amount_asc(self):
        """Should sort expenses by amount ascending."""
        response = self.client.get('/api/v1/expenses/', {'sortBy': 'amount', 'sortOrder': 'asc'})
        data = self.assert_paginated_response(response)
        amounts = [e['amount'] for e in data['data']]
        self.assertEqual(amounts, sorted(amounts))

    def test_list_expenses_sort_by_amount_desc(self):
        """Should sort expenses by amount descending."""
        response = self.client.get('/api/v1/expenses/', {'sortBy': 'amount', 'sortOrder': 'desc'})
        data = self.assert_paginated_response(response)
        amounts = [e['amount'] for e in data['data']]
        self.assertEqual(amounts, sorted(amounts, reverse=True))

    def test_list_expenses_default_sort_is_date_desc(self):
        """Should default-sort by expense_date descending."""
        response = self.client.get('/api/v1/expenses/')
        data = self.assert_paginated_response(response)
        dates = [e['expenseDate'] for e in data['data']]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_list_expenses_response_format(self):
        """Should include _id alias and camelCase fields."""
        response = self.client.get('/api/v1/expenses/')
        data = self.assert_paginated_response(response)
        expense = data['data'][0]
        self.assertIn('_id', expense)
        self.assertIn('expenseDate', expense)
        self.assertIn('paymentMethod', expense)
        self.assertIn('isRecurring', expense)
        self.assertIn('createdAt', expense)
        self.assertEqual(expense['_id'], str(expense['id']))


class ExpenseCreateTests(BaseAPITestCase):
    """POST /api/v1/expenses/ — creating expenses."""

    def test_create_expense_success(self):
        """Should create expense and return 201."""
        payload = {
            'title': 'Coffee & Snacks',
            'amount': '24.50',
            'category': 'Food',
            'paymentMethod': 'Cash',
            'expenseDate': self.now.isoformat(),
        }
        response = self.client.post('/api/v1/expenses/', payload, format='json')
        data = self.assert_success_response(response, 201)
        self.assertEqual(data['message'], 'Expense created successfully')
        self.assertEqual(data['data']['title'], 'Coffee & Snacks')
        self.assertEqual(data['data']['amount'], 24.50)
        self.assertEqual(Expense.objects.count(), 5)

    def test_create_expense_with_tags(self):
        """Should create expense with tags array."""
        payload = {
            'title': 'Protein Shake',
            'amount': '8.00',
            'category': 'Food',
            'expenseDate': self.now.isoformat(),
            'tags': ['health', 'supplements'],
        }
        response = self.client.post('/api/v1/expenses/', payload, format='json')
        data = self.assert_success_response(response, 201)
        self.assertEqual(data['data']['tags'], ['health', 'supplements'])

    def test_create_expense_with_recurring(self):
        """Should create recurring expense."""
        payload = {
            'title': 'Gym Membership',
            'amount': '50.00',
            'category': 'Health',
            'expenseDate': self.now.isoformat(),
            'isRecurring': True,
            'recurringType': 'monthly',
        }
        response = self.client.post('/api/v1/expenses/', payload, format='json')
        data = self.assert_success_response(response, 201)
        self.assertTrue(data['data']['isRecurring'])
        self.assertEqual(data['data']['recurringType'], 'monthly')

    def test_create_expense_missing_required_fields(self):
        """Should return 400 for missing required fields."""
        payload = {'title': 'Incomplete Expense'}
        response = self.client.post('/api/v1/expenses/', payload, format='json')
        self.assert_error_response(response, 400)

    def test_create_expense_missing_title(self):
        """Should return 400 when title is missing."""
        payload = {
            'amount': '50.00',
            'category': 'Food',
            'expenseDate': self.now.isoformat(),
        }
        response = self.client.post('/api/v1/expenses/', payload, format='json')
        self.assert_error_response(response, 400)


class ExpenseDetailTests(BaseAPITestCase):
    """GET/PUT/DELETE /api/v1/expenses/<id>/"""

    def test_get_expense_by_id(self):
        """Should return expense details by ID."""
        response = self.client.get(f'/api/v1/expenses/{self.expense1.id}/')
        data = self.assert_success_response(response)
        self.assertEqual(data['data']['title'], 'Grocery Shopping')
        self.assertEqual(data['data']['amount'], 142.50)

    def test_get_expense_not_found(self):
        """Should return 404 for non-existent expense."""
        response = self.client.get('/api/v1/expenses/99999/')
        self.assert_error_response(response, 404)

    def test_update_expense(self):
        """Should update expense fields."""
        payload = {'title': 'Updated Grocery', 'amount': '160.00'}
        response = self.client.put(
            f'/api/v1/expenses/{self.expense1.id}/', payload, format='json'
        )
        data = self.assert_success_response(response)
        self.assertEqual(data['data']['title'], 'Updated Grocery')
        self.assertEqual(data['data']['amount'], 160.00)
        self.assertEqual(data['message'], 'Expense updated successfully')

    def test_update_expense_partial(self):
        """Should partially update expense (only amount)."""
        payload = {'amount': '200.00'}
        response = self.client.put(
            f'/api/v1/expenses/{self.expense1.id}/', payload, format='json'
        )
        data = self.assert_success_response(response)
        self.assertEqual(data['data']['amount'], 200.00)
        self.assertEqual(data['data']['title'], 'Grocery Shopping')  # unchanged

    def test_update_expense_not_found(self):
        """Should return 404 for updating non-existent expense."""
        response = self.client.put('/api/v1/expenses/99999/', {'title': 'X'}, format='json')
        self.assert_error_response(response, 404)

    def test_delete_expense(self):
        """Should delete expense and return success message."""
        count_before = Expense.objects.count()
        response = self.client.delete(f'/api/v1/expenses/{self.expense1.id}/')
        data = self.assert_success_response(response)
        self.assertEqual(data['message'], 'Expense deleted successfully')
        self.assertEqual(Expense.objects.count(), count_before - 1)

    def test_delete_expense_not_found(self):
        """Should return 404 for deleting non-existent expense."""
        response = self.client.delete('/api/v1/expenses/99999/')
        self.assert_error_response(response, 404)


class ExpenseSearchTests(BaseAPITestCase):
    """GET /api/v1/expenses/search"""

    def test_search_by_title(self):
        """Should find expenses matching title."""
        response = self.client.get('/api/v1/expenses/search', {'q': 'Netflix'})
        data = self.assert_success_response(response)
        self.assertEqual(len(data['data']), 1)
        self.assertEqual(data['data'][0]['title'], 'Netflix Subscription')



    def test_search_by_notes(self):
        """Should find expenses matching notes."""
        response = self.client.get('/api/v1/expenses/search', {'q': 'supermarket'})
        data = self.assert_success_response(response)
        self.assertEqual(len(data['data']), 1)

    def test_search_empty_query_returns_empty_list(self):
        """Should return empty list for empty query."""
        response = self.client.get('/api/v1/expenses/search', {'q': ''})
        data = self.assert_success_response(response)
        self.assertEqual(data['data'], [])

    def test_search_no_results(self):
        """Should return empty list for unmatched query."""
        response = self.client.get('/api/v1/expenses/search', {'q': 'xyznonexistent'})
        data = self.assert_success_response(response)
        self.assertEqual(data['data'], [])

    def test_search_case_insensitive(self):
        """Search should be case-insensitive."""
        response = self.client.get('/api/v1/expenses/search', {'q': 'GROCERY'})
        data = self.assert_success_response(response)
        self.assertGreaterEqual(len(data['data']), 1)

    def test_search_limits_to_20_results(self):
        """Should limit search results to 20."""
        # Create 25 expenses with matching title
        for i in range(25):
            Expense.objects.create(
                title=f'Test Searchable {i}',
                amount=Decimal('10.00'),
                category='Food',
                expense_date=self.now - timedelta(hours=i),
            )
        response = self.client.get('/api/v1/expenses/search', {'q': 'Searchable'})
        data = self.assert_success_response(response)
        self.assertEqual(len(data['data']), 20)


class ExpenseRecurringTests(BaseAPITestCase):
    """GET /api/v1/expenses/recurring"""

    def test_get_recurring_expenses(self):
        """Should return only recurring expenses."""
        response = self.client.get('/api/v1/expenses/recurring')
        data = self.assert_success_response(response)
        self.assertEqual(len(data['data']), 1)
        self.assertTrue(data['data'][0]['isRecurring'])
        self.assertEqual(data['data'][0]['title'], 'Netflix Subscription')

    def test_recurring_empty_when_none_exist(self):
        """Should return empty list when no recurring expenses."""
        Expense.objects.filter(is_recurring=True).delete()
        response = self.client.get('/api/v1/expenses/recurring')
        data = self.assert_success_response(response)
        self.assertEqual(data['data'], [])


class ExpenseReceiptUploadTests(BaseAPITestCase):
    """POST /api/v1/expenses/<id>/receipt"""

    def _create_test_image(self):
        """Create a small in-memory test image."""
        img = Image.new('RGB', (100, 100), color='red')
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG')
        buffer.seek(0)
        return SimpleUploadedFile(
            'test_receipt.jpg', buffer.read(), content_type='image/jpeg'
        )

    def test_upload_receipt_success(self):
        """Should upload receipt image for expense."""
        image = self._create_test_image()
        response = self.client.post(
            f'/api/v1/expenses/{self.expense1.id}/receipt',
            {'receiptImage': image},
            format='multipart',
        )
        data = self.assert_success_response(response)
        self.assertEqual(data['message'], 'Receipt uploaded successfully')
        self.assertIsNotNone(data['data']['receiptImage'])

    def test_upload_receipt_no_file(self):
        """Should return 400 when no file is provided."""
        response = self.client.post(
            f'/api/v1/expenses/{self.expense1.id}/receipt',
            {},
            format='multipart',
        )
        self.assert_error_response(response, 400)

    def test_upload_receipt_expense_not_found(self):
        """Should return 404 for non-existent expense."""
        image = self._create_test_image()
        response = self.client.post(
            '/api/v1/expenses/99999/receipt',
            {'receiptImage': image},
            format='multipart',
        )
        self.assert_error_response(response, 404)


class ExpenseSeedAPITests(BaseAPITestCase):
    """POST /api/v1/expenses/seed"""

    def test_seed_expenses_success(self):
        """Should seed 250 test expenses with available categories."""
        initial_count = Expense.objects.filter(user=self.test_user).count()

        response = self.client.post('/api/v1/expenses/seed', format='json')
        data = self.assert_success_response(response)
        
        self.assertEqual(data['message'], 'Successfully seeded 250 test expenses')
        self.assertEqual(data['data']['count'], 250)

        final_count = Expense.objects.filter(user=self.test_user).count()
        self.assertEqual(final_count, initial_count + 250)
