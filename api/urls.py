"""
API URL configuration for ExpenseIQ.
Mirrors the Node.js Express router structure:
  /api/v1/expenses/*
  /api/v1/analytics/*
  /api/v1/categories/*
  /api/v1/budget/*
  /api/v1/reports/*
"""
from django.urls import path

from .views import (
    ExpenseListCreateView,
    ExpenseDetailView,
    ExpenseSearchView,
    ExpenseRecurringView,
    ExpenseReceiptUploadView,
)
from .views.ai_views import AIAssistantView

from .views.general_views import (
    CategoryListCreateView,
    CategoryDetailView,
    BudgetSetView,
    BudgetGetView,
    BudgetGetAllView,
    BudgetWarningsView,
    ReportCSVView,
    ReportPDFView,
    ReportHistoryView,
    UserSettingsView,
)
from .views.analytics_views import (
    AnalyticsKPIsView,
    AnalyticsWeeklyView,
    AnalyticsMonthlyView,
    AnalyticsMonthlyBarChartView,
    AnalyticsWeeklyLineChartView,
    AnalyticsCategoryPieChartView,
    AnalyticsCategoryView,
)

urlpatterns = [
    # ───── Expense Routes ─────
    path('expenses/', ExpenseListCreateView.as_view(), name='expense-list-create'),
    path('expenses/search', ExpenseSearchView.as_view(), name='expense-search'),
    path('expenses/recurring', ExpenseRecurringView.as_view(), name='expense-recurring'),
    path('expenses/<int:pk>/', ExpenseDetailView.as_view(), name='expense-detail'),
    path('expenses/<int:pk>/receipt', ExpenseReceiptUploadView.as_view(), name='expense-receipt'),

    # ───── Category Routes ─────
    path('categories', CategoryListCreateView.as_view(), name='category-list-create'),
    path('categories/<int:pk>', CategoryDetailView.as_view(), name='category-detail'),

    # ───── User Settings Routes ─────
    path('settings', UserSettingsView.as_view(), name='user-settings'),

    # ───── Budget Routes ─────
    path('budget', BudgetSetView.as_view(), name='budget-set'),
    path('budget/', BudgetGetView.as_view(), name='budget-get'),
    path('budget/all', BudgetGetAllView.as_view(), name='budget-get-all'),
    path('budget/warnings', BudgetWarningsView.as_view(), name='budget-warnings'),

    # ───── Report Routes ─────
    path('reports/csv', ReportCSVView.as_view(), name='report-csv'),
    path('reports/pdf', ReportPDFView.as_view(), name='report-pdf'),
    path('reports/history', ReportHistoryView.as_view(), name='report-history'),

    # ───── Analytics Routes ─────
    path('analytics/kpis', AnalyticsKPIsView.as_view(), name='analytics-kpis'),
    path('analytics/weekly', AnalyticsWeeklyView.as_view(), name='analytics-weekly'),
    path('analytics/monthly', AnalyticsMonthlyView.as_view(), name='analytics-monthly'),
    path('analytics/charts/monthly-bar', AnalyticsMonthlyBarChartView.as_view(), name='analytics-monthly-bar'),
    path('analytics/charts/weekly-line', AnalyticsWeeklyLineChartView.as_view(), name='analytics-weekly-line'),
    path('analytics/charts/category-pie', AnalyticsCategoryPieChartView.as_view(), name='analytics-category-pie'),
    path('analytics/categories', AnalyticsCategoryView.as_view(), name='analytics-categories'),
    path('ai/assistant', AIAssistantView.as_view(), name='ai-assistant'),
]
