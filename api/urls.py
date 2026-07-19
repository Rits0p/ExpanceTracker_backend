"""
API URL configuration for ExpenseIQ.
Mirrors the Node.js Express router structure:
  /api/v1/expenses/*
  /api/v1/analytics/*
  /api/v1/categories/*
  /api/v1/budget/*
  /api/v1/reports/*
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ExpenseListCreateView,
    ExpenseDetailView,
    ExpenseSearchView,
    ExpenseRecurringView,
    ExpenseReceiptUploadView,
    ExpenseSeedView,
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
    NotificationAlertsView,
)
from .views.analytics_views import (
    AnalyticsKPIsView,
    AnalyticsWeeklyView,
    AnalyticsMonthlyView,
    AnalyticsMonthlyBarChartView,
    AnalyticsWeeklyLineChartView,
    AnalyticsCategoryPieChartView,
    AnalyticsBudgetExpenseChartView,
    AnalyticsCategoryView,
    AnalyticsRecurringView,
)
from .views.recurring_expense_views import RecurringExpenseViewSet
from .views.notification_views import (
    DeviceTokenDetailView,
    DeviceTokenListCreateView,
    FirebaseConfigView,
    NotificationTestView,
)

# ───── DRF Router for ViewSets ─────
router = DefaultRouter()
router.register(r'recurring-expenses', RecurringExpenseViewSet, basename='recurring-expense')

urlpatterns = [
    # ───── Expense Routes ─────
    path('expenses/', ExpenseListCreateView.as_view(), name='expense-list-create'),
    path('expenses/search', ExpenseSearchView.as_view(), name='expense-search'),
    path('expenses/seed', ExpenseSeedView.as_view(), name='expense-seed'),
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
    path('notifications/alerts', NotificationAlertsView.as_view(), name='notification-alerts'),

    # ───── Report Routes ─────
    path('reports/csv', ReportCSVView.as_view(), name='report-csv'),
    path('reports/pdf', ReportPDFView.as_view(), name='report-pdf'),
    path('reports/history', ReportHistoryView.as_view(), name='report-history'),

    # ───── Analytics Routes ─────
    path('analytics/kpis', AnalyticsKPIsView.as_view(), name='analytics-kpis'),
    path('analytics/weekly', AnalyticsWeeklyView.as_view(), name='analytics-weekly'),
    path('analytics/monthly', AnalyticsMonthlyView.as_view(), name='analytics-monthly'),
    path('analytics/recurring', AnalyticsRecurringView.as_view(), name='analytics-recurring'),
    path('analytics/charts/monthly-bar', AnalyticsMonthlyBarChartView.as_view(), name='analytics-monthly-bar'),
    path('analytics/charts/weekly-line', AnalyticsWeeklyLineChartView.as_view(), name='analytics-weekly-line'),
    path('analytics/charts/category-pie', AnalyticsCategoryPieChartView.as_view(), name='analytics-category-pie'),
    path('analytics/charts/budget-expense', AnalyticsBudgetExpenseChartView.as_view(), name='analytics-budget-expense'),
    path('analytics/categories', AnalyticsCategoryView.as_view(), name='analytics-categories'),

    # ───── AI Routes ─────
    path('ai/assistant', AIAssistantView.as_view(), name='ai-assistant'),

    # Firebase Cloud Messaging device registration and diagnostics
    path('notifications/config', FirebaseConfigView.as_view(), name='firebase-config'),
    path('notifications/devices', DeviceTokenListCreateView.as_view(), name='device-list-create'),
    path('notifications/devices/<int:pk>', DeviceTokenDetailView.as_view(), name='device-detail'),
    path('notifications/test', NotificationTestView.as_view(), name='notification-test'),

    # ───── Recurring Expense Routes (ViewSet via Router) ─────
    path('', include(router.urls)),
]
