"""Root URL configuration for ExpenseIQ Django backend."""
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.conf import settings
from django.conf.urls.static import static

_start_time = time.time()


def health_check(request):
    """Health check endpoint matching Node.js format."""
    from datetime import datetime, timezone
    return JsonResponse({
        'status': 'ok',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'uptime': round(time.time() - _start_time, 2),
    })


from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from django.contrib.auth.decorators import login_required
from api.views.auth_views import (
    login_view, register_view, logout_view, profile_view, password_reset_view,
    JWTRegisterView, JWTLoginView, JWTRefreshView, JWTLogoutView,
    JWTMeView, JWTChangePasswordView,
)
from api.views.general_views import index_view
from api.views.general_views import index_view

urlpatterns = [
    path('', index_view, name='home'),
    path('expenses/', login_required(TemplateView.as_view(template_name='expenses.html')), name='expenses'),
    path('budget/', login_required(TemplateView.as_view(template_name='budget.html')), name='budget'),
    path('ai-assistant/', login_required(TemplateView.as_view(template_name='ai_assistant.html')), name='ai-assistant'),

    path('settings/', login_required(TemplateView.as_view(template_name='settings.html')), name='settings'),
    path('profile/', profile_view, name='profile'),

    # Template-based Auth Routes (Session)
    path('login/', login_view, name='login'),
    path('register/', register_view, name='register'),
    path('logout/', logout_view, name='logout'),
    path('password-reset/', password_reset_view, name='password_reset'),

    # ───── JWT API Auth Routes ─────
    path('api/v1/auth/register', JWTRegisterView.as_view(), name='jwt-register'),
    path('api/v1/auth/login', JWTLoginView.as_view(), name='jwt-login'),
    path('api/v1/auth/refresh', JWTRefreshView.as_view(), name='jwt-refresh'),
    path('api/v1/auth/logout', JWTLogoutView.as_view(), name='jwt-logout'),
    path('api/v1/auth/me', JWTMeView.as_view(), name='jwt-me'),
    path('api/v1/auth/change-password', JWTChangePasswordView.as_view(), name='jwt-change-password'),

    path('admin/', admin.site.urls),
    path('health', health_check),
    path('api/v1/', include('api.urls')),
    path('api/chats/', include('api.chats_urls')),
    path('api/v1/chats/', include('api.chats_urls')),

    # Swagger docs
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/docs/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
