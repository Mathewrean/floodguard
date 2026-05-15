from .base import BaseDataSource


class WeatherAPISource(BaseDataSource):
    name = 'weather_api'
    required_env_vars = ['WEATHERAPI_KEY']

    def fetch(self, lat, lon):
        import os
        import requests

        response = requests.get(
            'https://api.weatherapi.com/v1/forecast.json',
            params={
                'key': os.environ['WEATHERAPI_KEY'],
                'q': f'{lat},{lon}',
                'days': 3,
                'aqi': 'no',
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        today = data.get('forecast', {}).get('forecastday', [{}])[0].get('day', {})
        return {
            'total_precip_mm': today.get('totalprecip_mm', 0),
            'max_wind_kph': today.get('maxwind_kph', 0),
            'avg_humidity_pct': today.get('avghumidity', 0),
            'chance_of_rain': today.get('daily_chance_of_rain', 0),
            'condition_text': today.get('condition', {}).get('text', ''),
            'uv_index': today.get('uv', 0),
        }

