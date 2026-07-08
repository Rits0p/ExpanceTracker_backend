"""Django admin configuration for ExpenseIQ models."""
from django.contrib import admin
from .models import Expense, Category, Budget, Report


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'icon', 'color', 'monthly_budget', 'created_at']
    search_fields = ['name']


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ['title', 'amount', 'category', 'payment_method', 'expense_date', 'is_recurring']
    list_filter = ['category', 'payment_method', 'is_recurring']
    search_fields = ['title', 'notes']
    date_hierarchy = 'expense_date'


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ['month', 'year', 'total_monthly_budget', 'warning_threshold']
    list_filter = ['year']


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['type', 'format', 'start_date', 'end_date', 'total_expense', 'total_income', 'created_at']
    list_filter = ['type', 'format']
    date_hierarchy = 'created_at'
