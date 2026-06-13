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
                'past_days': 1,
                'forecast_days': 7,
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        discharge = (data.get('daily') or {}).get('river_discharge') or [0]
        padded = list(discharge) + [0, 0, 0]
        return {
            'river_discharge_today': padded[0] or 0,
            'river_discharge_24h': padded[1] or 0,
            'river_discharge_48h': padded[2] or 0,
            'river_discharge_7d_max': max(value or 0 for value in padded),
        }

