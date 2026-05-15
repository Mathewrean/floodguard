from .base import BaseDataSource


class OSMSource(BaseDataSource):
    name = 'openstreetmap'
    required_env_vars = []

    def fetch(self, lat, lon):
        return {
            'drainage_density': 0,
            'road_density': 0,
            'osm_available': False,
        }

