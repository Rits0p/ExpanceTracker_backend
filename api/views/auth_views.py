"""
Authentication views for ExpenseIQ.
- Session-based auth for template pages (login_view, register_view, etc.)
- JWT API endpoints for programmatic auth (/api/v1/auth/*)
"""
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from ..authentication import CookieJWTAuthentication, clear_token_cookies, get_tokens_for_user, set_token_cookies
from ..utils import ApiResponse

# ═══════════════════════════════════════════════
#  TEMPLATE-BASED AUTH (Session — unchanged)
# ═══════════════════════════════════════════════

def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')

        if password != confirm_password:
            messages.error(request, 'Passwords do not match')
            return render(request, 'register.html')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already taken')
            return render(request, 'register.html')

        user = User.objects.create_user(username=username, email=email, password=password)
        login(request, user)
        messages.success(request, 'Account created successfully!')
        return redirect('home')

    return render(request, 'register.html')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        identifier = request.POST.get('identifier') or request.POST.get('username')
        password = request.POST.get('password')
        user = None
        if identifier:
            if '@' in identifier:
                user = User.objects.filter(email__iexact=identifier).first()
            if user is None:
                user = User.objects.filter(username__iexact=identifier).first()

        if user is not None:
            user = authenticate(request, username=user.username, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, f'Welcome back, {user.username}!')
            return redirect('home')
        else:
            messages.error(request, 'Invalid username/email or password')

    return render(request, 'login.html')


def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('login')


@login_required
def profile_view(request):
    if request.method == 'POST':
        user = request.user
        email = request.POST.get('email')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')

        # Update basic info
        user.email = email
        user.first_name = first_name
        user.last_name = last_name

        user.save()
        messages.success(request, 'Profile updated successfully!')
        return redirect('profile')

    return render(request, 'profile.html', {'user': request.user})


def password_reset_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        new_password = request.POST.get('new_password')
        try:
            user = User.objects.get(username=username)
            user.set_password(new_password)
            user.save()
            messages.success(request, 'Password reset successful! You can now log in.')
            return redirect('login')
        except User.DoesNotExist:
            messages.error(request, 'User with this username does not exist.')

    return render(request, 'password_reset.html')


# ═══════════════════════════════════════════════════════════
#  JWT API AUTH (Access + Refresh tokens in HTTP-only cookies)
# ═══════════════════════════════════════════════════════════

class JWTRegisterView(APIView):
    """
    POST /api/v1/auth/register
    Creates a new user and returns JWT tokens in HTTP-only cookies.

    Body: { username, email, password, confirmPassword }
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        username = request.data.get('username', '').strip()
        email = request.data.get('email', '').strip()
        password = request.data.get('password', '')
        confirm = request.data.get('confirmPassword', '')

        # Validation
        if not username or not email or not password:
            return ApiResponse.error('username, email, and password are required', 400)

        if password != confirm:
            return ApiResponse.error('Passwords do not match', 400)

        if len(password) < 8:
            return ApiResponse.error('Password must be at least 8 characters', 400)

        # Validate password strength via Django validators
        try:
            validate_password(password)
        except ValidationError as e:
            return ApiResponse.error('Weak password', 400, list(e.messages))

        if User.objects.filter(username__iexact=username).exists():
            return ApiResponse.error('Username already taken', 409)

        if User.objects.filter(email__iexact=email).exists():
            return ApiResponse.error('Email already registered', 409)

        # Create user
        user = User.objects.create_user(
            username=username, email=email, password=password
        )

        # Send welcome notification
        from ..notifications import notify_auth_event
        notify_auth_event(user, event_type="account_created",
                          title="Account created",
                          body="Welcome! Your MoneyMatrix account has been created.",
                          url="/settings/")

        # Generate JWT tokens
        tokens = get_tokens_for_user(user)

        response = ApiResponse.created(
            {
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                },
            },
            message='Account created successfully',
        )

        # Set tokens in HTTP-only cookies
        set_token_cookies(response, tokens)
        return response


class JWTLoginView(APIView):
    """
    POST /api/v1/auth/login
    Authenticates user and returns JWT tokens in HTTP-only cookies.

    Body: { identifier, password }
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        identifier = request.data.get('identifier', '').strip() or request.data.get('username', '').strip()
        password = request.data.get('password', '')

        if not identifier or not password:
            return ApiResponse.error('identifier and password are required', 400)

        user = None
        if identifier:
            # Prefer email lookup first when the identifier looks like an email
            if '@' in identifier:
                user = User.objects.filter(email__iexact=identifier).first()
            if user is None:
                user = User.objects.filter(username__iexact=identifier).first()

        if user is None:
            return ApiResponse.error('Invalid credentials', 401)

        # Check if user is active first, but verify password to prevent enum/timing attacks
        if not user.is_active:
            if not user.check_password(password):
                return ApiResponse.error('Invalid credentials', 401)

            try:
                from django.db import transaction
                from api.notifications import send_push_notification

                def deferred_send():
                    try:
                        send_push_notification(
                            user,
                            event_type="auth_account_disabled",
                            title="Account disabled",
                            body="Your MoneyMatrix account has been disabled.",
                        )
                    except Exception:
                        pass

                transaction.on_commit(deferred_send)
            except Exception:
                pass
            return ApiResponse.error('Account is disabled', 403)

        authenticated_user = authenticate(request, username=user.username, password=password)
        if authenticated_user is None:
            return ApiResponse.error('Invalid credentials', 401)

        # Also log into Django session (so template pages work too)
        login(request, authenticated_user)

        # Send login notification (new device / session)
        from ..notifications import notify_auth_event
        notify_auth_event(authenticated_user, event_type="auth_new_device_login",
                          title="New login",
                          body=f"Your account was accessed from {request.META.get('REMOTE_ADDR', 'unknown IP')}.",
                          url="/settings/")

        # Generate JWT tokens
        tokens = get_tokens_for_user(user)

        response = ApiResponse.success(
            {
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'firstName': user.first_name,
                    'lastName': user.last_name,
                },
            },
            message=f'Welcome back, {user.username}!',
        )

        # Set tokens in HTTP-only cookies
        set_token_cookies(response, tokens)
        return response


