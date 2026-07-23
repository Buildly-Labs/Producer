"""
Local engine registration, session management, and heartbeat handling.

Security model:
- Registration key is one-time use, returned only once
- Session tokens are short-lived (default 1 hour, configurable)
- Every session validated against browser origin
- All operations audited (created_by, created_at)
"""
import secrets
from datetime import timedelta
from typing import Optional

from django.utils import timezone
from django.core.exceptions import ValidationError

from splice.models import LocalEngineInstallation, LocalEngineSession


class LocalEngineService:
    """Service for local engine lifecycle management."""

    DEFAULT_SESSION_DURATION_MINUTES = 60
    REGISTRATION_KEY_LENGTH = 32

    @staticmethod
    def register_engine(
        org_uuid,
        engine_name: str,
        platform: str,
        user=None,
    ) -> tuple[LocalEngineInstallation, str]:
        """
        Register a new local engine installation.

        Args:
            org_uuid: Organization UUID
            engine_name: User-friendly name for this engine
            platform: OS platform (windows, macos, linux)
            user: User performing the registration (for audit trail)

        Returns:
            Tuple of (LocalEngineInstallation instance, registration_key)
            The registration_key is returned only once and should not be logged.

        Raises:
            ValidationError: If platform is invalid or name is duplicate
        """
        if platform not in ['windows', 'macos', 'linux']:
            raise ValidationError(f"Invalid platform: {platform}")

        if LocalEngineInstallation.objects.filter(
            organization_uuid=org_uuid,
            engine_name=engine_name
        ).exists():
            raise ValidationError(
                f"Engine name '{engine_name}' already exists in this organization"
            )

        # Generate unique engine_uuid and one-time registration key
        engine_uuid = __import__('uuid').uuid4()
        registration_key = secrets.token_urlsafe(LocalEngineService.REGISTRATION_KEY_LENGTH)

        # Hash the registration key for secure storage
        import hashlib
        registration_key_hash = hashlib.sha256(registration_key.encode()).hexdigest()

        # Create the installation record
        engine = LocalEngineInstallation.objects.create(
            organization_uuid=org_uuid,
            engine_name=engine_name,
            engine_uuid=engine_uuid,
            registration_key_hash=registration_key_hash,
            platform=platform,
            is_online=False,
            created_by=user,
        )

        return engine, registration_key

    @staticmethod
    def create_session(
        local_engine_id: str,
        browser_origin: str,
        expires_in_minutes: int = DEFAULT_SESSION_DURATION_MINUTES,
        user=None,
    ) -> LocalEngineSession:
        """
        Create a short-lived session for browser-to-engine communication.

        Args:
            local_engine_id: LocalEngineInstallation UUID
            browser_origin: Browser origin for validation (e.g., 'http://localhost:3000')
            expires_in_minutes: Session duration in minutes
            user: User creating the session (for audit trail)

        Returns:
            LocalEngineSession with session_token ready to return to browser

        Raises:
            LocalEngineInstallation.DoesNotExist: If engine not found
        """
        engine = LocalEngineInstallation.objects.get(id=local_engine_id)

        session_token = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timedelta(minutes=expires_in_minutes)

        session = LocalEngineSession.objects.create(
            organization_uuid=engine.organization_uuid,
            local_engine=engine,
            session_token=session_token,
            browser_origin=browser_origin,
            expires_at=expires_at,
            created_by=user,
        )

        return session

    @staticmethod
    def validate_session(
        session_token: str,
        browser_origin: str,
    ) -> Optional[LocalEngineInstallation]:
        """
        Validate a session token and return the associated engine.

        Checks:
        1. Token exists
        2. Token not expired
        3. Browser origin matches (CORS protection)

        Args:
            session_token: The session token from the browser
            browser_origin: The origin making the request

        Returns:
            LocalEngineInstallation if valid, None otherwise
        """
        try:
            session = LocalEngineSession.objects.get(session_token=session_token)
        except LocalEngineSession.DoesNotExist:
            return None

        # Check expiration
        if session.expires_at < timezone.now():
            return None

        # Validate origin
        if session.browser_origin != browser_origin:
            return None

        # Update heartbeat
        session.last_heartbeat = timezone.now()
        session.save(update_fields=['last_heartbeat'])

        return session.local_engine

    @staticmethod
    def heartbeat(local_engine_id: str) -> bool:
        """
        Record a heartbeat from a local engine.

        Updates last_heartbeat and marks engine as online.

        Args:
            local_engine_id: LocalEngineInstallation UUID

        Returns:
            True if heartbeat recorded successfully
        """
        try:
            engine = LocalEngineInstallation.objects.get(id=local_engine_id)
            engine.last_heartbeat = timezone.now()
            engine.is_online = True
            engine.save(update_fields=['last_heartbeat', 'is_online'])
            return True
        except LocalEngineInstallation.DoesNotExist:
            return False

    @staticmethod
    def check_engine_offline(
        local_engine_id: str,
        timeout_minutes: int = 30,
    ) -> bool:
        """
        Check if an engine should be marked offline (no heartbeat).

        Args:
            local_engine_id: LocalEngineInstallation UUID
            timeout_minutes: Minutes without heartbeat before offline

        Returns:
            True if engine has timed out, False otherwise
        """
        try:
            engine = LocalEngineInstallation.objects.get(id=local_engine_id)
            if not engine.last_heartbeat:
                return False

            timeout_threshold = timezone.now() - timedelta(minutes=timeout_minutes)
            if engine.last_heartbeat < timeout_threshold:
                engine.is_online = False
                engine.save(update_fields=['is_online'])
                return True
            return False
        except LocalEngineInstallation.DoesNotExist:
            return False

    @staticmethod
    def cleanup_expired_sessions(older_than_days: int = 7) -> int:
        """
        Remove expired sessions older than specified days.

        Args:
            older_than_days: Delete sessions expired more than N days ago

        Returns:
            Number of sessions deleted
        """
        cutoff = timezone.now() - timedelta(days=older_than_days)
        count, _ = LocalEngineSession.objects.filter(expires_at__lt=cutoff).delete()
        return count
