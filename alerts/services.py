from alerts.models import FloodAlert

THRESHOLDS = {
    "river_level": {"MEDIUM": 4.0, "HIGH": 6.0},
    "rainfall": {"MEDIUM": 50, "HIGH": 100},
}

def evaluate_alert(location, parameter, value):
    if parameter not in THRESHOLDS:
        return None

    severity = None
    limits = THRESHOLDS[parameter]

    if value >= limits["HIGH"]:
        severity = "HIGH"
    elif value >= limits["MEDIUM"]:
        severity = "MEDIUM"

    if severity:
        return FloodAlert.objects.create(
            location=location,
            parameter=parameter,
            value=value,
            threshold=limits[severity],
            severity=severity,
        )
