from .base import BaseDataSource


class OpenMeteoSource(BaseDataSource):
    name = 'open_meteo'
    required_env_vars = []

    def fetch(self, lat, lon):
        import requests

        response = requests.get(
            'https://flood-api.open-meteo.com/v1/flood',
            params={
                'latitude': lat,
                'longitude': lon,
                'daily': 'river_discharge',
                'hourly': 'precipitation,rain,river_discharge',
                'past_days': 1,
                'forecast_days': 7,
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        discharge = (data.get('daily') or {}).get('river_discharge') or [0]
        padded = list(discharge) + [0, 0, 0]
        
        hourly = data.get('hourly', {})
        precip_1h = (hourly.get('precipitation') or [0])
        rain_1h = (hourly.get('rain') or [0])
        hourly_discharge = (hourly.get('river_discharge') or [0])
        
        # Get next 24 hours of precipitation for forecast analysis
        precip_24h = precip_1h[:24] if precip_1h else []
        rain_24h = rain_1h[:24] if rain_1h else []
        
        return {
            'river_discharge_today': padded[0] or 0,
            'river_discharge_24h': padded[1] or 0,
            'river_discharge_48h': padded[2] or 0,
            'river_discharge_7d_max': max(value or 0 for value in padded),
            'precipitation_forecast_24h': precip_24h,
            'rain_forecast_24h': rain_24h,
            'hourly_river_discharge': hourly_discharge[:24] if hourly_discharge else [],
        }

