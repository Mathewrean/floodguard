from .base import BaseDataSource


class NASAGPMSource(BaseDataSource):
    name = 'nasa_gpm'
    required_env_vars = ['NASA_EARTHDATA_TOKEN']

    def fetch(self, lat, lon):
        import os
        from datetime import date, timedelta

        import requests

        yesterday = (date.today() - timedelta(days=1)).strftime('%Y%m%d')
        response = requests.get(
            'https://gpm.nasa.gov/api/v1/imerg',
            params={
                'start': yesterday,
                'end': yesterday,
                'lat': lat,
                'lon': lon,
                'format': 'json',
            },
            headers={'Authorization': f'Bearer {os.environ["NASA_EARTHDATA_TOKEN"]}'},
            timeout=15,
        )
        if response.status_code != 200:
            return {'nasa_precip_mmhr': 0, 'nasa_quality': 0}
        data = response.json()
        return {
            'nasa_precip_mmhr': data.get('precipitation', 0),
            'nasa_quality': data.get('qualityIndex', 0),
        }

