"""Root URL configuration for ExpenseIQ Django backend."""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datetime import UTC

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.http import HttpResponse, JsonResponse
from django.urls import include, path

_start_time = time.time()


def health_check(request):
    """Health check endpoint matching Node.js format."""
    from datetime import datetime

    return JsonResponse(
        {
            "status": "ok",
            "timestamp": datetime.now(UTC).isoformat(),
            "uptime": round(time.time() - _start_time, 2),
        }
    )


def firebase_messaging_service_worker(request):
    """Serve FCM's required root-scoped worker with public web config only."""
    config = settings.FIREBASE_WEB_CONFIG
    required = ("apiKey", "authDomain", "projectId", "messagingSenderId", "appId", "vapidKey")
    if not all(config.get(key) for key in required):
        return HttpResponse(
            "// Firebase messaging is not configured.", content_type="application/javascript", status=503
        )

    script = f"""importScripts('https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.14.1/firebase-messaging-compat.js');
firebase.initializeApp({config!r});
const messaging = firebase.messaging();
// Handle data-only messages received in the background by showing a
// visible notification so the user is always informed.
messaging.onBackgroundMessage((payload) => {{
  if (payload.notification) {{
    return;
  }}
  const data = payload.data || {{}};
  const title = data.title || 'MoneyMatrix';
  const body = data.body || 'You have a new notification.';
  return self.registration.showNotification(title, {{
    body,
    icon: '/static/images/avatar.png',
    data: {{ url: data.url || '/' }},
  }});
}});
// When the user clicks a notification, navigate to the relevant page.
// FCM may nest custom data under different paths depending on the message
// type, so we check multiple locations for the target URL.
self.addEventListener('notificationclick', (event) => {{
  event.notification.close();
  const data = event.notification.data || {{}};
  const fcmData = data.FCM_MSG?.data || {{}};
  const url = data.url || fcmData.url || '/';
  event.waitUntil(
    clients.matchAll({{ type: 'window', includeUncontrolled: true }}).then((windowClients) => {{
      for (const client of windowClients) {{
        if (client.url.includes(self.location.origin) && 'focus' in client) {{
          client.navigate(url);
          return client.focus();
        }}
      }}
      if (clients.openWindow) {{
        return clients.openWindow(url);
      }}
    }})
  );
}});
"""
    return HttpResponse(script, content_type="application/javascript")


from django.contrib.auth.decorators import login_required
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from api.views.auth_views import (
    JWTChangePasswordView,
    JWTLoginView,
    JWTLogoutView,
    JWTMeView,
    JWTRefreshView,
    JWTRegisterView,
    login_view,
    logout_view,
    password_reset_view,
    profile_view,
    register_view,
)
from api.views.general_views import index_view

urlpatterns = [
    path("", index_view, name="home"),
    path("expenses/", login_required(TemplateView.as_view(template_name="expenses.html")), name="expenses"),
    path("budget/", login_required(TemplateView.as_view(template_name="budget.html")), name="budget"),
    path("ai-assistant/", login_required(TemplateView.as_view(template_name="ai_assistant.html")), name="ai-assistant"),
    path("settings/", login_required(TemplateView.as_view(template_name="settings.html")), name="settings"),
    path("profile/", profile_view, name="profile"),
    # Template-based Auth Routes (Session)
    path("login/", login_view, name="login"),
    path("register/", register_view, name="register"),
    path("logout/", logout_view, name="logout"),
    path("password-reset/", password_reset_view, name="password_reset"),
    # ───── JWT API Auth Routes ─────
    path("api/v1/auth/register", JWTRegisterView.as_view(), name="jwt-register"),
    path("api/v1/auth/login", JWTLoginView.as_view(), name="jwt-login"),
    path("api/v1/auth/refresh", JWTRefreshView.as_view(), name="jwt-refresh"),
    path("api/v1/auth/logout", JWTLogoutView.as_view(), name="jwt-logout"),
    path("api/v1/auth/me", JWTMeView.as_view(), name="jwt-me"),
    path("api/v1/auth/change-password", JWTChangePasswordView.as_view(), name="jwt-change-password"),
    path("admin/", admin.site.urls),
    path("health", health_check),
    path("firebase-messaging-sw.js", firebase_messaging_service_worker, name="firebase-messaging-sw"),
    path("api/v1/", include("api.urls")),
    path("api/chats/", include("api.chats_urls")),
    path("api/v1/chats/", include("api.chats_urls")),
    # Swagger docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/swagger/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/docs/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

if settings.DEBUG:
    # Serve collected static files and media in development
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
