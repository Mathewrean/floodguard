"""
Nairobi 500-Zone Generator for FloodGuard Validation.
Generates geographically diverse test coordinates across Nairobi County.
"""
import random
import math
from typing import List, Dict, Any


def get_zone_categories() -> List[Dict[str, Any]]:
    return [
        {
            'name': 'urban_commercial',
            'subcategories': [
                {'name': 'CBD', 'center_lat': -1.2921, 'center_lon': 36.8219, 'radius': 0.015, 'count': 50},
                {'name': 'Westlands', 'center_lat': -1.2676, 'center_lon': 36.8108, 'radius': 0.012, 'count': 35},
                {'name': 'Upper_Hill', 'center_lat': -1.3000, 'center_lon': 36.8100, 'radius': 0.010, 'count': 20},
                {'name': 'Industrial_Area', 'center_lat': -1.3100, 'center_lon': 36.8500, 'radius': 0.015, 'count': 20},
            ]
        },
        {
            'name': 'residential_high_density',
            'subcategories': [
                {'name': 'Kibera', 'center_lat': -1.3133, 'center_lon': 36.7892, 'radius': 0.010, 'count': 45},
                {'name': 'Mathare', 'center_lat': -1.2547, 'center_lon': 36.8765, 'radius': 0.010, 'count': 35},
                {'name': 'Kayole', 'center_lat': -1.2833, 'center_lon': 36.9167, 'radius': 0.012, 'count': 25},
                {'name': 'Eastleigh', 'center_lat': -1.2833, 'center_lon': 36.8333, 'radius': 0.010, 'count': 25},
                {'name': 'Roysambu', 'center_lat': -1.2167, 'center_lon': 36.9000, 'radius': 0.012, 'count': 25},
            ]
        },
        {
            'name': 'peri_urban_rural',
            'subcategories': [
                {'name': 'Karen', 'center_lat': -1.3167, 'center_lon': 36.7000, 'radius': 0.020, 'count': 30},
                {'name': 'Limuru_border', 'center_lat': -1.1000, 'center_lon': 36.6500, 'radius': 0.025, 'count': 20},
                {'name': 'Athi_River', 'center_lat': -1.4500, 'center_lon': 37.0000, 'radius': 0.020, 'count': 20},
            ]
        },
        {
            'name': 'critical_infrastructure',
            'subcategories': [
                {'name': 'Kenyatta_National_Hospital', 'center_lat': -1.3019, 'center_lon': 36.8075, 'radius': 0.005, 'count': 15},
                {'name': 'Central_Police_Station', 'center_lat': -1.2833, 'center_lon': 36.8167, 'radius': 0.005, 'count': 10},
                {'name': 'Nyayo_Bridge', 'center_lat': -1.3000, 'center_lon': 36.8300, 'radius': 0.005, 'count': 10},
                {'name': 'Railway_Bridge', 'center_lat': -1.2900, 'center_lon': 36.8300, 'radius': 0.005, 'count': 10},
                {'name': 'Nairobi_Power_Station', 'center_lat': -1.2800, 'center_lon': 36.8200, 'radius': 0.005, 'count': 10},
                {'name': 'Schools_Cluster_Eastlands', 'center_lat': -1.2900, 'center_lon': 36.8600, 'radius': 0.010, 'count': 15},
            ]
        },
        {
            'name': 'hydrological_features',
            'subcategories': [
                {'name': 'Nairobi_River_CBD', 'center_lat': -1.2921, 'center_lon': 36.8219, 'radius': 0.008, 'count': 20},
                {'name': 'Ngong_River', 'center_lat': -1.3500, 'center_lon': 36.7500, 'radius': 0.015, 'count': 15},
                {'name': 'Mbagathi_River', 'center_lat': -1.3500, 'center_lon': 36.8000, 'radius': 0.012, 'count': 15},
                {'name': 'Wetlands_Dandora', 'center_lat': -1.2500, 'center_lon': 36.8800, 'radius': 0.010, 'count': 10},
                {'name': 'Low_Lying_Basin_Kibera', 'center_lat': -1.3133, 'center_lon': 36.7892, 'radius': 0.010, 'count': 15},
                {'name': 'River_Plains_Athi', 'center_lat': -1.4000, 'center_lon': 37.0000, 'radius': 0.020, 'count': 5},
            ]
        }
    ]


def _gaussian_random(center, spread, bound_min, bound_max):
    value = center + random.gauss(0, spread)
    return max(bound_min, min(bound_max, value))


def generate_nairobi_500_zones(seed=42) -> List[Dict[str, Any]]:
    random.seed(seed)
    zones = []
    zone_id = 1
    nairobi_lat_min, nairobi_lat_max = -1.450, -1.100
    nairobi_lon_min, nairobi_lon_max = 36.650, 37.150

    categories = get_zone_categories()

    for category in categories:
        for subcat in category['subcategories']:
            for i in range(subcat['count']):
                lat = _gaussian_random(
                    subcat['center_lat'],
                    subcat['radius'] / 2.5,
                    nairobi_lat_min,
                    nairobi_lat_max
                )
                lon = _gaussian_random(
                    subcat['center_lon'],
                    subcat['radius'] / 2.5,
                    nairobi_lon_min,
                    nairobi_lon_max
                )
                zones.append({
                    'id': zone_id,
                    'name': f"Nairobi-{subcat['name'].replace('_', '-')}-{i+1:03d}",
                    'lat': round(lat, 6),
                    'lon': round(lon, 6),
                    'category': category['name'],
                    'subcategory': subcat['name'],
                })
                zone_id += 1

    random.shuffle(zones)
    for idx, zone in enumerate(zones, 1):
        zone['id'] = idx

    return zones


def get_sample_zones(zones, sample_size=50):
    if len(zones) <= sample_size:
        return zones
    step = len(zones) // sample_size
    return zones[::step][:sample_size]
