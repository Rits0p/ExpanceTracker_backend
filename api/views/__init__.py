"""
Views for ExpenseIQ API — Expense endpoints.
Mirrors: /api/v1/expenses/*
"""
import random
from datetime import timedelta
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from django.db.models import Q

from ..models import Expense, Category
from ..serializers import ExpenseSerializer
from ..utils import ApiResponse, get_pagination_params


def normalize_expense_payload(data):
    """Accept either snake_case or camelCase from clients by mapping
    common expense fields to the serializer's camelCase names.
    """
    # Convert QueryDict-like objects to a plain dict with single values
    payload = {}
    try:
        keys = list(data.keys())
    except Exception:
        # If data is a plain dict
        payload = dict(data)
        keys = list(payload.keys())

    if not payload:
        for k in keys:
            payload[k] = data.get(k)

    # mapping snake_case -> camelCase expected by serializer
    mapping = {
        'expense_date': 'expenseDate',
        'payment_method': 'paymentMethod',
        'is_recurring': 'isRecurring',
        'recurring_type': 'recurringType',
        'receipt_image': 'receiptImage',
    }

    for snake, camel in mapping.items():
        if snake in payload and camel not in payload:
            payload[camel] = payload.get(snake)

    return payload


class ExpenseListCreateView(APIView):
    """GET /api/v1/expenses/ — list with filters & pagination
        POST /api/v1/expenses/ — create new expense"""

    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def _normalize_payload(self, data):
        return normalize_expense_payload(data)

    def get(self, request):
        page, limit = get_pagination_params(request.query_params)
        sort_by = request.query_params.get('sortBy', 'expense_date')
        sort_order = request.query_params.get('sortOrder', 'desc')
        category = request.query_params.get('category')
        payment_method = request.query_params.get('paymentMethod')
        search = request.query_params.get('search')
        start_date = request.query_params.get('startDate')
        end_date = request.query_params.get('endDate')
        min_amount = request.query_params.get('minAmount')
        max_amount = request.query_params.get('maxAmount')
        is_recurring = request.query_params.get('isRecurring')

        # Map camelCase sort fields to snake_case
        sort_field_map = {
            'expenseDate': 'expense_date',
            'amount': 'amount',
            'category': 'category',
            'title': 'title',
        }
        sort_field = sort_field_map.get(sort_by, sort_by)
        if sort_field not in ['expense_date', 'amount', 'category', 'title']:
            sort_field = 'expense_date'

        queryset = Expense.objects.filter(user=request.user)

        # Apply filters
        if category:
            queryset = queryset.filter(category=category)
        if payment_method:
            queryset = queryset.filter(payment_method=payment_method)
        if is_recurring is not None and is_recurring != '':
            queryset = queryset.filter(is_recurring=is_recurring.lower() in ('true', '1'))
        if start_date:
            queryset = queryset.filter(expense_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(expense_date__lte=end_date)
        if min_amount:
            queryset = queryset.filter(amount__gte=min_amount)
        if max_amount:
            queryset = queryset.filter(amount__lte=max_amount)
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(notes__icontains=search)
            )

        # Sorting
        ordering = f"{'-' if sort_order == 'desc' else ''}{sort_field}"
        queryset = queryset.order_by(ordering)

        # Pagination
        total = queryset.count()
        offset = (page - 1) * limit
        expenses = queryset[offset:offset + limit]

        serializer = ExpenseSerializer(expenses, many=True)
        return ApiResponse.paginated(serializer.data, page, limit, total)

    def post(self, request):
        normalized = self._normalize_payload(request.data)
        serializer = ExpenseSerializer(data=normalized)
        if serializer.is_valid():
            expense = serializer.save(user=request.user)
            from django.db import transaction
            from ..notifications import notify_budget_status, notify_category_budget_exceeded, notify_large_expense

            transaction.on_commit(
                lambda: (
                    notify_budget_status(request.user, expense),
                    notify_category_budget_exceeded(request.user, expense),
                    notify_large_expense(request.user, expense),
                )
            )
            return ApiResponse.created(
                ExpenseSerializer(expense).data,
                message='Expense created successfully'
            )
        print("DEBUG normalized payload:", normalized)
        print("DEBUG errors:", serializer.errors)
        return ApiResponse.error('Validation failed', 400, serializer.errors)


