from .models import ShowRoleAssignment


def user_role_context(request):
    """Add is_guest_user flag to template context."""
    if not request.user.is_authenticated:
        return {}

    if request.user.is_superuser:
        return {'is_guest_user': False}

    # User is guest-only if they have no role assignments >= editor
    has_non_guest_role = ShowRoleAssignment.objects.filter(
        user=request.user,
    ).exclude(role='guest').exists()

    return {'is_guest_user': not has_non_guest_role}
