"""
Management command to generate weekly spending reports.

Runs weekly via cron to calculate metrics and send summary push notifications.

Usage:
    python manage.py generate_weekly_reports
    python manage.py generate_weekly_reports --user <user_id>
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from api.services import generate_weekly_report


class Command(BaseCommand):
    help = "Generate weekly spending reports and send push notifications to users"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            type=int,
            help="User ID to generate report for (default: all users)",
        )

    def handle(self, *args, **options):
        user_id = options.get("user")
        users = []

        if user_id:
            try:
                user = User.objects.get(id=user_id)
                users.append(user)
                self.stdout.write(f"Processing weekly report for user: {user.username}")
            except User.DoesNotExist:
                self.stderr.write(f"User with id {user_id} not found")
                return
        else:
            users = list(User.objects.filter(is_active=True))
            self.stdout.write(f"Processing weekly reports for {len(users)} active user(s)")

        sent_count = 0
        skipped_count = 0

        for user in users:
            result = generate_weekly_report(user)
            if result.get("sent", 0) > 0:
                sent_count += 1
                self.stdout.write(self.style.SUCCESS(f"  - Sent weekly report to {user.username}"))
            else:
                skipped_count += 1
                skipped_reason = result.get("skipped", "unknown")
                self.stdout.write(f"  - Skipped {user.username} (reason: {skipped_reason})")

        self.stdout.write(
            self.style.SUCCESS(f"Weekly reports processing complete. Sent: {sent_count}, Skipped: {skipped_count}")
        )
