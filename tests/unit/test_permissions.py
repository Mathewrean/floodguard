import pytest
from django.test import RequestFactory
from django.contrib.auth.models import AnonymousUser, User
from core.permissions import IsAuthority, IsAdminUser
from tests.factories import UserFactory, AuthorityUserFactory


@pytest.mark.django_db
class TestIsAuthority:
    def test_returns_true_for_authority_user(self):
        request = RequestFactory().get('/')
        user = AuthorityUserFactory()
        request.user = user
        permission = IsAuthority()
        assert permission.has_permission(request, None)

    def test_returns_false_for_citizen_user(self):
        request = RequestFactory().get('/')
        user = UserFactory()
        request.user = user
        permission = IsAuthority()
        assert not permission.has_permission(request, None)

    def test_returns_false_for_anonymous(self):
        request = RequestFactory().get('/')
        request.user = AnonymousUser()
        permission = IsAuthority()
        assert not permission.has_permission(request, None)


@pytest.mark.django_db
class TestIsAdminUser:
    def test_returns_true_for_superuser(self):
        request = RequestFactory().get('/')
        user = User.objects.create_superuser('admin', 'admin@test.com', 'pass')
        request.user = user
        permission = IsAdminUser()
        assert permission.has_permission(request, None)

    def test_returns_false_for_non_superuser(self):
        request = RequestFactory().get('/')
        user = UserFactory()
        request.user = user
        permission = IsAdminUser()
        assert not permission.has_permission(request, None)

    def test_returns_false_for_anonymous(self):
        request = RequestFactory().get('/')
        request.user = AnonymousUser()
        permission = IsAdminUser()
        assert not permission.has_permission(request, None)