"""
Views for ExpenseIQ API — Category, Budget, Report endpoints.
Mirrors: /api/v1/categories/*, /api/v1/budget/*, /api/v1/reports/*
"""
import csv
import io
from datetime import datetime, timezone as dt_timezone

from rest_framework.views import APIView
from django.http import HttpResponse
from django.db.models import Sum, Count
from django.utils import timezone

from ..models import Category, Budget, Expense, Report, UserSettings
from ..serializers import CategorySerializer, BudgetSerializer, ReportSerializer, UserSettingsSerializer
from ..utils import ApiResponse, get_start_of_month, get_end_of_month
from django.shortcuts import render
from django.contrib.auth.decorators import login_required


# ═══════════════════════════════════════════
#  CATEGORY VIEWS
# ═══════════════════════════════════════════
class CategoryListCreateView(APIView):
    """GET /api/v1/categories/ — list all categories
       POST /api/v1/categories/ — create new category"""

    def get(self, request):
        categories = Category.objects.filter(user=request.user).order_by('name')
        serializer = CategorySerializer(categories, many=True)
        return ApiResponse.success(serializer.data)

    def post(self, request):
        name = request.data.get('name', '').strip()
        if Category.objects.filter(user=request.user, name__iexact=name).exists():
            return ApiResponse.error('Category already exists', 409)

        serializer = CategorySerializer(data=request.data)
        if serializer.is_valid():
            cat = serializer.save(user=request.user)
            return ApiResponse.created(
                CategorySerializer(cat).data,
                message='Category created'
            )
        return ApiResponse.error('Validation failed', 400, serializer.errors)


class CategoryDetailView(APIView):
    """PUT/DELETE /api/v1/categories/<id>/"""

    def put(self, request, pk):
        try:
            cat = Category.objects.get(pk=pk, user=request.user)
        except Category.DoesNotExist:
            return ApiResponse.error('Category not found', 404)

        serializer = CategorySerializer(cat, data=request.data, partial=True)
        if serializer.is_valid():
            cat = serializer.save()
            return ApiResponse.success(
                CategorySerializer(cat).data,
                message='Category updated'
            )
        return ApiResponse.error('Validation failed', 400, serializer.errors)

    def delete(self, request, pk):
        try:
            cat = Category.objects.get(pk=pk, user=request.user)
        except Category.DoesNotExist:
            return ApiResponse.error('Category not found', 404)
        cat.delete()
        return ApiResponse.success(message='Category deleted')


# ═══════════════════════════════════════════
#  BUDGET VIEWS
# ═══════════════════════════════════════════
class BudgetSetView(APIView):
    """POST /api/v1/budget — set/update monthly budget"""

    def post(self, request):
        month = request.data.get('month')
        year = request.data.get('year')

        if not month or not year:
            return ApiResponse.error('month and year are required', 400)

        existing = Budget.objects.filter(user=request.user, month=int(month), year=int(year)).first()

        total = request.data.get('totalMonthlyBudget')
        if total is None:
            total = existing.total_monthly_budget if existing else 0

        threshold = request.data.get('warningThreshold')
        if threshold is None:
            threshold = existing.warning_threshold if existing else 80

        daily = request.data.get('dailyBudget')
        if daily is None:
            daily = existing.daily_budget if existing else 0

        weekly = request.data.get('weeklyBudget')
        if weekly is None:
            weekly = existing.weekly_budget if existing else 0

        yearly = request.data.get('yearlyBudget')
        if yearly is None:
            yearly = existing.yearly_budget if existing else 0

        budget, _ = Budget.objects.update_or_create(
            user=request.user, month=int(month), year=int(year),
            defaults={
                'total_monthly_budget': total,
                'warning_threshold': threshold,
                'daily_budget': daily,
                'weekly_budget': weekly,
                'yearly_budget': yearly,
            }
        )
        return ApiResponse.success(
            BudgetSerializer(budget).data,
            message='Budget set successfully'
        )


