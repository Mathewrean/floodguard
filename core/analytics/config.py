"""
Configurable weights for flood risk calculation.
All weights are defined in settings with environment variable overrides.
"""

from django.conf import settings

def get_risk_weights():
    """Get risk calculation weights from settings or defaults."""
    return {
        # Discharge weights
        'discharge_current': getattr(settings, 'RISK_WEIGHT_DISCHARGE_CURRENT', 0.50),
        'discharge_24h': getattr(settings, 'RISK_WEIGHT_DISCHARGE_24H', 0.30),
        'discharge_7d': getattr(settings, 'RISK_WEIGHT_DISCHARGE_7D', 0.20),
        
        # Precipitation weights (combined in precip_component)
        'precip_weight': getattr(settings, 'RISK_WEIGHT_PRECIP', 0.30),
        
        # Environmental weights
        'humidity_weight': getattr(settings, 'RISK_WEIGHT_HUMIDITY', 0.60),
        'sar_water_weight': getattr(settings, 'RISK_WEIGHT_SAR_WATER', 0.40),
        'env_total_weight': getattr(settings, 'RISK_WEIGHT_ENVIRONMENTAL', 0.25),
        
        # Overall component weights
        'discharge_total_weight': getattr(settings, 'RISK_WEIGHT_DISCHARGE', 0.45),
        
        # Confidence penalties
        'confidence_single_source_penalty': getattr(settings, 'RISK_CONFIDENCE_PENALTY_1', 0.80),
        'confidence_two_source_penalty': getattr(settings, 'RISK_CONFIDENCE_PENALTY_2', 0.90),
    }


def get_h3_resolution_config():
    """Get H3 resolution configuration for different geographic contexts."""
    return {
        'urban': getattr(settings, 'H3_RESOLUTION_URBAN', 7),
        'semi_urban': getattr(settings, 'H3_RESOLUTION_SEMI_URBAN', 6),
        'rural': getattr(settings, 'H3_RESOLUTION_RURAL', 5),
        'forest': getattr(settings, 'H3_RESOLUTION_FOREST', 5),
        'mountain': getattr(settings, 'H3_RESOLUTION_MOUNTAIN', 4),
        'coastal': getattr(settings, 'H3_RESOLUTION_COASTAL', 6),
        'default': getattr(settings, 'H3_RESOLUTION_DEFAULT', 7),
        
        # Urban center definitions (used for auto-resolution)
        'urban_centers': [
            {'lat': -1.2921, 'lon': 36.8219, 'name': 'Nairobi'},
            {'lat': 39.9042, 'lon': 116.4074, 'name': 'Beijing'},
            {'lat': 31.2304, 'lon': 121.4737, 'name': 'Shanghai'},
            {'lat': 19.0760, 'lon': 72.8777, 'name': 'Mumbai'},
            {'lat': 40.7128, 'lon': -74.0060, 'name': 'New York'},
            {'lat': 51.5074, 'lon': -0.1278, 'name': 'London'},
            {'lat': 48.8566, 'lon': 2.3522, 'name': 'Paris'},
            {'lat': -33.8688, 'lon': 151.2093, 'name': 'Sydney'},
            {'lat': 35.6762, 'lon': 139.6503, 'name': 'Tokyo'},
        ]
    }


def get_threshold_config():
    """Get risk thresholds for different severity levels."""
    return {
        'critical': getattr(settings, 'RISK_THRESHOLD_CRITICAL', 0.85),
        'high': getattr(settings, 'RISK_THRESHOLD_HIGH', 0.70),
        'moderate': getattr(settings, 'RISK_THRESHOLD_MODERATE', 0.40),
        'low': getattr(settings, 'RISK_THRESHOLD_LOW', 0.0),
    }