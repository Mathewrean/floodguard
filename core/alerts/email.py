"""
Email alert system for FloodGuard.
Sends flood alerts via SMTP email as an alternative to SMS.
"""

import logging
from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def build_email_alert(zone, risk_score, recipient_email):
    """
    Build and send email alert for flood warning.
    
    Args:
        zone: AlertZone instance
        risk_score: float (0.0-1.0)
        recipient_email: str - email address of recipient
    
    Returns:
        bool: True if sent successfully, False otherwise
    """
    if risk_score >= 0.85:
        severity = 'CRITICAL'
        subject = f'CRITICAL FLOOD ALERT - {zone.name}'
        template = 'emails/critical_alert.html'
    elif risk_score >= 0.70:
        severity = 'HIGH'
        subject = f'HIGH FLOOD RISK - {zone.name}'
        template = 'emails/high_alert.html'
    elif risk_score >= 0.40:
        severity = 'MODERATE'
        subject = f'MODERATE FLOOD WATCH - {zone.name}'
        template = 'emails/moderate_alert.html'
    else:
        severity = 'SAFE'
        subject = f'SAFE FLOOD UPDATE - {zone.name}'
        template = 'emails/advisory_alert.html'
    
    # Context for email template
    context = {
        'zone_name': zone.name,
        'risk_score': round(risk_score * 100, 1),
        'severity': severity,
        'risk_threshold': round(zone.risk_threshold * 100, 1),
        'timestamp': severity,
    }
    
    return send_email_alert(recipient_email, subject, template, context)


def send_email_alert(recipient_email, subject, template, context):
    """
    Send email using HTML template with plain text fallback.
    """
    if not settings.EMAIL_BACKEND or 'django.core.mail.backends.smtp.EmailBackend' not in settings.EMAIL_BACKEND:
        logger.warning("Email backend not configured; skipping email to %s", recipient_email)
        return False
    
    try:
        # Render HTML email
        html_content = render_to_string(template, context)
        text_content = strip_tags(html_content)
        
        # Create email message
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else 'noreply@floodguard.com',
            to=[recipient_email]
        )
        email.attach_alternative(html_content, "text/html")
        
        # Send
        email.send(fail_silently=False)
        logger.info("Email alert sent to %s: %s", recipient_email, subject)
        return True
        
    except Exception as e:
        logger.error("Failed to send email to %s: %s", recipient_email, str(e), exc_info=True)
        return False


def send_email_summary(recipient_email, zone_stats):
    """
    Send daily/weekly summary email with zone statuses.
    """
    subject = f"FloodGuard Daily Summary - {len(zone_stats)} zones monitored"
    
    context = {
        'zone_stats': zone_stats,
        'date': timezone.now().strftime('%Y-%m-%d'),
    }
    
    try:
        html_content = render_to_string('emails/daily_summary.html', context)
        text_content = strip_tags(html_content)
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@floodguard.com'),
            to=[recipient_email]
        )
        email.attach_alternative(html_content, "text/html")
        email.send()
        return True
    except Exception as e:
        logger.error("Failed to send summary email: %s", e)
        return False
