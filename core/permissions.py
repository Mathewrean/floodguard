from rest_framework import permissions


class IsAuthority(permissions.BasePermission):
    """
    Allows access only to users with EmergencyTeam group membership.
    """
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            (
                request.user.groups.filter(name='EmergencyTeam').exists() or
                request.user.is_superuser
            )
        )


class IsAdminUser(permissions.BasePermission):
    """
    Allows access only to superuser accounts.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_superuser