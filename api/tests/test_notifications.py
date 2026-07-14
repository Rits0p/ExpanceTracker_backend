"""Tests for FCM device registration and privacy boundaries."""

from django.contrib.auth.models import User

from api.models import DeviceToken
from api.tests.base import BaseAPITestCase


class DeviceTokenTests(BaseAPITestCase):
    def test_register_device_token_does_not_return_token(self):
        response = self.client.post(
            '/api/v1/notifications/devices',
            {
                'token': 'fcm-token-that-is-long-enough-to-pass-validation',
                'platform': 'web',
                'device_name': 'Test browser',
            },
            format='json',
        )

        data = self.assert_success_response(response, 201)
        self.assertNotIn('token', data['data'])
        self.assertTrue(DeviceToken.objects.filter(user=self.test_user).exists())

    def test_device_list_does_not_return_token(self):
        DeviceToken.objects.create(
            user=self.test_user,
            token='fcm-token-that-is-long-enough-to-pass-validation',
        )

        response = self.client.get('/api/v1/notifications/devices')

        data = self.assert_success_response(response)
        self.assertEqual(len(data['data']), 1)
        self.assertNotIn('token', data['data'][0])

    def test_user_cannot_delete_another_users_device(self):
        other_user = User.objects.create_user('other-user', password='Password123!')
        device = DeviceToken.objects.create(
            user=other_user,
            token='another-fcm-token-that-is-long-enough-to-pass-validation',
        )

        response = self.client.delete(f'/api/v1/notifications/devices/{device.id}')

        self.assert_error_response(response, 404)
        self.assertTrue(DeviceToken.objects.filter(pk=device.id).exists())
