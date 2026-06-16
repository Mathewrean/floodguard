from .base import BaseDataSource


class OpenWeatherSource(BaseDataSource):
    name = 'openweather'
    required_env_vars = ['OPENWEATHER_API_KEY']

    def fetch(self, lat, lon):
        import requests

        api_key = self.config_value('OPENWEATHER_API_KEY')
        if not api_key:
            return {}

        response = requests.get(
            'https://api.openweathermap.org/data/2.5/weather',
            params={
                'lat': lat,
                'lon': lon,
                'appid': api_key,
                'units': 'metric',
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        return {
            'rainfall_1h_mm': data.get('rain', {}).get('1h', 0),
            'rainfall_3h_mm': data.get('rain', {}).get('3h', 0),
            'humidity_pct': data.get('main', {}).get('humidity', 0),
            'pressure_hpa': data.get('main', {}).get('pressure', 1013),
            'wind_speed_ms': data.get('wind', {}).get('speed', 0),
            'cloud_cover_pct': data.get('clouds', {}).get('all', 0),
            'weather_condition': (data.get('weather') or [{}])[0].get('main', ''),
        }
