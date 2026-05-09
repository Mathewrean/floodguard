"""
Security Middleware for FloodGuard

Adds security headers to all responses:
- Content-Security-Policy (CSP)
- X-Frame-Options
- X-Content-Type-Options
- X-XSS-Protection
- Referrer-Policy
- Strict-Transport-Security (HSTS) in production
- Permissions-Policy
"""

from django.utils.deprecation import MiddlewareMixin
from django.conf import settings


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Adds security headers to all HTTP responses.
    """
    
    def process_response(self, request, response):
        # CSP - Content Security Policy
        # Define allowed sources for scripts, styles, images, etc.
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' https://unpkg.com",
            "style-src 'self' 'unsafe-inline' https://unpkg.com",
            "img-src 'self' data: https://*.tile.openstreetmap.org https://*.cartocdn.com",
            "font-src 'self' data:",
            "connect-src 'self' ws: wss: https://api.open-meteo.com https://api.africastalking.com",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
        response['Content-Security-Policy'] = "; ".join(csp_directives)
        
        # X-Frame-Options - prevent clickjacking
        if 'X-Frame-Options' not in response:
            response['X-Frame-Options'] = 'DENY'
        
        # X-Content-Type-Options - prevent MIME sniffing
        if 'X-Content-Type-Options' not in response:
            response['X-Content-Type-Options'] = 'nosniff'
        
        # X-XSS-Protection - enable browser XSS filter
        if 'X-XSS-Protection' not in response:
            response['X-XSS-Protection'] = '1; mode=block'
        
        # Referrer-Policy - control referrer header
        if 'Referrer-Policy' not in response:
            response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Permissions-Policy - limit browser features
        permissions = [
            "geolocation=(self)",
            "microphone=()",
            "camera=()",
        ]
        response['Permissions-Policy'] = ", ".join(permissions)
        
        # HSTS - only in production when DEBUG=False
        if not settings.DEBUG and 'Strict-Transport-Security' not in response:
            response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        
        return response


class XRobotsTagMiddleware(MiddlewareMixin):
    """
    Add X-Robots-Tag header to prevent indexing of non-public areas.
    """
    
    def process_response(self, request, response):
        # Add noindex, nofollow to admin and private pages
        if request.path.startswith('/admin') or request.path.startswith('/dashboard'):
            response['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
        return response
