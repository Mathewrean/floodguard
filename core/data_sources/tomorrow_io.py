from .base import BaseDataSource


class TomorrowIOSource(BaseDataSource):
    name = 'tomorrow_io'
    required_env_vars = ['TOMORROW_IO_API_KEY']

    def fetch(self, lat, lon):
        import os
        import requests

        response = requests.get(
            'https://api.tomorrow.io/v4/weather/forecast',
            params={
                'location': f'{lat},{lon}',
                'apikey': os.environ['TOMORROW_IO_API_KEY'],
                'units': 'metric',
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        hourly = data.get('timelines', {}).get('hourly', [{}])[0].get('values', {})
        return {
            'precip_intensity_mmhr': hourly.get('precipitationIntensity', 0),
            'precip_probability': hourly.get('precipitationProbability', 0),
            'precip_type': hourly.get('precipitationType', 0),
            'humidity_pct': hourly.get('humidity', 0),
            'wind_speed_ms': hourly.get('windSpeed', 0),
            'visibility_km': hourly.get('visibility', 10),
        }

