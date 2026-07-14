"""Legacy entry point.

FCM initialization and delivery now live in ``api.notifications`` so Django
loads credentials from ``FIREBASE_SERVICE_ACCOUNT_PATH`` at send time.
"""

from api.notifications import send_push_notification

__all__ = ['send_push_notification']
