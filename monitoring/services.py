import requests
from datetime import datetime
from .models import RiverReading

OPEN_METEO_FLOOD_URL = "https://flood-api.open-meteo.com/v1/flood"

def fetch_open_meteo(lat, lon):
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "river_discharge",
        "timezone": "Africa/Nairobi"
    }
    r = requests.get(OPEN_METEO_FLOOD_URL, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()

    for date, discharge in zip(
        data["daily"]["time"],
        data["daily"]["river_discharge"]
    ):
        RiverReading.objects.create(
            source="Open-Meteo",
            location="Configured Point",
            latitude=lat,
            longitude=lon,
            discharge=discharge,
            recorded_at=datetime.fromisoformat(date)
        )
