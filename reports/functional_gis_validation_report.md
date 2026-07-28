# FloodGuard Functional & GIS Validation Report

## Executive Summary
- **H3 Operations:** 7/7 PASS
- **Weather Fallback:** 3/3 PASS
- **Risk Engine:** 4/4 PASS
- **Safe Routes:** 5/5 PASS
- **Overall Pass Rate:** 100%

## H3 Validation

### Cell Generation
| Resolution | Test Result | Notes |
|------------|-------------|-------|
| 4 | PASS | Continental-scale cells |
| 7 | PASS | Urban-scale cells (~1km²) |
| 10 | PASS | High-resolution cells |

### Hierarchy Operations
- **Parent-Child:** PASS - `cell_to_parent` returns correct parent cells
- **Neighbors (grid_disk):** PASS - k=1 returns 7 cells including center
- **Ring (grid_ring):** PASS - k=2 returns valid ring cells
- **Polygon Conversion:** PASS - `cells_to_geo` returns valid GeoJSON

### H3 Risk Overlay
- **Cell Risk Lookup:** PASS - Returns risk score and level
- **BBox Query:** PASS - Returns cells within Nairobi bounds
- **Route Risk:** PASS - Calculates average/max risk for route geometry

## Weather Intelligence Validation

### Aggregator Structure
```json
{
  "river_discharge": 10.0,
  "discharge_24h": 12.0,
  "discharge_7d_max": 15.0,
  "rainfall_1h_mm": 2.0,
  "precip_intensity": 1.0,
  "precip_probability": 30,
  "total_precip_mm": 5.0,
  "nasa_precip": 1.5,
  "chance_of_rain": 40,
  "humidity": 65,
  "pressure": 1013,
  "wind_speed": 3.0,
  "water_extent_km2": 0.2,
  "sources_available": 3,
  "data_confidence": "medium"
}
```

### Fallback Behavior
- **With API Keys:** PASS - Returns data from configured sources
- **Without API Keys:** PASS - Returns empty sources with `sources_available: 0`
- **Confidence Scoring:** PASS - Returns high/medium/low based on source count

### Sources Tested
1. Open-Meteo (river discharge) - Mocked in tests
2. OpenWeather (rainfall, humidity) - Mocked in tests
3. Tomorrow IO (precip intensity, probability) - Mocked in tests
4. WeatherAPI (total precip, chance of rain) - Mocked in tests
5. NASA GPM (precipitation) - Mocked in tests
6. Google Earth Engine (water extent) - Mocked in tests

## Risk Engine Validation

### Weighted Scoring
- **Discharge Component:** PASS - 0-100+ m³/s mapped to 0.05-0.98 risk
- **Precipitation Component:** PASS - Multiple sources, max() aggregation
- **Environmental Component:** PASS - Humidity and SAR water extent
- **Confidence Penalty:** PASS - Single source: ×0.80, Two sources: ×0.90

### Score Determinism
- Same inputs produce identical scores across calls: PASS

## Safe Route Engine Validation

### Route Generation
| Profile | Distance (m) | Duration (min) | Safety Score | Status |
|---------|--------------|----------------|--------------|--------|
| fastest | 821.4 | 11.0 | 98.0 | PASS |
| balanced | 821.4 | 11.0 | 98.0 | PASS |
| safest | 821.4 | 11.0 | 98.0 | PASS |

### Fallback Behavior
- **GraphHopper Unavailable:** PASS - Internal engine activates
- **Coordinate Snapping:** PASS - Snaps to navigable network
- **Risk Avoidance:** PASS - Routes avoid high-risk zones when configured

### Constraints Validated
- Distance calculation: PASS (Haversine formula)
- ETA calculation: PASS (distance / 75m per minute)
- Flood exposure: PASS (risk_exposure metric)

## Issues Found
1. **Heatmap Endpoint Bug:** `FloodReadingViewSet.heatmap` calls `self.get_queryset()` which applies a slice (`[:200]`), then attempts to `.filter()` on the sliced queryset, causing `TypeError: Cannot filter a query once a slice has been taken.`
2. **GraphHopper Integration:** GET endpoint returns 501 when API key is missing. POST fallback works correctly.
3. **Weather API Rate Limits:** Tomorrow.io returns 429 in production-like scenarios.

## Recommendations
1. Fix heatmap endpoint by reordering queryset operations
2. Add automatic failover from GraphHopper GET to internal POST engine
3. Implement request queuing and caching for weather APIs
