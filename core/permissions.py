from rest_framework import permissions


def is_authority_user(user):
    return bool(
        user and user.is_authenticated and (
            user.groups.filter(name='EmergencyTeam').exists() or user.is_superuser
        )
    )


def is_admin_user(user):
    return bool(user and user.is_authenticated and user.is_superuser)


def is_government_user(user):
    return bool(
        user and user.is_authenticated and (
            user.groups.filter(name__in=['GovernmentTeam', 'EmergencyTeam']).exists() or user.is_superuser
        )
    )


def is_meteo_user(user):
    return bool(
        user and user.is_authenticated and (
            user.groups.filter(name='MeteorologicalTeam').exists() or user.is_superuser
        )
    )


def is_ngo_user(user):
    return bool(
        user and user.is_authenticated and (
            user.groups.filter(name='NGOTeam').exists() or user.is_superuser
        )
    )


def is_researcher_user(user):
    return bool(
        user and user.is_authenticated and (
            user.groups.filter(name='ResearchTeam').exists() or user.is_superuser
        )
    )


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


class IsGovernment(permissions.BasePermission):
    """
    Allows access to GovernmentTeam or EmergencyTeam or superuser.
    """
    def has_permission(self, request, view):
        return is_government_user(request.user)


class IsMeteoOfficer(permissions.BasePermission):
    """
    Allows access to MeteorologicalTeam or superuser.
    """
    def has_permission(self, request, view):
        return is_meteo_user(request.user)


class IsNGO(permissions.BasePermission):
    """
    Allows access to NGOTeam or superuser.
    """
    def has_permission(self, request, view):
        return is_ngo_user(request.user)


class IsResearcher(permissions.BasePermission):
    """
    Allows access to ResearchTeam or superuser.
    """
    def has_permission(self, request, view):
        return is_researcher_user(request.user)