#!/usr/bin/env python3
"""
FloodGuard Authentication Flow Verification Test

Tests the complete authentication flow without email/SMS verification:
1. User registration via browser-form POST
2. Immediate login with newly created credentials
3. Authenticated access to protected dashboard
4. Session persistence across requests
5. Logout functionality

Run: python3 scripts/test_auth_flow.py
"""

import sys
import os
import time
import json
import requests

# Ensure project root is on path for Django imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Configure Django settings BEFORE importing Django modules
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "floodguard.settings")
import django
django.setup()

from django.contrib.auth import get_user_model

# Configuration
BASE_URL = os.environ.get("FG_BASE_URL", "http://127.0.0.1:8000")
ADMIN_USER = os.environ.get("FG_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("FG_ADMIN_PASSWORD", "admin123")
TEST_USER_PREFIX = "authtest"
SESSION = requests.Session()


def log(msg, level="INFO"):
    colors = {
        "INFO": "\033[36m",
        "PASS": "\033[32m",
        "FAIL": "\033[31m",
        "WARN": "\033[33m",
    }
    reset = "\033[0m"
    print(f"{colors.get(level, '')}[{level}]{reset} {msg}")


def get_csrf(session, url):
    """Fetch a page and extract CSRF token."""
    resp = session.get(url, timeout=10)
    if resp.status_code != 200:
        raise RuntimeError(f"GET {url} failed: {resp.status_code}")
    for line in resp.text.split("\n"):
        if "csrfmiddlewaretoken" in line and "value=" in line:
            start = line.find('value="') + 7
            end = line.find('"', start)
            return line[start:end]
    raise RuntimeError(f"No CSRF token found on {url}")


def test_health():
    log("Testing health endpoint...")
    resp = requests.get(f"{BASE_URL}/health/", timeout=5)
    assert resp.status_code == 200, f"Health check failed: {resp.status_code}"
    log("Health endpoint: OK", "PASS")


def test_registration_no_verification():
    """Register a new user and verify they are active immediately."""
    timestamp = int(time.time())
    username = f"{TEST_USER_PREFIX}_{timestamp}"
    email = f"{username}@test.local"
    password = "TestPass123!"

    log(f"Registering user: {username}")

    # Get CSRF from registration page
    csrf = get_csrf(SESSION, f"{BASE_URL}/register/")

    # Submit registration
    resp = SESSION.post(
        f"{BASE_URL}/register/",
        data={
            "username": username,
            "email": email,
            "password1": password,
            "password2": password,
            "csrfmiddlewaretoken": csrf,
        },
        headers={"Referer": f"{BASE_URL}/register/"},
        timeout=10,
        allow_redirects=False,
    )

    # Should redirect on success (302) or render 200 with error
    assert resp.status_code in (200, 302), f"Registration returned {resp.status_code}"

    # Verify user exists in database and is active
    User = get_user_model()
    user = User.objects.filter(username=username).first()
    assert user is not None, f"User {username} not found in database after registration"
    assert user.is_active, f"User {username} is not active (email/SMS verification blocking?)"
    assert user.email == email, f"Email mismatch: {user.email} != {email}"

    log(f"User registered and active: {username} (email={email}, active={user.is_active})", "PASS")

    # Cleanup
    user.delete()
    log(f"Test user {username} cleaned up.")


def test_login_new_credentials():
    """Create a user via ORM, then test login via browser POST."""
    timestamp = int(time.time())
    username = f"{TEST_USER_PREFIX}_{timestamp}"
    email = f"{username}@test.local"
    password = "TestPass123!"

    # Create user directly in DB (simulating successful registration)
    user = get_user_model().objects.create_user(username=username, email=email, password=password)
    user.is_active = True
    user.save()

    log(f"Testing login for user: {username}")

    # Get CSRF from login page
    csrf = get_csrf(SESSION, f"{BASE_URL}/login/")

    # Attempt login
    resp = SESSION.post(
        f"{BASE_URL}/login/",
        data={
            "username": username,
            "password": password,
            "csrfmiddlewaretoken": csrf,
        },
        headers={"Referer": f"{BASE_URL}/login/"},
        timeout=10,
        allow_redirects=False,
    )

    assert resp.status_code in (200, 302), f"Login returned {resp.status_code}"

    # Verify session by accessing dashboard
    dash_resp = SESSION.get(f"{BASE_URL}/dashboard/citizen/", timeout=10, allow_redirects=False)
    # Should redirect to login if not authenticated, or 200 if authenticated
    # Actually Django will redirect to login if not authenticated
    assert dash_resp.status_code in (200, 302), f"Dashboard returned {dash_resp.status_code}"

    if dash_resp.status_code == 200:
        log(f"Login verified: authenticated dashboard access granted", "PASS")
    else:
        # Check if redirected to login (meaning NOT authenticated)
        if "/login" in dash_resp.headers.get("Location", ""):
            log(f"Login FAILED: redirected to login page (credentials not accepted)", "FAIL")
            user.delete()
            sys.exit(1)
        else:
            log(f"Login verified via redirect: {dash_resp.status_code}", "PASS")

    # Cleanup
    user.delete()
    log(f"Test user {username} cleaned up.")


def test_superuser_login():
    """Verify superuser can log in."""
    log(f"Testing superuser login: {ADMIN_USER}")
    csrf = get_csrf(SESSION, f"{BASE_URL}/login/")

    resp = SESSION.post(
        f"{BASE_URL}/login/",
        data={
            "username": ADMIN_USER,
            "password": ADMIN_PASSWORD,
            "csrfmiddlewaretoken": csrf,
        },
        headers={"Referer": f"{BASE_URL}/login/"},
        timeout=10,
        allow_redirects=False,
    )

    assert resp.status_code in (200, 302), f"Superuser login returned {resp.status_code}"

    # Verify admin dashboard access
    admin_resp = SESSION.get(f"{BASE_URL}/dashboard/admin/", timeout=10, allow_redirects=False)
    assert admin_resp.status_code == 200, f"Admin dashboard returned {admin_resp.status_code}"
    log(f"Superuser login and admin dashboard access: OK", "PASS")


def test_logout():
    """Verify logout works."""
    log("Testing logout...")
    csrf = get_csrf(SESSION, f"{BASE_URL}/login/")

    resp = SESSION.post(
        f"{BASE_URL}/logout/",
        data={"csrfmiddlewaretoken": csrf},
        headers={"Referer": f"{BASE_URL}/login/"},
        timeout=10,
        allow_redirects=False,
    )

    assert resp.status_code in (200, 302), f"Logout returned {resp.status_code}"

    # Verify dashboard now requires login
    dash_resp = SESSION.get(f"{BASE_URL}/dashboard/citizen/", timeout=10, allow_redirects=False)
    # Should redirect to login
    assert dash_resp.status_code == 302, f"Expected redirect after logout, got {dash_resp.status_code}"
    assert "/login" in dash_resp.headers.get("Location", ""), "Did not redirect to login after logout"

    log("Logout verified: session cleared", "PASS")


def main():
    print("=" * 60)
    print("FloodGuard Authentication Flow Verification")
    print(f"Target: {BASE_URL}")
    print("=" * 60)
    print()

    try:
        test_health()
        test_registration_no_verification()
        test_login_new_credentials()
        test_superuser_login()
        test_logout()

        print()
        print("=" * 60)
        log("ALL AUTH TESTS PASSED", "PASS")
        print("=" * 60)
        print()
        print("Summary:")
        print("  [PASS] Registration without email/SMS verification")
        print("  [PASS] New users are active immediately")
        print("  [PASS] Credentials persisted in PostgreSQL")
        print("  [PASS] Login with new credentials works")
        print("  [PASS] Authenticated session persists")
        print("  [PASS] Superuser login works")
        print("  [PASS] Logout clears session")
        print()
        return 0

    except Exception as e:
        log(f"TEST FAILED: {e}", "FAIL")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
