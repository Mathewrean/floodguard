def build_alert_message(zone, risk_score):
    """
    Build an alert message based on the risk score and zone.
    Follows the decision tree specified in the requirements.
    """
    if risk_score >= 0.85:
        severity_label = 'CRITICAL'
        message = f"CRITICAL FLOOD ALERT — {zone.name}: Severe flooding imminent. Evacuate low-lying areas immediately. Avoid all roads near {zone.name}."
    elif risk_score >= 0.70:
        severity_label = 'HIGH'
        message = f"HIGH FLOOD RISK — {zone.name}: Significant flooding likely within 2 hours. Avoid drainage channels and low roads. Stay alert."
    elif risk_score >= 0.40:
        severity_label = 'MODERATE'
        message = f"MODERATE FLOOD RISK — {zone.name}: Flooding possible. Monitor conditions and avoid low-lying routes."
    else:
        severity_label = 'ADVISORY'
        message = f"FLOOD ADVISORY — {zone.name}: Conditions are being monitored. No immediate action required."

    # Append the standard footer
    message = f"{message} — FloodGuard. Reply STOP to unsubscribe."

    # Truncate to 159 characters for SMS (leaving room for potential encoding issues)
    # We'll log a warning and truncate if necessary
    if len(message) > 159:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Alert message exceeds 159 characters: {len(message)}. Truncating.")
        message = message[:159]

    return message, severity_label


def truncate_sms(message):
    """
    Utility function to truncate a message to 159 characters for SMS.
    Logs a warning if truncation occurs.
    """
    if len(message) > 159:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"SMS message exceeds 159 characters: {len(message)}. Truncating.")
        return message[:159]
    return message