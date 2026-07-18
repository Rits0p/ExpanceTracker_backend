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


from unittest.mock import patch
from django.core.management import call_command
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from api.models import UserSettings, Expense


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

    def test_notification_test_view_success_async(self):
        # Mock _get_messaging to return a mock and send_push_notification to be mocked
        with (
            patch("api.notifications._get_messaging") as mock_get_messaging,
            patch("api.views.notification_views.send_push_notification") as mock_send,
        ):
            mock_get_messaging.return_value = object()
            response = self.client.post("/api/v1/notifications/test")
            self.assert_success_response(response, 200)
            # The test should return immediately, while spawning a background thread

    def test_firebase_messaging_service_worker_503(self):
        # If config is incomplete, it returns 503
        with self.settings(FIREBASE_WEB_CONFIG={"apiKey": ""}):
            response = self.client.get("/firebase-messaging-sw.js")
            self.assertEqual(response.status_code, 503)
            self.assertIn(b"Firebase messaging is not configured", response.content)