class JWTRefreshView(APIView):
    """
    POST /api/v1/auth/refresh
    Reads the refresh_token cookie, rotates tokens, and sets new cookies.
    No request body needed — the refresh token comes from the cookie.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        from django.conf import settings as django_settings
        refresh_token = request.COOKIES.get(
            django_settings.JWT_COOKIE_NAMES['refresh']
        )

        if not refresh_token:
            return ApiResponse.error('No refresh token provided', 401)

        try:
            old_refresh = RefreshToken(refresh_token)
            # Blacklist the old refresh token (rotation)
            old_refresh.blacklist()
        except TokenError:
            response = ApiResponse.error('Invalid or expired refresh token', 401)
            clear_token_cookies(response)
            return response

        # Issue new token pair
        user_id = old_refresh.payload.get('user_id')
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return ApiResponse.error('User not found', 404)

        tokens = get_tokens_for_user(user)
        response = ApiResponse.success(
            {'user': {'id': user.id, 'username': user.username}},
            message='Token refreshed',
        )
        set_token_cookies(response, tokens)
        return response


class JWTLogoutView(APIView):
    """
    POST /api/v1/auth/logout
    Blacklists the refresh token and clears all auth cookies.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        from django.conf import settings as django_settings
        refresh_token = request.COOKIES.get(
            django_settings.JWT_COOKIE_NAMES['refresh']
        )

        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except TokenError:
                pass  # Token was already invalid/expired — still clear cookies

        # Also clear Django session
        logout(request)

        response = ApiResponse.success(message='Logged out successfully')
        clear_token_cookies(response)
        return response


class JWTMeView(APIView):
    """
    GET /api/v1/auth/me
    Returns the currently authenticated user's profile.
    Requires valid access token.
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieJWTAuthentication]

    def get(self, request):
        user = request.user
        from ..models import UserSettings
        from ..serializers import UserSettingsSerializer
        settings, created = UserSettings.objects.get_or_create(user=user)
        settings_data = UserSettingsSerializer(settings).data

        return ApiResponse.success({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'firstName': user.first_name,
            'lastName': user.last_name,
            'dateJoined': user.date_joined.isoformat(),
            'lastLogin': user.last_login.isoformat() if user.last_login else None,
            'settings': settings_data,
        })


class JWTChangePasswordView(APIView):
    """
    POST /api/v1/auth/change-password
    Changes the user's password. Requires current password.

    Body: { currentPassword, newPassword, confirmPassword }
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieJWTAuthentication]

    def post(self, request):
        user = request.user
        current = request.data.get('currentPassword', '')
        new_pw = request.data.get('newPassword', '')
        confirm = request.data.get('confirmPassword', '')

        if not user.check_password(current):
            return ApiResponse.error('Current password is incorrect', 400)

        if new_pw != confirm:
            return ApiResponse.error('New passwords do not match', 400)

        if len(new_pw) < 8:
            return ApiResponse.error('Password must be at least 8 characters', 400)

        try:
            validate_password(new_pw, user=user)
        except ValidationError as e:
            return ApiResponse.error('Weak password', 400, list(e.messages))

        user.set_password(new_pw)
        user.save()

        from ..notifications import notify_auth_event
        notify_auth_event(user, event_type="auth_password_changed",
                          title="Password changed",
                          body="Your account password was changed successfully.",
                          url="/settings/")

        # Issue fresh tokens after password change
        tokens = get_tokens_for_user(user)
        response = ApiResponse.success(message='Password changed successfully')
        set_token_cookies(response, tokens)
        return response
