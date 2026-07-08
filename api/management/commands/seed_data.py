"""
Management command to seed the database with sample data.
Matches the AppData sample data from the frontend js/app.js.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import random

from api.models import Category, Expense, Budget


class Command(BaseCommand):
    help = 'Seed database with sample expense, category, and budget data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear', action='store_true',
            help='Clear existing data before seeding',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing data...')
            Expense.objects.all().delete()

            Category.objects.all().delete()
            Budget.objects.all().delete()

        self.stdout.write('Seeding categories...')
        categories_data = [
            {'name': 'Food', 'icon': 'ph-hamburger', 'color': '#10b981', 'monthly_budget': 500},
            {'name': 'Transport', 'icon': 'ph-car', 'color': '#06b6d4', 'monthly_budget': 200},
            {'name': 'Entertainment', 'icon': 'ph-film-strip', 'color': '#8b5cf6', 'monthly_budget': 150},
            {'name': 'Utilities', 'icon': 'ph-lightning', 'color': '#f59e0b', 'monthly_budget': 300},
            {'name': 'Health', 'icon': 'ph-barbell', 'color': '#ef4444', 'monthly_budget': 100},
            {'name': 'Shopping', 'icon': 'ph-tote', 'color': '#ec4899', 'monthly_budget': 250},
        ]
        for cat_data in categories_data:
            Category.objects.get_or_create(name=cat_data['name'], defaults=cat_data)

        self.stdout.write('Seeding expenses...')
        now = timezone.now()
        expenses_data = [
            {'title': 'Grocery Shopping', 'amount': 142, 'category': 'Food', 'payment_method': 'Credit Card', 'expense_date': now - timedelta(days=1)},
            {'title': 'Netflix Subscription', 'amount': 15, 'category': 'Entertainment', 'payment_method': 'Debit Card', 'expense_date': now - timedelta(days=2)},
            {'title': 'Electricity Bill', 'amount': 89, 'category': 'Utilities', 'payment_method': 'Bank Transfer', 'expense_date': now - timedelta(days=3)},
            {'title': 'Gym Membership', 'amount': 50, 'category': 'Health', 'payment_method': 'Credit Card', 'expense_date': now - timedelta(days=4)},
            {'title': 'Coffee & Snacks', 'amount': 24, 'category': 'Food', 'payment_method': 'Cash', 'expense_date': now - timedelta(days=5)},
            {'title': 'Uber Rides', 'amount': 37, 'category': 'Transport', 'payment_method': 'Debit Card', 'expense_date': now - timedelta(days=6)},
            {'title': 'Office Supplies', 'amount': 63, 'category': 'Shopping', 'payment_method': 'Credit Card', 'expense_date': now - timedelta(days=7)},
            {'title': 'Internet Bill', 'amount': 75, 'category': 'Utilities', 'payment_method': 'Auto Pay', 'expense_date': now - timedelta(days=8)},
            {'title': 'Restaurant Dinner', 'amount': 86, 'category': 'Food', 'payment_method': 'Credit Card', 'expense_date': now - timedelta(days=9)},
            {'title': 'Spotify Premium', 'amount': 10, 'category': 'Entertainment', 'payment_method': 'Debit Card', 'expense_date': now - timedelta(days=10)},
        ]

        # Add more variety — past months for analytics
        past_expenses = [
            {'title': 'Rent Payment', 'amount': 1200, 'category': 'Utilities', 'payment_method': 'Bank Transfer'},
            {'title': 'Fuel', 'amount': 55, 'category': 'Transport', 'payment_method': 'Debit Card'},
            {'title': 'Movie Tickets', 'amount': 30, 'category': 'Entertainment', 'payment_method': 'Credit Card'},
            {'title': 'Groceries', 'amount': 165, 'category': 'Food', 'payment_method': 'Credit Card'},
            {'title': 'Pharmacy', 'amount': 45, 'category': 'Health', 'payment_method': 'Cash'},
            {'title': 'Clothing', 'amount': 120, 'category': 'Shopping', 'payment_method': 'Credit Card'},
            {'title': 'Takeout', 'amount': 32, 'category': 'Food', 'payment_method': 'UPI'},
            {'title': 'Bus Pass', 'amount': 80, 'category': 'Transport', 'payment_method': 'Cash'},
        ]

        for exp_data in expenses_data:
            Expense.objects.create(**exp_data)

        # Generate past month expenses for analytics charts
        for month_offset in range(1, 6):
            for exp_template in past_expenses:
                day = random.randint(1, 28)
                base_date = now - timedelta(days=30 * month_offset + day)
                amt_variation = Decimal(str(random.uniform(0.8, 1.3)))
                Expense.objects.create(
                    title=exp_template['title'],
                    amount=Decimal(str(exp_template['amount'])) * amt_variation,
                    category=exp_template['category'],
                    payment_method=exp_template['payment_method'],
                    expense_date=base_date,
                )

        self.stdout.write('Seeding budgets...')
        current_month = now.month
        current_year = now.year
        Budget.objects.get_or_create(
            month=current_month, year=current_year,
            defaults={'total_monthly_budget': 2500, 'warning_threshold': 80}
        )

        self.stdout.write(self.style.SUCCESS(
            f'✅ Database seeded successfully!\n'
            f'   Categories: {Category.objects.count()}\n'
            f'   Expenses: {Expense.objects.count()}\n'
            f'   Budgets: {Budget.objects.count()}'
        ))
