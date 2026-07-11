from rest_framework import permissions


def is_authority_user(user):
    return bool(
        user and user.is_authenticated and (
            user.groups.filter(name='EmergencyTeam').exists() or user.is_superuser
        )
    )


def is_admin_user(user):
    return bool(user and user.is_authenticated and user.is_superuser)


class IsAuthority(permissions.BasePermission):
    """
    Allows access only to users with EmergencyTeam group membership.
    """
    def has_permission(self, request, view):
        return is_authority_user(request.user)


class IsAdminUser(permissions.BasePermission):
    """
    Allows access only to superuser accounts.
    """
    def has_permission(self, request, view):
        return is_admin_user(request.user)