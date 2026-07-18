"""
Django settings for ExpenseIQ project.
SQLite database, DRF, CORS headers, JWT auth, rate limiting.
"""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-expenseiq-dev-key-change-in-production')

DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '*').split(',')

# ── Application definition ──
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',  # Token blacklisting for logout/rotation
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    # Local
    'api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Serve static files in production
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'api.middleware.EnsureCsrfCookieMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Custom rate limiter
    'api.middleware.RateLimitMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ── Database (SQLite by default, MySQL optional) ──
# Docker / production uses MySQL. Local dev falls back to SQLite.
USE_MYSQL = os.getenv('USE_MYSQL', 'False').lower() in ('true', '1', 'yes')

if USE_MYSQL:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.getenv('MYSQL_DATABASE', 'expensetracker'),
            'USER': os.getenv('MYSQL_USER', 'expenseuser'),
            'PASSWORD': os.getenv('MYSQL_PASSWORD', 'expensepass'),
            'HOST': os.getenv('MYSQL_HOST', 'db'),
            'PORT': os.getenv('MYSQL_PORT', '3306'),
            'OPTIONS': {
                'charset': 'utf8mb4',
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            },
            'CONN_MAX_AGE': 60,
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }



# ── Cache (for rate limiting) ──
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'expenseiq-ratelimit',
    }
}

# ── Internationalization ──
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ── Static files ──
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'          # collectstatic output dir
STATIC_ROOT.mkdir(exist_ok=True)
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
# WhiteNoise: compress & cache static files in production
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ── Default auto field ──
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── CORS ──
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = os.getenv('CORS_ORIGINS', 'http://localhost:3000,http://127.0.0.1:5500').split(',')
CORS_ALLOW_METHODS = ['DELETE', 'GET', 'OPTIONS', 'PATCH', 'POST', 'PUT']
CORS_ALLOW_HEADERS = ['accept', 'authorization', 'content-type', 'origin', 'x-requested-with']
CORS_ALLOW_CREDENTIALS = True  # Required for cookies to be sent cross-origin

# ── Django REST Framework ──
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'api.authentication.CookieJWTAuthentication',   # JWT via HTTP-only cookies (primary)
        'rest_framework.authentication.SessionAuthentication',  # Fallback for admin/browsable API
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': None,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DATETIME_FORMAT': '%Y-%m-%dT%H:%M:%S.%fZ',
    'DATE_FORMAT': '%Y-%m-%d',
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': os.getenv('RATE_LIMIT', '100/hour'),
    },
    'EXCEPTION_HANDLER': 'api.utils.custom_exception_handler',
}

# ═══════════════════════════════════════════════
#  JWT CONFIGURATION (SimpleJWT)
# ═══════════════════════════════════════════════
SIMPLE_JWT = {
    # Token lifetimes
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),       # Short-lived access token
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),          # Long-lived refresh token
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=15),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=7),

    # Token rotation — issue new refresh on every refresh request
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,   # Blacklist old refresh tokens after rotation

    # Security
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'UPDATE_LAST_LOGIN': True,          # Update user.last_login on token creation

    # Token claims
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'TOKEN_TYPE_CLAIM': 'token_type',
    'JTI_CLAIM': 'jti',                # Unique token ID for blacklisting
}

# ── Cookie names for JWT tokens ──
JWT_COOKIE_NAMES = {
    'access': 'access_token',
    'refresh': 'refresh_token',
}

# Firebase Cloud Messaging. The web values are public Firebase configuration;
# the service-account path must point to a private JSON key outside source control.
FIREBASE_SERVICE_ACCOUNT_PATH = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH', '')
FIREBASE_WEB_CONFIG = {
    'apiKey': os.getenv('FIREBASE_API_KEY', ''),
    'authDomain': os.getenv('FIREBASE_AUTH_DOMAIN', ''),
    'projectId': os.getenv('FIREBASE_PROJECT_ID', ''),
    'storageBucket': os.getenv('FIREBASE_STORAGE_BUCKET', ''),
    'messagingSenderId': os.getenv('FIREBASE_MESSAGING_SENDER_ID', ''),
    'appId': os.getenv('FIREBASE_APP_ID', ''),
    'vapidKey': os.getenv('FIREBASE_VAPID_KEY', ''),
}

# ═══════════════════════════════════════════════
#  RATE LIMIT CONFIGURATION
# ═══════════════════════════════════════════════
RATE_LIMIT_CONFIG = {
    'GLOBAL_RATE': '200/minute',         # 200 requests/min for normal endpoints
    'AUTH_RATE': '10/minute',            # 10 requests/min for auth endpoints (brute-force protection)
    'AUTH_PATHS': ['/api/v1/auth/'],     # Paths that use the stricter AUTH_RATE
    'BLOCK_DURATION': 300,               # Block IP for 5 minutes after exceeding limit
}

# ── Security Headers ──
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
CSRF_COOKIE_HTTPONLY = False   # Allow JavaScript to read the CSRF cookie for API requests
if not DEBUG:
    # Disable SSL redirect when running behind Nginx/reverse proxy in Docker
    # (the proxy handles HTTPS termination; enabling this causes redirect loops)
    SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'False').lower() in ('true', '1', 'yes')
    SECURE_HSTS_SECONDS = 31536000      # 1 year HSTS
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Trust the X-Forwarded-Proto header from Nginx
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ── File Uploads ──
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5MB

# ── Spectacular Settings ──
SPECTACULAR_SETTINGS = {
    'TITLE': 'ExpenseTracker API',
    'DESCRIPTION': 'Expense tracker API documentation',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# ── Pagination Limits ──
PAGINATION_DEFAULT_LIMIT = 20
PAGINATION_MAX_LIMIT = 100

# ── Authentication Redirects ──
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'login'
