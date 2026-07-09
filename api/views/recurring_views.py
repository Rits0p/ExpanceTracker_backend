"""
Views for rendering Recurring Expense template pages.
These are thin view functions that render HTML shells.
All data operations happen client-side via the REST API.
"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from ..models import RecurringExpense, Category


@login_required
def recurring_expense_list(request):
    categories = Category.objects.filter(user=request.user).order_by('name')
    return render(request, 'recurring_expense/list.html', {
        'categories': categories,
        'frequencies': RecurringExpense.FREQUENCY_CHOICES,
    })


@login_required
def recurring_expense_detail(request, pk):
    return render(request, 'recurring_expense/detail.html', {
        'recurring_id': pk,
    })


@login_required
def recurring_expense_create(request):
    categories = Category.objects.filter(user=request.user).order_by('name')
    return render(request, 'recurring_expense/create.html', {
        'categories': categories,
        'frequencies': RecurringExpense.FREQUENCY_CHOICES,
    })


@login_required
def recurring_expense_update(request, pk):
    categories = Category.objects.filter(user=request.user).order_by('name')
    return render(request, 'recurring_expense/update.html', {
        'categories': categories,
        'frequencies': RecurringExpense.FREQUENCY_CHOICES,
        'recurring_id': pk,
    })