class ExpenseDetailView(APIView):
    """GET/PUT/DELETE /api/v1/expenses/<id>/"""

    def _get_expense(self, pk):
        try:
            return Expense.objects.get(pk=pk, user=self.request.user)
        except Expense.DoesNotExist:
            return None

    def get(self, request, pk):
        expense = self._get_expense(pk)
        if not expense:
            return ApiResponse.error('Expense not found', 404)
        return ApiResponse.success(ExpenseSerializer(expense).data)

    def put(self, request, pk):
        expense = self._get_expense(pk)
        if not expense:
            return ApiResponse.error('Expense not found', 404)
        normalized = normalize_expense_payload(request.data)
        serializer = ExpenseSerializer(expense, data=normalized, partial=True)
        if serializer.is_valid():
            expense = serializer.save()
            return ApiResponse.success(
                ExpenseSerializer(expense).data,
                message='Expense updated successfully'
            )
        return ApiResponse.error('Validation failed', 400, serializer.errors)

    def delete(self, request, pk):
        expense = self._get_expense(pk)
        if not expense:
            return ApiResponse.error('Expense not found', 404)
        expense.delete()
        return ApiResponse.success(message='Expense deleted successfully')


class ExpenseSearchView(APIView):
    """GET /api/v1/expenses/search?q=..."""

    def get(self, request):
        query = request.query_params.get('q', '')
        if not query:
            return ApiResponse.success([])

        expenses = Expense.objects.filter(user=request.user).filter(
            Q(title__icontains=query) |
            Q(notes__icontains=query)
        ).order_by('-expense_date')[:20]

        serializer = ExpenseSerializer(expenses, many=True)
        return ApiResponse.success(serializer.data)


class ExpenseRecurringView(APIView):
    """GET /api/v1/expenses/recurring"""

    def get(self, request):
        page, limit = get_pagination_params(request.query_params)

        expenses = Expense.objects.filter(user=request.user, is_recurring=True).order_by('-expense_date')
        total = expenses.count()
        offset = (page - 1) * limit
        paginated = expenses[offset:offset + limit]

        serializer = ExpenseSerializer(paginated, many=True)
        return ApiResponse.paginated(serializer.data, page, limit, total)


class ExpenseReceiptUploadView(APIView):
    """POST /api/v1/expenses/<id>/receipt"""
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        try:
            expense = Expense.objects.get(pk=pk, user=request.user)
        except Expense.DoesNotExist:
            return ApiResponse.error('Expense not found', 404)

        receipt = request.FILES.get('receiptImage')
        if not receipt:
            return ApiResponse.error('No file uploaded', 400)

        expense.receipt_image = receipt
        expense.save()
        return ApiResponse.success(
            ExpenseSerializer(expense).data,
            message='Receipt uploaded successfully'
        )


class ExpenseSeedView(APIView):
    """POST /api/v1/expenses/seed — Seeds 250 test expenses for the user."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        
        # Get user's available categories (names)
        user_categories = list(Category.objects.filter(user=user).values_list('name', flat=True))
        
        # If no categories exist, make default ones
        default_categories = ['Food', 'Transport', 'Entertainment', 'Utilities', 'Shopping', 'Health']
        if not user_categories:
            for cat_name in default_categories:
                Category.objects.get_or_create(user=user, name=cat_name)
            user_categories = default_categories
            
        # Seed titles matching category to look realistic
        titles = {
            'Food': ['Groceries', 'Dinner with friends', 'Subway lunch', 'Starbucks Coffee', 'Pizza Hut dinner', 'Fruit basket'],
            'Transport': ['Uber ride', 'Gas refill', 'Metro ticket', 'Train journey', 'Parking ticket', 'Toll toll'],
            'Entertainment': ['Netflix premium', 'Movie ticket', 'Spotify subscription', 'Arcade tokens', 'Video game', 'Concert ticket'],
            'Utilities': ['Electricity bill', 'Water charges', 'Fiber internet bill', 'Mobile network bill', 'Gas bill'],
            'Shopping': ['Winter shoes', 'Cotton T-shirt', 'Jeans wear', 'Book buy', 'Desk lamp', 'Airpods'],
            'Health': ['Medicines', 'Dental clinic', 'Gym monthly fee', 'Eye checkup', 'Vitamins supplements']
        }
        
        payment_methods = ['Credit Card', 'Debit Card', 'Cash', 'Bank Transfer', 'UPI']
        
        expenses_to_create = []
        now = timezone.now()
        
        for i in range(250):
            cat_name = random.choice(user_categories)
            category_titles = titles.get(cat_name, ['Miscellaneous expense', 'Quick shop', 'Utility bill'])
            title = random.choice(category_titles) + f" #{i+1}"
            amount = random.randint(50, 4500)
            method = random.choice(payment_methods)
            
            # Scatter over last 90 days
            days_ago = random.randint(0, 90)
            hours_ago = random.randint(0, 23)
            minutes_ago = random.randint(0, 59)
            expense_date = now - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)
            
            expenses_to_create.append(Expense(
                user=user,
                title=title,
                amount=amount,
                category=cat_name,
                payment_method=method,
                expense_date=expense_date,
                notes=f"Seed transaction #{i+1} for visual pagination testing."
            ))
            
        Expense.objects.bulk_create(expenses_to_create)
        
        return ApiResponse.success(
            data={"count": 250},
            message="Successfully seeded 250 test expenses"
        )
