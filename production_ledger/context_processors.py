from .models import ShowRoleAssignment
from .permissions import get_user_organization_uuid


def user_role_context(request):
    """Add is_guest_user flag and unread_comment_count to template context."""
    if not request.user.is_authenticated:
        return {}

    if request.user.is_superuser:
        return {'is_guest_user': False, 'unread_comment_count': 0}

    # User is guest-only if they have no role assignments >= editor
    has_non_guest_role = ShowRoleAssignment.objects.filter(
        user=request.user,
    ).exclude(role='guest').exists()

    # Unread comment badge count (new top-level comments only)
    unread_count = 0
    try:
        from .models import PlatformComment  # noqa: PLC0415
        from .constants import CommentStatus  # noqa: PLC0415
        org_uuid = get_user_organization_uuid(request.user)
        if org_uuid:
            unread_count = PlatformComment.objects.filter(
                organization_uuid=org_uuid,
                status=CommentStatus.NEW,
                parent__isnull=True,
            ).count()
    except Exception:
        pass

    return {
        'is_guest_user': not has_non_guest_role,
        'unread_comment_count': unread_count,
    }
