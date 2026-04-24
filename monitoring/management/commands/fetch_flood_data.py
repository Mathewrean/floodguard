from django.core.management.base import BaseCommand
from monitoring.services import fetch_open_meteo

class Command(BaseCommand):
    help = "Fetch real-time flood/river data"

    def handle(self, *args, **kwargs):
        # Example coordinates (replace with Kenyan rivers)
        fetch_open_meteo(lat=-0.0917, lon=34.7679)
        self.stdout.write(self.style.SUCCESS("Flood data ingested"))
