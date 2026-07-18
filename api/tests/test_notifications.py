"""Tests for FCM device registration and privacy boundaries."""

from django.contrib.auth.models import User

from api.models import DeviceToken
from api.tests.base import BaseAPITestCase


class DeviceTokenTests(BaseAPITestCase):
    def test_register_device_token_does_not_return_token(self):
        response = self.client.post(
            "/api/v1/notifications/devices",
            {
                "token": "fcm-token-that-is-long-enough-to-pass-validation",
                "platform": "web",
                "device_name": "Test browser",
            },
            format="json",
        )

        data = self.assert_success_response(response, 201)
        self.assertNotIn("token", data["data"])
        self.assertTrue(DeviceToken.objects.filter(user=self.test_user).exists())

    def test_device_list_does_not_return_token(self):
        DeviceToken.objects.create(
            user=self.test_user,
            token="fcm-token-that-is-long-enough-to-pass-validation",
        )

        response = self.client.get("/api/v1/notifications/devices")

        data = self.assert_success_response(response)
        self.assertEqual(len(data["data"]), 1)
        self.assertNotIn("token", data["data"][0])

    def test_user_cannot_delete_another_users_device(self):
        other_user = User.objects.create_user("other-user", password="Password123!")
        device = DeviceToken.objects.create(
            user=other_user,
            token="another-fcm-token-that-is-long-enough-to-pass-validation",
        )

        response = self.client.delete(f"/api/v1/notifications/devices/{device.id}")

        self.assert_error_response(response, 404)
        self.assertTrue(DeviceToken.objects.filter(pk=device.id).exists())


from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.management import call_command
from django.utils import timezone

from api.models import Expense, UserSettings


class NotificationServiceAndCommandTests(BaseAPITestCase):
    def test_cleanup_stale_device_tokens_service_and_command(self):
        # Create a fresh token (should not be deleted)
        DeviceToken.objects.create(
            user=self.test_user,
            token="fresh-token-that-is-long-enough-to-pass-validation",
        )

        # Create a stale token and manually set its last_seen_at using update
        stale_device = DeviceToken.objects.create(
            user=self.test_user,
            token="stale-token-that-is-long-enough-to-pass-validation",
        )
        DeviceToken.objects.filter(id=stale_device.id).update(last_seen_at=timezone.now() - timedelta(days=40))

        # Run command
        call_command("cleanup_device_tokens", days=35)

        # Stale token should be deleted, fresh token kept
        self.assertFalse(DeviceToken.objects.filter(id=stale_device.id).exists())
        self.assertEqual(DeviceToken.objects.filter(user=self.test_user).count(), 1)

    @patch("api.notifications._get_messaging")
    def test_generate_weekly_report_and_command(self, mock_get_messaging):
        mock_get_messaging.return_value = None  # skips sending to FCM, but runs logic

        # Create user settings with weekly_report enabled
        settings, _ = UserSettings.objects.get_or_create(user=self.test_user)
        settings.weekly_report = True
        settings.save()

        # Create some expenses in the current week
        Expense.objects.create(
            user=self.test_user,
            title="Weekly Expense 1",
            amount=Decimal("100.00"),
            category="Food",
            expense_date=timezone.now() - timedelta(days=2),
        )

        # Call management command
        call_command("generate_weekly_reports", user=self.test_user.id)

        # The command runs successfully without throwing exceptions

    def test_notification_test_view_not_configured(self):
        # If Firebase is not configured, it should return 503
        with patch("api.notifications._get_messaging", return_value=None):
            response = self.client.post("/api/v1/notifications/test")
            self.assert_error_response(response, 503)

    def test_notification_test_view_success_sync(self):
        # Mock _get_messaging and send_push_notification so we test the endpoint without FCM
        with (
            patch("api.notifications._get_messaging") as mock_get_messaging,
            patch("api.views.notification_views.send_push_notification") as mock_send,
        ):
            mock_get_messaging.return_value = object()
            mock_send.return_value = {"sent": 1, "removed": 0}
            response = self.client.post("/api/v1/notifications/test")
            data = self.assert_success_response(response, 200)
            self.assertEqual(data["data"]["sent"], 1)
            mock_send.assert_called_once()

    def test_firebase_messaging_service_worker_503(self):
        # If config is incomplete, it returns 503
        with self.settings(FIREBASE_WEB_CONFIG={"apiKey": ""}):
            response = self.client.get("/firebase-messaging-sw.js")
            self.assertEqual(response.status_code, 503)
            self.assertIn(b"Firebase messaging is not configured", response.content)


