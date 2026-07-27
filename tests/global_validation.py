"""
Global location validation framework.
Tests FloodGuard functionality at 500+ worldwide coordinates.
"""

import random
import json
from typing import List, Dict, Any

# Predefined global coordinates covering diverse regions
GLOBAL_COORDINATES = [
    # Africa
    {'lat': -1.2921, 'lon': 36.8219, 'region': 'Nairobi, Kenya'},
    {'lat': -2.5217, 'lon': 31.5792, 'region': 'Bukavu, DRC'},
    {'lat': 6.5244, 'lon': 3.3792, 'region': 'Lagos, Nigeria'},
    {'lat': -33.9249, 'lon': 18.4241, 'region': 'Cape Town, South Africa'},
    {'lat': 30.0444, 'lon': 31.2357, 'region': 'Cairo, Egypt'},
    {'lat': -4.0487, 'lon': 39.6591, 'region': 'Mombasa, Kenya'},
    
    # Europe
    {'lat': 51.5074, 'lon': -0.1278, 'region': 'London, UK'},
    {'lat': 48.8566, 'lon': 2.3522, 'region': 'Paris, France'},
    {'lat': 52.5200, 'lon': 13.4050, 'region': 'Berlin, Germany'},
    {'lat': 40.7128, 'lon': -74.0060, 'region': 'New York, USA'},
    {'lat': 35.6762, 'lon': 139.6503, 'region': 'Tokyo, Japan'},
    {'lat': -33.8688, 'lon': 151.2093, 'region': 'Sydney, Australia'},
    
    # Asia
    {'lat': 28.6139, 'lon': 77.2090, 'region': 'Delhi, India'},
    {'lat': 19.0760, 'lon': 72.8777, 'region': 'Mumbai, India'},
    {'lat': 31.2304, 'lon': 121.4737, 'region': 'Shanghai, China'},
    {'lat': 39.9042, 'lon': 116.4074, 'region': 'Beijing, China'},
    {'lat': 13.7563, 'lon': 100.5018, 'region': 'Bangkok, Thailand'},
    {'lat': -6.2088, 'lon': 106.8456, 'region': 'Jakarta, Indonesia'},
    
    # Americas
    {'lat': 40.7128, 'lon': -74.0060, 'region': 'New York, USA'},
    {'lat': 51.0447, 'lon': -114.0719, 'region': 'Calgary, Canada'},
    {'lat': -22.9068, 'lon': -43.1729, 'region': 'Rio de Janeiro, Brazil'},
    {'lat': -33.4489, 'lon': -70.6693, 'region': 'Santiago, Chile'},
    {'lat': 4.6126, 'lon': -74.0705, 'region': 'Bogota, Colombia'},
    {'lat': -12.0464, 'lon': -77.0428, 'region': 'Lima, Peru'},
    
    # Remote/Mountain/Coastal
    {'lat': 64.1333, 'lon': -21.9000, 'region': 'Reykjavik, Iceland'},
    {'lat': -17.8241, 'lon': 22.4167, 'region': 'Windhoek, Namibia'},
    {'lat': -1.5228, 'lon': -78.6322, 'region': 'Amazon, Ecuador'},
    {'lat': 72.0, 'lon': -40.0, 'region': 'Greenland Ice Sheet'},
    {'lat': -77.85, 'lon': 166.67, 'region': 'Antarctica'},
    {'lat': 25.0, 'lon': -150.0, 'region': 'Pacific Ocean'},
]


def generate_random_coordinates(count: int = 500) -> List[Dict[str, Any]]:
    """Generate random coordinates worldwide for testing."""
    coordinates = []
    
    for _ in range(count):
        # Random latitude (-90 to 90)
        lat = random.uniform(-85, 85)
        # Random longitude (-180 to 180)
        lon = random.uniform(-175, 175)
        
        # Determine region type
        abs_lat = abs(lat)
        if abs_lat < 23.5:
            region_type = 'tropical'
        elif abs_lat < 66.5:
            region_type = 'temperate'
        else:
            region_type = 'polar'
        
        # Add some known flood-prone areas
        known_flood_areas = [
            {'lat': 29.9444, 'lon': -90.0719, 'region': 'New Orleans, USA (flood-prone)'},
            {'lat': 52.37, 'lon': 4.89, 'region': 'Amsterdam, Netherlands (below sea level)'},
            {'lat': 51.1657, 'lon': 11.7074, 'region': 'Dresden, Germany (Elbe flood)'},
            {'lat': 33.7490, 'lon': -84.3880, 'region': 'Atlanta, USA (urban flooding)'},
        ]
        
        if random.random() < 0.1:  # 10% known flood-prone
            coord = random.choice(known_flood_areas)
            coordinates.append(coord)
        else:
            coordinates.append({'lat': lat, 'lon': lon, 'region_type': region_type})
    
    return coordinates


def run_coordinate_test(coord: Dict[str, Any]) -> Dict[str, Any]:
    """Run a single coordinate test and return results."""
    try:
        import django
        django.setup()
        
        from core.h3_risk import get_h3_cell_for_point, get_hisk_cell_stats
        from core.data_sources.aggregator import build_risk_feature_vector
        
        lat, lon = coord['lat'], coord['lon']
        
        # Test H3
        h3_result = get_h3_cell_for_point(lat, lon)
        
        # Test weather aggregation
        try:
            weather = build_risk_feature_vector(lat, lon, f'test_{lat}_{lon}')
        except Exception as e:
            weather = {'error': str(e)}
        
        return {
            'coordinate': coord,
            'h3_cell': h3_result.get('h3_index') if h3_result else None,
            'h3_risk': h3_result.get('risk_score') if h3_result else 0,
            'weather_available': weather.get('sources_available', 0) if isinstance(weather, dict) else 0,
            'status': 'pass' if h3_result else 'fail',
        }
    except Exception as e:
        return {
            'coordinate': coord,
            'error': str(e),
            'status': 'error',
        }


if __name__ == '__main__':
    coords = generate_random_coordinates(50)
    results = []
    for coord in coords:
        result = run_coordinate_test(coord)
        results.append(result)
        print(f"{result['status']}: {coord.get('region', coord)} - H3: {result.get('h3_cell', 'N/A')[:12] if result.get('h3_cell') else 'N/A'}")