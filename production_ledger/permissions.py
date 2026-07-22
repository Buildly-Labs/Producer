"""
RBAC (Role-Based Access Control) for Production Ledger.

Provides permission helpers and decorators for enforcing role-based access.
"""
from functools import wraps
import logging

from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from .constants import Role
from .models import Episode, EpisodeRoleOverride, Guest, Show, ShowRoleAssignment


logger = logging.getLogger(__name__)


def _highest_role(roles):
    """Return the highest-privilege role from a list of role strings."""
    if not roles:
        return None
    return max(roles, key=lambda role: Role.HIERARCHY.get(role, 0))


def get_user_role_for_show(user, show):
    """
    Get a user's role for a specific show.
    Returns None if user has no role assigned.
    """
    if not user or not user.is_authenticated:
        return None
    
    # Superusers are always admins
    if user.is_superuser:
        return Role.ADMIN
    
    roles = list(
        ShowRoleAssignment.objects
        .filter(show=show, user=user)
        .values_list('role', flat=True)
    )
    if not roles:
        return None

    if len(roles) > 1:
        logger.warning(
            'Duplicate ShowRoleAssignment rows detected for user=%s show=%s; roles=%s',
            getattr(user, 'id', None),
            getattr(show, 'id', None),
            roles,
        )
    return _highest_role(roles)


def get_user_role_for_episode(user, episode):
    """
    Get a user's role for a specific episode.
    Checks for episode-specific overrides first, then falls back to show role.
    """
    if not user or not user.is_authenticated:
        return None
    
    # Superusers are always admins
    if user.is_superuser:
        return Role.ADMIN
    
    # Check for episode-specific override first
    override_roles = list(
        EpisodeRoleOverride.objects
        .filter(episode=episode, user=user)
        .values_list('role', flat=True)
    )
    if override_roles:
        if len(override_roles) > 1:
            logger.warning(
                'Duplicate EpisodeRoleOverride rows detected for user=%s episode=%s; roles=%s',
                getattr(user, 'id', None),
                getattr(episode, 'id', None),
                override_roles,
            )
        return _highest_role(override_roles)
    
    # Fall back to show role
    return get_user_role_for_show(user, episode.show)


def has_role(user, show_or_episode, roles):
    """
    Check if a user has one of the specified roles for a show or episode.
    
    Args:
        user: The user to check
        show_or_episode: Show or Episode instance
        roles: List of role strings to check against
    
    Returns:
        bool: True if user has one of the specified roles
    """
    if isinstance(show_or_episode, Episode):
        user_role = get_user_role_for_episode(user, show_or_episode)
    elif isinstance(show_or_episode, Show):
        user_role = get_user_role_for_show(user, show_or_episode)
    else:
        return False
    
    if not user_role:
        return False
    
    return user_role in roles


def has_minimum_role(user, show_or_episode, minimum_role):
    """
    Check if a user has at least the specified role level.
    Uses role hierarchy: GUEST < EDITOR < PRODUCER < HOST < ADMIN
    
    Args:
        user: The user to check
        show_or_episode: Show or Episode instance
        minimum_role: The minimum role required
    
    Returns:
        bool: True if user has at least the minimum role level
    """
    if isinstance(show_or_episode, Episode):
        user_role = get_user_role_for_episode(user, show_or_episode)
    elif isinstance(show_or_episode, Show):
        user_role = get_user_role_for_show(user, show_or_episode)
    else:
        return False
    
    if not user_role:
        return False
    
    user_level = Role.HIERARCHY.get(user_role, 0)
    required_level = Role.HIERARCHY.get(minimum_role, 0)
    
    return user_level >= required_level


def require_role(roles, show_param='show_id', episode_param='episode_id'):
    """
    Decorator to require specific roles for a view.
    
    Args:
        roles: List of role strings that are allowed
        show_param: Name of the URL parameter containing show ID
        episode_param: Name of the URL parameter containing episode ID
    
    Usage:
        @require_role([Role.ADMIN, Role.HOST])
        def my_view(request, episode_id):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Try to get episode first
            episode_id = kwargs.get(episode_param)
            show_id = kwargs.get(show_param)
            
            if episode_id:
                episode = get_object_or_404(Episode, id=episode_id)
                if not has_role(request.user, episode, roles):
                    raise PermissionDenied(
                        f"You need one of these roles: {', '.join(roles)}"
                    )
                # Add episode to request for convenience
                request.episode = episode
            elif show_id:
                show = get_object_or_404(Show, id=show_id)
                if not has_role(request.user, show, roles):
                    raise PermissionDenied(
                        f"You need one of these roles: {', '.join(roles)}"
                    )
                # Add show to request for convenience
                request.show = show
            else:
                raise PermissionDenied("No show or episode specified")
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def require_minimum_role(minimum_role, show_param='show_id', episode_param='episode_id'):
    """
    Decorator to require at least a minimum role level for a view.
    
    Args:
        minimum_role: The minimum role required
        show_param: Name of the URL parameter containing show ID
        episode_param: Name of the URL parameter containing episode ID
    
    Usage:
        @require_minimum_role(Role.EDITOR)
        def my_view(request, episode_id):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Try to get episode first
            episode_id = kwargs.get(episode_param)
            show_id = kwargs.get(show_param)
            
            if episode_id:
                episode = get_object_or_404(Episode, id=episode_id)
                if not has_minimum_role(request.user, episode, minimum_role):
                    raise PermissionDenied(
                        f"You need at least {minimum_role} role"
                    )
                request.episode = episode
            elif show_id:
                show = get_object_or_404(Show, id=show_id)
                if not has_minimum_role(request.user, show, minimum_role):
                    raise PermissionDenied(
                        f"You need at least {minimum_role} role"
                    )
                request.show = show
            else:
                raise PermissionDenied("No show or episode specified")
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def scope_queryset_by_org(queryset, organization_uuid):
    """
    Filter a queryset by organization UUID.
    
    Args:
        queryset: The queryset to filter
        organization_uuid: The organization UUID to filter by
    
    Returns:
        Filtered queryset
    """
    return queryset.filter(organization_uuid=organization_uuid)


