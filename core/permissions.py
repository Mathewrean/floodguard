from rest_framework.permissions import BasePermission


class IsAuthority(BasePermission):
    """
    Custom permission to only allow users with authority or admin role.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            profile = request.user.profile
            return profile.role in ['authority', 'admin']
        except request.user.profile.RelatedObjectDoesNotExist:
            return False


class IsAdminUser(BasePermission):
    """
    Custom permission to only allow users with admin role.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            profile = request.user.profile
            return profile.role == 'admin'
        except request.user.profile.RelatedObjectDoesNotExist:
            return False