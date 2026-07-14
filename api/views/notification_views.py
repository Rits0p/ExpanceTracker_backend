"""Authenticated device-registration and FCM test endpoints."""

from django.conf import settings
from django.shortcuts import get_object_or_404
from hashlib import sha256
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from ..models import DeviceToken
from ..notifications import send_push_notification
from ..serializers import DeviceTokenSerializer
from ..utils import ApiResponse


class FirebaseConfigView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        config = settings.FIREBASE_WEB_CONFIG
        required = ('apiKey', 'authDomain', 'projectId', 'messagingSenderId', 'appId', 'vapidKey')
        if not all(config.get(key) for key in required):
            return ApiResponse.error('Firebase web messaging is not configured.', 503)
        return ApiResponse.success(config)


class DeviceTokenListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        devices = DeviceToken.objects.filter(user=request.user)
        serializer = DeviceTokenSerializer(devices, many=True)
        return ApiResponse.success(serializer.data)

    def post(self, request):
        serializer = DeviceTokenSerializer(data=request.data)
        if not serializer.is_valid():
            return ApiResponse.error('Validation failed', 400, serializer.errors)

        token = serializer.validated_data.pop('token')
        token_hash = sha256(token.encode('utf-8')).hexdigest()
        DeviceToken.objects.filter(token_hash=token_hash).exclude(user=request.user).delete()
        device, created = DeviceToken.objects.update_or_create(
            user=request.user,
            token_hash=token_hash,
            defaults={**serializer.validated_data, 'token': token},
        )
        return ApiResponse.success(
            DeviceTokenSerializer(device).data,
            status_code=201 if created else 200,
            message='Device registered successfully',
        )


class DeviceTokenDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        device = get_object_or_404(DeviceToken, pk=pk, user=request.user)
        device.delete()
        return ApiResponse.success(message='Device removed successfully')


class NotificationTestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        result = send_push_notification(
            request.user,
            event_type='test',
            title='ExpenseTracker notifications enabled',
            body='This device can now receive expense notifications.',
            url='/settings/',
        )
        if result.get('skipped') == 'firebase_not_configured':
            return ApiResponse.error('Firebase server messaging is not configured.', 503)
        return ApiResponse.success(result, message='Test notification processed')