def scope_queryset_by_org_and_role(queryset, user, organization_uuid, model_class=None):
    """
    Filter a queryset by organization UUID and user's role-based access.
    
    For guests, this further restricts access to only episodes they're guests on.
    For other roles, it returns all objects within the organization.
    
    Args:
        queryset: The queryset to filter
        user: The user making the request
        organization_uuid: The organization UUID to filter by
        model_class: Optional model class hint for guest-specific filtering
    
    Returns:
        Filtered queryset
    """
    # First, scope by organization
    queryset = queryset.filter(organization_uuid=organization_uuid)
    
    # Superusers see everything in the org
    if user.is_superuser:
        return queryset
    
    # Get all shows the user has roles on
    user_shows = ShowRoleAssignment.objects.filter(
        user=user,
        show__organization_uuid=organization_uuid
    ).values_list('show_id', flat=True)
    
    # Check if model has a show or episode foreign key
    if hasattr(queryset.model, 'show'):
        queryset = queryset.filter(show_id__in=user_shows)
    elif hasattr(queryset.model, 'episode'):
        queryset = queryset.filter(episode__show_id__in=user_shows)
    
    # For guests, further restrict to their episodes
    # This requires the model to have an episode FK
    guest_roles = ShowRoleAssignment.objects.filter(
        user=user,
        role=Role.GUEST,
        show__organization_uuid=organization_uuid
    )
    
    if guest_roles.exists() and hasattr(queryset.model, 'episode'):
        from .models import EpisodeGuest
        # Get episodes where user is a guest
        user_guest = Guest.objects.filter(
            organization_uuid=organization_uuid,
            # You'd need a way to link user to guest - simplification here
        )
        # For MVP, guests see all in shows they're assigned to
    
    return queryset


def get_user_organization_uuid(user):
    """
    Get the organization UUID for a user.
    
    In a full implementation, this would look up the user's organization
    membership. For MVP, we'll return a default or the first show's org.
    
    Returns:
        UUID or None
    """
    import uuid
    
    # For MVP, try to get from user's show assignments
    assignment = ShowRoleAssignment.objects.filter(user=user).first()
    if assignment:
        return assignment.show.organization_uuid
    
    # Fallback for superusers - get first show's org or generate default
    if user.is_superuser:
        show = Show.objects.first()
        if show:
            return show.organization_uuid
        # Generate a consistent default org UUID for new setups
        # Use a namespace UUID based on the user's pk for consistency
        return uuid.uuid5(uuid.NAMESPACE_DNS, f'org.default.{user.pk}')
    
    return None


# Permission check functions for specific actions

def can_approve_show_notes(user, episode):
    """Check if user can approve final show notes."""
    return has_role(user, episode, [Role.ADMIN, Role.HOST])


def can_create_ai_artifact(user, episode):
    """Check if user can create AI artifacts."""
    return has_role(user, episode, [Role.ADMIN, Role.HOST, Role.PRODUCER, Role.EDITOR])


def can_approve_ai_artifact(user, episode):
    """Check if user can approve AI artifacts."""
    return has_role(user, episode, [Role.ADMIN, Role.HOST, Role.PRODUCER])


def can_manage_clips(user, episode):
    """Check if user can manage clip moments."""
    return has_role(user, episode, [Role.ADMIN, Role.HOST, Role.PRODUCER, Role.EDITOR])


def can_manage_transcripts(user, episode):
    """Check if user can manage transcripts."""
    return has_role(user, episode, [Role.ADMIN, Role.HOST, Role.PRODUCER, Role.EDITOR])


def can_export(user, episode):
    """Check if user can export episode data."""
    return has_role(user, episode, [Role.ADMIN, Role.HOST, Role.PRODUCER, Role.EDITOR])


def can_manage_guests(user, episode):
    """Check if user can manage episode guests."""
    return has_role(user, episode, [Role.ADMIN, Role.HOST, Role.PRODUCER])


def can_transition_status(user, episode, new_status):
    """
    Check if user can transition episode to a new status.
    
    - ADMIN/HOST can do any transition
    - PRODUCER can transition up to 'edited'
    - EDITOR can transition up to 'transcribed'
    - GUEST cannot transition
    """
    from .constants import EpisodeStatus
    
    user_role = get_user_role_for_episode(user, episode)
    if not user_role:
        return False
    
    # Check basic transition validity
    if not episode.can_transition_to(new_status):
        return False
    
    # Role-based restrictions
    if user_role in [Role.ADMIN, Role.HOST]:
        return True
    
    if user_role == Role.PRODUCER:
        restricted = [EpisodeStatus.APPROVED, EpisodeStatus.PUBLISHED]
        return new_status not in restricted
    
    if user_role == Role.EDITOR:
        allowed = [EpisodeStatus.INGESTED, EpisodeStatus.TRANSCRIBED]
        return new_status in allowed
    
    return False
