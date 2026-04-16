"""
Cross-app SSO authentication.

Reads the ``forge_auth`` cookie set by the Flask gateway and auto-creates /
logs in the corresponding Django user.  The cookie is HMAC-signed with a
shared secret so it cannot be forged.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)

AUTH_COOKIE_NAME = 'forge_auth'
SHARED_SECRET = os.getenv('SHARED_AUTH_SECRET', 'forge-shared-auth-2025')
MAX_AGE_SECONDS = 60 * 60 * 24 * 14  # 14 days — match Flask side


def _verify_token(token: str) -> dict | None:
    """
    Verify an HMAC-signed token.  Returns the payload dict or None.
    """
    try:
        encoded_payload, sig = token.rsplit('.', 1)
        payload_bytes = base64.urlsafe_b64decode(encoded_payload)
        expected_sig = hmac.new(
            SHARED_SECRET.encode(), payload_bytes, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        data = json.loads(payload_bytes)
        # Reject expired tokens
        if time.time() - data.get('ts', 0) > MAX_AGE_SECONDS:
            return None
        return data
    except Exception:
        return None


# ── Authentication backend ───────────────────────────────────

class GatewayTokenBackend(BaseBackend):
    """Authenticate a user based on a verified gateway token payload."""

    def authenticate(self, request, gateway_email=None, gateway_name=None, **kwargs):
        if not gateway_email:
            return None
        email = gateway_email.lower().strip()
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Auto-create — producer is behind gateway login anyway
            username = email.split('@')[0][:150]
            # Ensure unique username
            base = username
            n = 1
            while User.objects.filter(username=username).exists():
                username = f'{base}{n}'
                n += 1
            user = User.objects.create_user(
                username=username,
                email=email,
                first_name=(gateway_name or '').split()[0][:30] if gateway_name else '',
            )
            user.set_unusable_password()
            user.save()
            logger.info('Auto-created Django user for gateway SSO: %s', email)
        return user

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None


# ── Middleware ────────────────────────────────────────────────

class GatewaySSOMiddleware:
    """
    If the user is not authenticated in Django but carries a valid
    ``forge_auth`` cookie from the Flask gateway, log them in automatically.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            token = request.COOKIES.get(AUTH_COOKIE_NAME)
            if token:
                payload = _verify_token(token)
                if payload and payload.get('email'):
                    user = GatewayTokenBackend().authenticate(
                        request,
                        gateway_email=payload['email'],
                        gateway_name=payload.get('name', ''),
                    )
                    if user:
                        login(request, user, backend='production_ledger.gateway_auth.GatewayTokenBackend')

        return self.get_response(request)
