"""
Management command to clean up stale FCM device tokens.

Usage:
    python manage.py cleanup_device_tokens
    python manage.py cleanup_device_tokens --days 60
"""

from django.core.management.base import BaseCommand
from api.services import cleanup_stale_device_tokens


class Command(BaseCommand):
    help = "Clean up stale FCM device tokens that have not been seen for a specified number of days"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Cutoff age in days for stale device tokens (default: 30)",
        )

    def handle(self, *args, **options):
        days = options.get("days")
        self.stdout.write(f"Cleaning up FCM device tokens older than {days} days...")
        count = cleanup_stale_device_tokens(days=days)
        self.stdout.write(self.style.SUCCESS(f"Successfully deleted {count} stale device token(s)."))
