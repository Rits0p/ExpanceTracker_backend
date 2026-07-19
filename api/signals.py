import sys
from datetime import date
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Budget, Category, UserSettings

@receiver(post_save, sender=User)
def create_default_categories(sender, instance, created, **kwargs):
    if created and 'test' not in sys.argv:
        # Create default UserSettings
        UserSettings.objects.get_or_create(user=instance)

        defaults = [
            {'name': 'Food', 'icon': 'ph-hamburger', 'color': '#10b981'},
            {'name': 'Groceries', 'icon': 'ph-shopping-cart', 'color': '#2cb67d'},
            {'name': 'Housing', 'icon': 'ph-house-line', 'color': '#8b5cf6'},
            {'name': 'Utilities', 'icon': 'ph-lightning', 'color': '#f59e0b'},
            {'name': 'Health', 'icon': 'ph-heartbeat', 'color': '#ef4444'},
            {'name': 'Entertainment', 'icon': 'ph-film-strip', 'color': '#ec4899'},
            {'name': 'Shopping', 'icon': 'ph-bag', 'color': '#f43f5e'},
            {'name': 'Travel', 'icon': 'ph-car', 'color': '#06b6d4'},
            {'name': 'Other', 'icon': 'ph-package', 'color': '#6b7280'},
        ]
        for cat in defaults:
            Category.objects.get_or_create(
                user=instance,
                name=cat['name'],
                defaults={
                    'icon': cat['icon'],
                    'color': cat['color'],
                }
            )

        # Create default budget for current month with all values at 0
        today = date.today()
        Budget.objects.get_or_create(
            user=instance,
            month=today.month,
            year=today.year,
            defaults={
                'total_monthly_budget': 0,
                'daily_budget': 0,
                'weekly_budget': 0,
                'yearly_budget': 0,
                'warning_threshold': 80,
            }
        )