class BudgetGetView(APIView):
    """GET /api/v1/budget?month=&year= — get budget with spending info"""

    def get(self, request):
        month = request.query_params.get('month')
        year = request.query_params.get('year')

        if not month or not year:
            return ApiResponse.error('month and year query params are required', 400)

        try:
            budget = Budget.objects.get(user=request.user, month=int(month), year=int(year))
        except Budget.DoesNotExist:
            return ApiResponse.error('Budget not found', 404)

        # Calculate current spending for the month
        start = datetime(int(year), int(month), 1, tzinfo=dt_timezone.utc)
        if int(month) == 12:
            end = datetime(int(year) + 1, 1, 1, tzinfo=dt_timezone.utc)
        else:
            end = datetime(int(year), int(month) + 1, 1, tzinfo=dt_timezone.utc)

        current_spent = Expense.objects.filter(
            user=request.user,
            expense_date__gte=start, expense_date__lt=end
        ).aggregate(total=Sum('amount'))['total'] or 0
        current_spent = float(current_spent)
        budget_total = float(budget.total_monthly_budget)

        data = BudgetSerializer(budget).data
        data['currentSpent'] = current_spent
        data['remainingAmount'] = budget_total - current_spent
        data['usagePercent'] = round((current_spent / budget_total * 100), 2) if budget_total > 0 else 0
        data['isWarning'] = (current_spent / budget_total * 100) >= budget.warning_threshold if budget_total > 0 else False

        return ApiResponse.success(data)


class BudgetGetAllView(APIView):
    """GET /api/v1/budget/all — list all budgets"""

    def get(self, request):
        budgets = Budget.objects.filter(user=request.user)
        serializer = BudgetSerializer(budgets, many=True)
        return ApiResponse.success(serializer.data)


class BudgetWarningsView(APIView):
    """GET /api/v1/budget/warnings — check current month budget warnings"""

    def get(self, request):
        now = timezone.now()
        try:
            budget = Budget.objects.get(user=request.user, month=now.month, year=now.year)
        except Budget.DoesNotExist:
            return ApiResponse.success({'warning': False, 'message': 'No budget set for current month'})

        start = get_start_of_month(now)
        end = get_end_of_month(now)
        spent = float(
            Expense.objects.filter(
                user=request.user,
                expense_date__gte=start, expense_date__lte=end
            ).aggregate(total=Sum('amount'))['total'] or 0
        )
        budget_total = float(budget.total_monthly_budget)
        usage = (spent / budget_total * 100) if budget_total > 0 else 0

        return ApiResponse.success({
            'warning': usage >= budget.warning_threshold,
            'usage': round(usage, 2),
            'spent': spent,
            'budget': budget_total,
            'remaining': budget_total - spent,
            'threshold': budget.warning_threshold,
        })


# ═══════════════════════════════════════════
#  REPORT VIEWS
# ═══════════════════════════════════════════
class ReportCSVView(APIView):
    """POST /api/v1/reports/csv — generate and download CSV report"""

    def post(self, request):
        start_date = request.data.get('startDate')
        end_date = request.data.get('endDate')

        if not start_date or not end_date:
            return ApiResponse.error('startDate and endDate are required', 400)

        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))

        expenses = Expense.objects.filter(
            user=request.user,
            expense_date__gte=start, expense_date__lte=end
        ).order_by('-expense_date')

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Title', 'Amount', 'Category', 'Payment Method', 'Date', 'Notes'])

        for e in expenses:
            writer.writerow([
                e.title,
                float(e.amount),
                e.category,
                e.payment_method,
                e.expense_date.strftime('%Y-%m-%d'),
                e.notes,
            ])

        # Save report record
        total_expense = float(expenses.aggregate(total=Sum('amount'))['total'] or 0)
        Report.objects.create(
            user=request.user,
            type='custom',
            start_date=start,
            end_date=end,
            format='csv',
            total_expense=total_expense,
        )

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename=expenses_report.csv'
        return response


