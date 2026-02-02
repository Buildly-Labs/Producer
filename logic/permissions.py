import logging
from rest_framework.permissions import IsAuthenticated

logger = logging.getLogger(__name__)


class AllowOptionsAuthentication(IsAuthenticated):
    def has_permission(self, request, view):
        if request.method == 'OPTIONS' or request.user.is_superuser:
            return True

        if getattr(request, 'session', None) and \
                request.session.get('jwt_username') and\
                request.session.get('jwt_user_uuid'):
            return True
        return False