class NewNotificationTriggerTests(BaseAPITestCase):
    @patch("api.notifications.send_push_notification")
    def test_auth_password_changed_notification(self, mock_send):
        # The user is already pre-authenticated in self.client
        # Let's change the password from ApiTestPassword123 to NewPassword123!
        response = self.client.post(
            "/api/v1/auth/change-password",
            {
                "currentPassword": "ApiTestPassword123",
                "newPassword": "NewPassword123!",
                "confirmPassword": "NewPassword123!"
            },
            format="json"
        )
        self.assert_success_response(response, 200)
        mock_send.assert_called_with(
            self.test_user,
            event_type="auth_password_changed",
            title="Password changed",
            body="Your account password was changed successfully.",
            url="/settings/",
            data=None
        )

    @patch("api.notifications.send_push_notification")
    def test_auth_account_disabled_notification(self, mock_send):
        self.test_user.is_active = False
        self.test_user.save()

        with patch("django.db.transaction.on_commit") as mock_on_commit:
            response = self.client.post(
                "/api/v1/auth/login",
                {
                    "identifier": "apitestuser",
                    "password": "ApiTestPassword123"
                },
                format="json"
            )
            self.assert_error_response(response, 403)
            mock_on_commit.assert_called_once()
            mock_send.assert_not_called()

            # Retrieve and execute callback
            callback = mock_on_commit.call_args[0][0]
            callback()

            mock_send.assert_called_with(
                self.test_user,
                event_type="auth_account_disabled",
                title="Account disabled",
                body="Your ExpenseTracker account has been disabled."
            )

    @patch("api.notifications.send_push_notification")
    def test_report_generated_notification(self, mock_send):
        with patch("django.db.transaction.on_commit") as mock_on_commit:
            response = self.client.post(
                "/api/v1/reports/csv",
                {
                    "startDate": "2026-07-01T00:00:00Z",
                    "endDate": "2026-07-31T23:59:59Z"
                },
                format="json"
            )
            self.assertEqual(response.status_code, 200)
            mock_on_commit.assert_called_once()
            mock_send.assert_not_called()

            # Retrieve and execute callback
            callback = mock_on_commit.call_args[0][0]
            callback()

            mock_send.assert_called_with(
                self.test_user,
                event_type="report_generated",
                title="Csv report generated",
                body="Your csv report (2026-07-01 – 2026-07-31) is ready.",
                url="/reports/",
                data={
                    "reportType": "csv",
                    "startDate": "2026-07-01",
                    "endDate": "2026-07-31"
                }
            )

    @patch("api.notifications.send_push_notification")
    @patch("api.notifications.send_once")
    def test_budget_notifications_triggered_on_expense(self, mock_send_once, mock_send):
        from datetime import datetime as dt
        from decimal import Decimal

        from django.utils import timezone

        from api.models import Budget, Category, Expense
        from api.notifications import (
            notify_budget_status,
            notify_category_budget_exceeded,
            notify_large_expense,
        )

        # Retrieve cat_food and update its budget
        cat = Category.objects.filter(user=self.test_user, name="Food").first()
        cat.monthly_budget = Decimal("100.00")
        cat.save()

        budget = Budget.objects.filter(user=self.test_user, month=7, year=2026).first()
        if budget:
            budget.total_monthly_budget = Decimal("500.00")
            budget.warning_threshold = 80
            budget.save()
        else:
            budget = Budget.objects.create(
                user=self.test_user,
                month=7,
                year=2026,
                total_monthly_budget=Decimal("500.00"),
                warning_threshold=80
            )

        expense = Expense.objects.create(
            user=self.test_user,
            title="Dinner",
            amount=Decimal("300.00"),
            category="Food",
            expense_date=timezone.make_aware(dt(2026, 7, 15, 12, 0))
        )

        notify_budget_status(self.test_user, expense)
        notify_category_budget_exceeded(self.test_user, expense)
        notify_large_expense(self.test_user, expense)

        calls = [call[1]["event_type"] for call in mock_send_once.call_args_list]
        self.assertIn("large_expense_created", calls)
        self.assertIn("category_budget_exceeded", calls)