class ReportPDFView(APIView):
    """POST /api/v1/reports/pdf — generate and download PDF report"""

    def post(self, request):
        start_date = request.data.get('startDate')
        end_date = request.data.get('endDate')

        if not start_date or not end_date:
            return ApiResponse.error('startDate and endDate are required', 400)

        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))

        expenses = Expense.objects.filter(
            user=request.user,
            expense_date__gte=start, expense_date__lte=end
        ).order_by('-expense_date')

        total_expense = float(expenses.aggregate(total=Sum('amount'))['total'] or 0)
        expense_count = expenses.count()

        # Category breakdown
        category_data = (
            expenses.values('category')
            .annotate(total=Sum('amount'), count=Count('id'))
            .order_by('-total')
        )

        # Generate PDF using ReportLab
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as pdf_canvas

        buffer = io.BytesIO()
        c = pdf_canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # Title
        c.setFont('Helvetica-Bold', 22)
        c.drawCentredString(width / 2, height - 50, 'ExpenseIQ Financial Report')
        c.setFont('Helvetica', 11)
        c.setFillColorRGB(0.4, 0.4, 0.4)
        c.drawCentredString(
            width / 2, height - 70,
            f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}"
        )

        # Summary
        y = height - 110
        c.setFillColorRGB(0, 0, 0)
        c.setFont('Helvetica-Bold', 14)
        c.drawString(50, y, 'Summary')
        y -= 25
        c.setFont('Helvetica', 11)
        c.drawString(50, y, f'Total Expenses: ${total_expense:,.0f}')
        y -= 18
        c.drawString(50, y, f'Transactions: {expense_count}')

        # Category breakdown
        y -= 35
        c.setFont('Helvetica-Bold', 14)
        c.drawString(50, y, 'Spending by Category')
        y -= 25
        c.setFont('Helvetica', 10)
        for cat in category_data:
            c.drawString(50, y, f"{cat['category']}: ${float(cat['total']):,.0f} ({cat['count']} transactions)")
            y -= 16
            if y < 50:
                c.showPage()
                y = height - 50

        # Expense Details
        y -= 25
        c.setFont('Helvetica-Bold', 14)
        c.drawString(50, y, 'Expense Details')
        y -= 25
        c.setFont('Helvetica', 9)
        for e in expenses[:50]:
            c.drawString(
                50, y,
                f"{e.expense_date.strftime('%Y-%m-%d')}  |  {e.title}  |  ${float(e.amount)}  |  {e.category}"
            )
            y -= 14
            if y < 50:
                c.showPage()
                y = height - 50

        if expenses.count() > 50:
            y -= 10
            c.drawString(50, y, f'... and {expenses.count() - 50} more transactions')

        c.save()

        # Save report record
        Report.objects.create(
            user=request.user,
            type='custom',
            start_date=start,
            end_date=end,
            format='pdf',
            total_expense=total_expense,
        )

        buffer.seek(0)
        response = HttpResponse(buffer.read(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename=financial_report.pdf'
        return response


class ReportHistoryView(APIView):
    """GET /api/v1/reports/history — paginated report history"""

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        limit = int(request.query_params.get('limit', 10))

        queryset = Report.objects.filter(user=request.user).order_by('-created_at')
        total = queryset.count()
        offset = (page - 1) * limit
        reports = queryset[offset:offset + limit]

        serializer = ReportSerializer(reports, many=True)
        return ApiResponse.paginated(serializer.data, page, limit, total)


class UserSettingsView(APIView):
    """GET/PUT /api/v1/settings"""

    def get(self, request):
        settings, created = UserSettings.objects.get_or_create(user=request.user)
        serializer = UserSettingsSerializer(settings)
        return ApiResponse.success(serializer.data)

    def put(self, request):
        settings, created = UserSettings.objects.get_or_create(user=request.user)
        serializer = UserSettingsSerializer(settings, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return ApiResponse.success(serializer.data, message='Settings updated successfully')
        return ApiResponse.error('Validation failed', 400, serializer.errors)


@login_required
def index_view(request):
    """Renders the dashboard index page with server-side context fallback."""
    now = timezone.now()
    
    # Query categories
    categories = Category.objects.filter(user=request.user).order_by('name')
    categories_map = {c.name: c.icon for c in categories}
    
    # Query recent expenses
    recent_expenses = Expense.objects.filter(user=request.user).order_by('-expense_date')[:7]
    for e in recent_expenses:
        e.category_icon = categories_map.get(e.category, 'ph-package')
        
    # Query budget warnings/info for current month
    budget_info = None
    budget = Budget.objects.filter(user=request.user, month=now.month, year=now.year).first()
    if budget:
        start = get_start_of_month(now)
        end = get_end_of_month(now)
        spent = float(
            Expense.objects.filter(
                user=request.user,
                expense_date__gte=start, expense_date__lte=end
            ).aggregate(total=Sum('amount'))['total'] or 0
        )
        budget_total = float(budget.total_monthly_budget)
        usage = (spent / budget_total * 100) if budget_total > 0 else 0
        budget_info = {
            'budget': budget_total,
            'spent': spent,
            'remaining': budget_total - spent,
            'usage': round(usage, 2),
            'threshold': budget.warning_threshold,
            'warning': usage >= budget.warning_threshold,
        }
        
    context = {
        'categories': categories,
        'recent_expenses': recent_expenses,
        'budget_info': budget_info,
    }
    return render(request, 'index.html', context)
