"""
Authentication for local engine <-> cloud API requests.

Local engines are not Django Users - they authenticate with the
registration_key issued at registration time, never a user session
or user API token. This keeps the engine's credential scoped to
exactly one LocalEngineInstallation (and therefore one organization),
independent of any human user's login state.

Header format:
    Authorization: Engine <engine_uuid>:<raw_registration_key>
"""
import hashlib

from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import authentication, exceptions

from splice.models import LocalEngineInstallation


class EngineAuthentication(authentication.BaseAuthentication):
    """
    Authenticates a LocalEngineInstallation via its registration key.

    On success, request.user is an AnonymousUser-like stand-in is NOT
    used; instead we set request.engine to the LocalEngineInstallation
    and return (engine, None) so DRF's request.user resolves to the
    engine object directly. Views/permissions that accept engine calls
    must be written against request.engine (or check isinstance on
    request.user), since it is not a real Django User.
    """

    keyword = 'Engine'

    def authenticate(self, request):
        auth_header = authentication.get_authorization_header(request).decode('utf-8')
        if not auth_header or not auth_header.startswith(f'{self.keyword} '):
            return None

        token = auth_header[len(self.keyword) + 1:].strip()
        if ':' not in token:
            raise exceptions.AuthenticationFailed('Malformed engine credentials.')

        engine_uuid, raw_key = token.split(':', 1)
        if not engine_uuid or not raw_key:
            raise exceptions.AuthenticationFailed('Malformed engine credentials.')

        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        try:
            engine = LocalEngineInstallation.objects.get(
                engine_uuid=engine_uuid,
                registration_key_hash=key_hash,
            )
        except (LocalEngineInstallation.DoesNotExist, ValueError, ValidationError):
            raise exceptions.AuthenticationFailed('Invalid engine credentials.')

        engine.last_heartbeat = timezone.now()
        engine.is_online = True
        engine.save(update_fields=['last_heartbeat', 'is_online'])

        request.engine = engine
        return (engine, None)
