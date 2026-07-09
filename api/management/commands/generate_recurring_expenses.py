"""
Management command to generate expenses from active recurring expense templates.

Runs daily via cron/celery beat to check all active recurring expenses
and create Expense records for any that are past their next_due_date.

Usage:
    python manage.py generate_recurring_expenses
    python manage.py generate_recurring_expenses --user <user_id>
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from api.services import generate_recurring_expenses


class Command(BaseCommand):
    help = 'Generate expense records from active recurring expense templates'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=int,
            help='User ID to generate expenses for (default: all users)',
        )

    def handle(self, *args, **options):
        user_id = options.get('user')
        user = None

        if user_id:
            try:
                user = User.objects.get(id=user_id)
                self.stdout.write(f'Processing recurring expenses for user: {user.username}')
            except User.DoesNotExist:
                self.stderr.write(f'User with id {user_id} not found')
                return

        created = generate_recurring_expenses(user=user)

        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully generated {len(created)} expense(s)')
            )
            for expense in created:
                self.stdout.write(
                    f'  - {expense.title}: ${expense.amount} on {expense.expense_date.date()}'
                )
        else:
            self.stdout.write(self.style.WARNING('No expenses needed to be generated'))
