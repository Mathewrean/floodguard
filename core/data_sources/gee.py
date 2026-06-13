from .base import BaseDataSource


class GEESource(BaseDataSource):
    name = 'google_earth_engine'
    required_env_vars = ['GEE_SERVICE_ACCOUNT_KEY_PATH']

    def fetch(self, lat, lon):
        try:
            import os

            import ee
        except ImportError:
            return {}

        key_file = os.environ.get('GEE_SERVICE_ACCOUNT_KEY_PATH')
        if not key_file:
            return {}

        credentials = ee.ServiceAccountCredentials(
            email=None,
            key_file=key_file,
        )
        ee.Initialize(credentials)
        point = ee.Geometry.Point([lon, lat])
        buffer = point.buffer(5000)
        sentinel = (
            ee.ImageCollection('COPERNICUS/S1_GRD')
            .filterBounds(buffer)
            .filterDate('2024-01-01', 'now')
            .filter(ee.Filter.eq('instrumentMode', 'IW'))
            .select('VV')
            .median()
        )
        water_pixels = sentinel.lt(-15)
        area = water_pixels.multiply(ee.Image.pixelArea())
        try:
            stats = area.reduceRegion(ee.Reducer.sum(), buffer, 30)
            water_m2 = stats.getInfo().get('VV', 0)
        except Exception:
            return {}
        return {
            'water_extent_km2': round(water_m2 / 1_000_000, 4),
            'data_age_days': 1,
        }

