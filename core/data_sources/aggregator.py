from concurrent.futures import ThreadPoolExecutor, wait

from .gee import GEESource
from .nasa_gpm import NASAGPMSource
from .open_meteo import OpenMeteoSource
from .openweather import OpenWeatherSource
from .tomorrow_io import TomorrowIOSource
from .weather_api import WeatherAPISource

ALL_SOURCES = [
    OpenMeteoSource(),
    OpenWeatherSource(),
    TomorrowIOSource(),
    WeatherAPISource(),
    NASAGPMSource(),
    GEESource(),
]


def get_source_status() -> list[dict]:
    statuses = []
    for source in ALL_SOURCES:
        configured = source.is_configured()
        statuses.append({
            'name': source.name,
            'configured': configured,
            'status': 'ok' if configured else 'no_key',
        })
    return statuses


def fetch_all_sources(lat: float, lon: float) -> dict:
    results = {}
    with ThreadPoolExecutor(max_workers=len(ALL_SOURCES)) as executor:
        futures = {
            executor.submit(source.safe_fetch, lat, lon): source.name
            for source in ALL_SOURCES
        }
        done, not_done = wait(futures, timeout=15)
        for future in done:
            source_name = futures[future]
            try:
                data = future.result()
            except Exception as exc:
                data = {'source': source_name, 'available': False, 'error': str(exc)}
            results[data.get('source', source_name)] = data
        for future in not_done:
            future.cancel()
            source_name = futures[future]
            results[source_name] = {'source': source_name, 'available': False, 'error': 'timeout'}
    return results


def build_risk_feature_vector(lat: float, lon: float, zone_name: str = '') -> dict:
    all_data = fetch_all_sources(lat, lon)
    open_meteo = all_data.get('open_meteo', {})
    openweather = all_data.get('openweather', {})
    tomorrow_io = all_data.get('tomorrow_io', {})
    weather_api = all_data.get('weather_api', {})
    nasa_gpm = all_data.get('nasa_gpm', {})
    gee = all_data.get('google_earth_engine', {})
    available_count = sum(1 for value in all_data.values() if value.get('available'))

    return {
        'river_discharge': open_meteo.get('river_discharge_today', 0),
        'discharge_24h': open_meteo.get('river_discharge_24h', 0),
        'discharge_7d_max': open_meteo.get('river_discharge_7d_max', 0),
        'rainfall_1h_mm': openweather.get('rainfall_1h_mm', 0),
        'precip_intensity': tomorrow_io.get('precip_intensity_mmhr', 0),
        'precip_probability': tomorrow_io.get('precip_probability', 0),
        'total_precip_mm': weather_api.get('total_precip_mm', 0),
        'nasa_precip': nasa_gpm.get('nasa_precip_mmhr', 0),
        'chance_of_rain': weather_api.get('chance_of_rain', 0),
        'humidity': openweather.get('humidity_pct', tomorrow_io.get('humidity_pct', 50)),
        'pressure': openweather.get('pressure_hpa', 1013),
        'wind_speed': openweather.get('wind_speed_ms', 0),
        'water_extent_km2': gee.get('water_extent_km2', 0),
        'sources_available': available_count,
        'data_confidence': 'high' if available_count >= 3 else 'medium' if available_count >= 2 else 'low',
        'zone_name': zone_name,
        'sources': all_data,
    }
