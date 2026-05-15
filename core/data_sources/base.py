from abc import ABC, abstractmethod


class BaseDataSource(ABC):
    name: str
    required_env_vars: list[str] = []

    def is_configured(self) -> bool:
        import os

        return all(os.environ.get(var) for var in self.required_env_vars)

    @abstractmethod
    def fetch(self, lat: float, lon: float) -> dict:
        """Fetch data for coordinates. Return an empty dict on failure."""

    def safe_fetch(self, lat: float, lon: float) -> dict:
        if not self.is_configured():
            return {'source': self.name, 'available': False}
        try:
            data = self.fetch(lat, lon) or {}
            data['source'] = self.name
            data['available'] = True
            return data
        except Exception as exc:
            import logging

            logging.getLogger('core').warning("%s fetch failed: %s", self.name, exc)
            return {
                'source': self.name,
                'available': False,
                'error': str(exc),
            }

