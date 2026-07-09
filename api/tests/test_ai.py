"""
Tests for AI Assistant — covers all CRUD intents via mocked Groq responses.
Each test simulates the Groq LLM returning a specific JSON intent and verifies
the backend correctly executes the corresponding database operation.
"""
import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.utils import timezone

from api.tests.base import BaseAPITestCase
from api.models import Expense, Budget, Category, UserSettings


def _mock_groq_response(intent, message, data):
    """Helper to create a mock Groq API response."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "intent": intent,
                        "message": message,
                        "data": data,
                    })
                }
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()
    return mock_response


AI_ENDPOINT = '/api/v1/ai/assistant'


class AIAssistantTests(BaseAPITestCase):
    """Tests for the AIAssistantView covering all supported intents."""

    def test_ai_assistant_returns_error_when_no_input(self):
        """POST with no text/audio/image returns 400."""
        response = self.client.post(AI_ENDPOINT, {}, format='multipart')
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn("Provide 'text', 'audio', or 'image'", data['message'])

    @patch('api.views.ai_views.requests.post')
    def test_ai_assistant_text_post_returns_ai_response(self, mock_post):
        """POST with text returns AI-generated response (none intent)."""
        mock_post.return_value = _mock_groq_response(
            "none", "Hello from AI", {}
        )

        response = self.client.post(AI_ENDPOINT, {'text': 'Hello AI'}, format='multipart')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['message'], 'Hello from AI')
        self.assertIsNone(data['data']['action'])
        mock_post.assert_called_once()

    # ── EXPENSE CRUD ──────────────────────────────────────────────────

    @patch('api.views.ai_views.requests.post')
    def test_add_expense_via_ai(self, mock_post):
        """AI add_expense intent creates a new expense."""
        mock_post.return_value = _mock_groq_response(
            "add_expense",
            "Added **Lunch** — ₹350",
            {
                "title": "Lunch",
                "amount": 350,
                "category": "Food",
                "payment_method": "UPI",
                "expense_date": timezone.now().isoformat(),
            }
        )

        count_before = Expense.objects.filter(user=self.test_user).count()
        response = self.client.post(
            AI_ENDPOINT, {'text': 'I spent 350 on lunch via UPI'}, format='multipart'
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['crud_type'], 'created')
        self.assertIsNotNone(data['data']['crud_record'])
        self.assertEqual(data['data']['crud_record']['title'], 'Lunch')
        self.assertEqual(
            Expense.objects.filter(user=self.test_user).count(),
            count_before + 1,
        )

    @patch('api.views.ai_views.requests.post')
    def test_edit_expense_via_ai(self, mock_post):
        """AI edit_expense intent updates an existing expense."""
        mock_post.return_value = _mock_groq_response(
            "edit_expense",
            "Updated **Grocery Shopping** amount to ₹200",
            {
                "search": "Grocery",
                "fields": {"amount": 200},
            }
        )

        response = self.client.post(
            AI_ENDPOINT, {'text': 'Change grocery amount to 200'}, format='multipart'
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['crud_type'], 'updated')
        self.expense1.refresh_from_db()
        self.assertEqual(self.expense1.amount, Decimal('200.00'))

    @patch('api.views.ai_views.requests.post')
    def test_edit_expense_by_id_via_ai(self, mock_post):
        """AI edit_expense intent with ID-based lookup."""
        mock_post.return_value = _mock_groq_response(
            "edit_expense",
            "Updated expense",
            {
                "id": self.expense2.id,
                "fields": {"amount": 25},
            }
        )

        response = self.client.post(
            AI_ENDPOINT, {'text': 'Change Netflix to 25'}, format='multipart'
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['data']['crud_type'], 'updated')
        self.expense2.refresh_from_db()
        self.assertEqual(self.expense2.amount, Decimal('25.00'))

    @patch('api.views.ai_views.requests.post')
    def test_delete_expense_via_ai(self, mock_post):
        """AI del_expense intent deletes an expense."""
        mock_post.return_value = _mock_groq_response(
            "del_expense",
            "Deleted **Uber Rides**",
            {"search": "Uber"}
        )

        count_before = Expense.objects.filter(user=self.test_user).count()
        response = self.client.post(
            AI_ENDPOINT, {'text': 'Delete my Uber expense'}, format='multipart'
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['data']['crud_type'], 'deleted')
        self.assertEqual(
            Expense.objects.filter(user=self.test_user).count(),
            count_before - 1,
        )

    @patch('api.views.ai_views.requests.post')
    def test_delete_expense_not_found(self, mock_post):
        """AI del_expense with non-existent title returns error message."""
        mock_post.return_value = _mock_groq_response(
            "del_expense",
            "Deleted expense",
            {"search": "NonExistentExpenseXYZ"}
        )

        response = self.client.post(
            AI_ENDPOINT, {'text': 'Delete NonExistentExpenseXYZ'}, format='multipart'
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("No expense matching", data['data']['message'])

    @patch('api.views.ai_views.requests.post')
    def test_list_expenses_via_ai(self, mock_post):
        """AI list_expenses intent returns expense list."""
        mock_post.return_value = _mock_groq_response(
            "list_expenses",
            "Here are your expenses",
            {"limit": 10}
        )

        response = self.client.post(
            AI_ENDPOINT, {'text': 'Show my expenses'}, format='multipart'
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Expenses", data['data']['message'])

    @patch('api.views.ai_views.requests.post')
    def test_list_expenses_with_category_filter(self, mock_post):
        """AI list_expenses with category filter returns filtered results."""
        mock_post.return_value = _mock_groq_response(
            "list_expenses",
            "Food expenses",
            {"category": "Food", "limit": 10}
        )

        response = self.client.post(
            AI_ENDPOINT, {'text': 'Show my food expenses'}, format='multipart'
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])

    # ── BUDGET CRUD ───────────────────────────────────────────────────

    @patch('api.views.ai_views.requests.post')
    def test_set_budget_via_ai(self, mock_post):
        """AI set_budget intent creates/updates a budget."""
        mock_post.return_value = _mock_groq_response(
            "set_budget",
            "Updated your monthly budget to ₹30,000",
            {"total": 30000, "weekly": 7500, "daily": 1000}
        )

        response = self.client.post(
            AI_ENDPOINT, {'text': 'Set my budget to 30000'}, format='multipart'
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(data['data']['crud_type'], ['created', 'updated'])
        self.assertIsNotNone(data['data']['crud_record'])
        self.assertEqual(data['data']['crud_record']['type'], 'budget')

    @patch('api.views.ai_views.requests.post')
    def test_get_budget_via_ai(self, mock_post):
        """AI get_budget intent returns current month budget details."""
        mock_post.return_value = _mock_groq_response(
            "get_budget",
            "Here's your budget",
            {}
        )

        response = self.client.post(
            AI_ENDPOINT, {'text': 'What is my budget this month?'}, format='multipart'
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertIn("Budget", data['data']['message'])

    @patch('api.views.ai_views.requests.post')
    def test_delete_budget_via_ai(self, mock_post):
        """AI del_budget intent deletes a budget."""
        now = timezone.now()
        mock_post.return_value = _mock_groq_response(
            "del_budget",
            "Deleted budget",
            {"month": now.month, "year": now.year}
        )

        response = self.client.post(
            AI_ENDPOINT, {'text': 'Delete my budget for this month'}, format='multipart'
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['data']['crud_type'], 'deleted')
        self.assertFalse(
            Budget.objects.filter(
                user=self.test_user, month=now.month, year=now.year
            ).exists()
        )

    @patch('api.views.ai_views.requests.post')
    def test_list_budgets_via_ai(self, mock_post):
        """AI list_budgets intent returns all budgets."""
        mock_post.return_value = _mock_groq_response(
            "list_budgets",
            "Here are your budgets",
            {}
        )

        response = self.client.post(
            AI_ENDPOINT, {'text': 'Show all my budgets'}, format='multipart'
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Budgets", data['data']['message'])

    # ── CATEGORY CRUD ─────────────────────────────────────────────────

    @patch('api.views.ai_views.requests.post')
    def test_add_category_via_ai(self, mock_post):
        """AI add_category intent creates a new category."""
        mock_post.return_value = _mock_groq_response(
            "add_category",
            "Created category **Travel**",
            {"name": "Travel", "monthly_budget": 5000}
        )

        count_before = Category.objects.filter(user=self.test_user).count()
        response = self.client.post(
            AI_ENDPOINT,
            {'text': 'Create a Travel category with 5000 budget'},
            format='multipart'
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['data']['crud_type'], 'created')
        self.assertEqual(
            Category.objects.filter(user=self.test_user).count(),
            count_before + 1,
        )
        self.assertTrue(
            Category.objects.filter(user=self.test_user, name__iexact='Travel').exists()
        )

    @patch('api.views.ai_views.requests.post')
    def test_add_duplicate_category_via_ai(self, mock_post):
        """AI add_category for existing category returns info message."""
        mock_post.return_value = _mock_groq_response(
            "add_category",
            "Category already exists",
            {"name": "Food"}
        )

        response = self.client.post(
            AI_ENDPOINT, {'text': 'Create Food category'}, format='multipart'
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("already exists", data['data']['message'])

    @patch('api.views.ai_views.requests.post')
    def test_edit_category_via_ai(self, mock_post):
        """AI edit_category intent updates a category budget."""
        mock_post.return_value = _mock_groq_response(
            "edit_category",
            "Updated category **Food** budget",
            {
                "name": "Food",
                "fields": {"monthly_budget": 800}
            }
        )

        response = self.client.post(
            AI_ENDPOINT,
            {'text': 'Change Food category budget to 800'},
            format='multipart'
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['data']['crud_type'], 'updated')
        self.cat_food.refresh_from_db()
        self.assertEqual(self.cat_food.monthly_budget, Decimal('800.00'))

    @patch('api.views.ai_views.requests.post')
    def test_delete_category_via_ai(self, mock_post):
        """AI del_category intent deletes a category."""
        mock_post.return_value = _mock_groq_response(
            "del_category",
            "Deleted category **Entertainment**",
            {"name": "Entertainment"}
        )

        response = self.client.post(
            AI_ENDPOINT,
            {'text': 'Delete Entertainment category'},
            format='multipart'
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['data']['crud_type'], 'deleted')
        self.assertFalse(
            Category.objects.filter(user=self.test_user, name='Entertainment').exists()
        )

    @patch('api.views.ai_views.requests.post')
    def test_delete_category_not_found(self, mock_post):
        """AI del_category for non-existent category returns error."""
        mock_post.return_value = _mock_groq_response(
            "del_category",
            "Deleted category",
            {"name": "NonExistentCategory"}
        )

        response = self.client.post(
            AI_ENDPOINT,
            {'text': 'Delete NonExistentCategory'},
            format='multipart'
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("not found", data['data']['message'])

    @patch('api.views.ai_views.requests.post')
    def test_list_categories_via_ai(self, mock_post):
        """AI list_categories intent returns all categories."""
        mock_post.return_value = _mock_groq_response(
            "list_categories",
            "Here are your categories",
            {}
        )

        response = self.client.post(
            AI_ENDPOINT, {'text': 'List my categories'}, format='multipart'
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Categories", data['data']['message'])

    # ── THEME CHANGE ──────────────────────────────────────────────────

    @patch('api.views.ai_views.requests.post')
    def test_change_theme_to_light_via_ai(self, mock_post):
        """AI change_theme intent switches to light mode."""
        mock_post.return_value = _mock_groq_response(
            "change_theme",
            "🎨 Theme changed to **light** mode.",
            {"theme": "light"}
        )

        response = self.client.post(
            AI_ENDPOINT, {'text': 'Switch to light mode'}, format='multipart'
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['data']['crud_type'], 'change_theme')
        self.assertEqual(data['data']['crud_record']['theme'], 'light')

        # Verify DB was updated
        us = UserSettings.objects.filter(user=self.test_user).first()
        if us:
            self.assertEqual(us.theme, 'light')

    @patch('api.views.ai_views.requests.post')
    def test_change_theme_to_dark_via_ai(self, mock_post):
        """AI change_theme intent switches to dark mode."""
        # First set to light
        UserSettings.objects.get_or_create(
            user=self.test_user, defaults={'theme': 'light'}
        )

        mock_post.return_value = _mock_groq_response(
            "change_theme",
            "🎨 Theme changed to **dark** mode.",
            {"theme": "dark"}
        )

        response = self.client.post(
            AI_ENDPOINT, {'text': 'Switch to dark mode'}, format='multipart'
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['data']['crud_type'], 'change_theme')
        self.assertEqual(data['data']['crud_record']['theme'], 'dark')

        us = UserSettings.objects.get(user=self.test_user)
        self.assertEqual(us.theme, 'dark')

    # ── EDGE CASES ────────────────────────────────────────────────────

    @patch('api.views.ai_views.requests.post')
    def test_ai_handles_non_json_response(self, mock_post):
        """AI responds with plain text instead of JSON — handled gracefully."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "I'm not sure what you mean."}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        response = self.client.post(
            AI_ENDPOINT, {'text': 'gibberish input'}, format='multipart'
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        # Should return the raw text as message
        self.assertIn("not sure", data['data']['message'])

    @patch('api.views.ai_views.requests.post')
    def test_ai_handles_markdown_fenced_json(self, mock_post):
        """AI wraps JSON in ```json fences — should be stripped."""
        content = '```json\n{"intent": "none", "message": "Hello!", "data": {}}\n```'
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": content}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        response = self.client.post(
            AI_ENDPOINT, {'text': 'Hello'}, format='multipart'
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['data']['message'], 'Hello!')

    @patch('api.views.ai_views.requests.post')
    def test_dashboard_command_bypasses_groq(self, mock_post):
        """The special dashboard command is handled locally without Groq call."""
        response = self.client.post(
            AI_ENDPOINT,
            {'text': '📊 Show me my dashboard'},
            format='multipart'
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertIn("financial overview", data['data']['message'])
        mock_post.assert_not_called()
