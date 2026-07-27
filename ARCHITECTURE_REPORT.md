# FloodGuard Architecture & Data Flow Report

## Architecture Overview

### Apps
- **core** - Main application (models, views, tasks, data sources, analytics)
- **floodguard** - Project configuration (settings, routing, celery)

### Modules

**core/models.py**
- `AlertZone` - Geographic flood zones with risk_threshold/risk_score
- `FloodReading` - Water level readings with metadata
- `IncidentReport` - Community flood reports with clustering
- `AlertLog` - SMS/email alert delivery tracking
- `UserProfile` - User roles (citizen/authority/admin) + phone verification
- `FloodPrediction` - 7-day forecasts
- `AlertZoneActivity` - GPS check-ins for dynamic zones
- `Milestone` - Project achievements for impact dashboard
- `BeneficiaryGroup` - Trained community groups
- `MonthlyReport` - Monthly operational reports

**core/views.py**
- `AlertZoneViewSet` - CRUD + manual_override + dispatch_alert actions
- `FloodReadingViewSet` - predict + heatmap actions
- `IncidentReportViewSet` - verify action
- `safe_route_view` - GraphHopper + internal prototype
- `ai_flood_analysis` - Groq-powered decision support
- `impact_stats` - Real DB statistics
- `service_worker_view` - PWA caching

**core/tasks.py**
- `fetch_flood_api` - Multi-source data fetch
- `fetch_all_zones` - Global data collection
- `run_risk_scoring` - Risk calculation
- `dispatch_alerts` - SMS/email dispatch with deduplication
- `dispatch_manual_alert` - Admin-triggered alerts
- `generate_7day_forecasts` - Prediction generation
- `expire_manual_overrides` - Cleanup task
- `sync_dynamic_zones` - Zone maintenance
- `update_h3_risk_scores` - H3 cache updates

**core/data_sources/**
- `open_meteo.py` - River discharge API
- `openweather.py` - Weather current conditions
- `tomorrow_io.py` - Precipitation forecast
- `weather_api.py` - WeatherAPI.com
- `nasa_gpm.py` - NASA precipitation
- `gee.py` - Google Earth Engine (requires credentials)

**core/analytics/scoring.py**
- `calculate_risk_score` - Multi-source weighted scoring (45% discharge, 30% precip, 25% env)

**core/h3_risk.py**
- `get_h3_cell_for_point` - Point to H3 conversion
- `get_h3_cells_for_bbox` - Bbox H3 generation
- `get_risk_for_route` - Route risk scoring
- `update_h3_risk_scores` - Cache updates

**core/consumers.py**
- `AlertConsumer` - WebSocket alerts (`/ws/alerts/`)
- `FloodMapConsumer` - Map updates (`/ws/flood-map/`)

---

## Data Flow

```
Weather APIs (OpenWeather, Tomorrow.io, WeatherAPI, NASA GPM, Open-Meteo)
        ↓
core/data_sources/aggregator.py (build_risk_feature_vector)
Parallel multi-source fetch with ThreadPoolExecutor (15s timeout)
        ↓
core/analytics/scoring.py (calculate_risk_score)
Multi-source weighted formula:
  - 45% river discharge (current, 24h, 7d avg)
  - 30% precipitation (rainfall, intensity, probability)
  - 25% environmental (humidity 60%, satellite water 40%)
Confidence multiplier: <2 sources = 80%, <3 sources = 90%
        ↓
core/h3_risk.py (get_h3_cell_for_point)
Point → H3 cell → zone intersection → avg risk
        ↓
core/tasks.py → dispatch_alerts
Creates FloodReading, updates AlertZone.risk_score
WebSocket broadcast via FloodMapConsumer
        ↓
core/alerts/messages.py (build_alert_message)
Severity-based message templates (CRITICAL/HIGH/MODERATE/SAFE)
        ↓
core/tasks.py → dispatch_alerts
SMS via Africa's Talking (primary) / Email (fallback)
        ↓
core/views.py (ai_flood_analysis)
Groq LLM with structured prompt
Returns: overall_risk, summary, immediate_actions, 24h_outlook, safe_zones
        ↓
core/views.py (safe_route_view)
GraphHopper API (if key valid) OR internal prototype
Risk scoring along routes via H3 cells
        ↓
Dashboard/API endpoints
/api/v1/stats/, /api/v1/impact/, /api/v1/zones/
```

---

## Database Schema

### Tables
| Table | Purpose | Key Fields |
|-------|---------|------------|
| core_alertzone | Flood zones | polygon (PostGIS), risk_score, risk_threshold |
| core_floodreading | Sensor readings | location (Point), risk_score, metadata (JSON) |
| core_incidentreport | Community reports | location, severity, status, cluster_id |
| core_alertlog | Alert history | delivery_status, provider_message_id |
| core_userprofile | User profiles | role, phone_number, sms_enabled |
| core_floodprediction | Forecasts | zone, target_date, risk_score, confidence |

### Indexes
- `AlertZone`: risk_score, manual_override_active, -updated_at (3 indexes)
- `FloodReading`: timestamp, -timestamp, risk_score, location (4 indexes)
- `IncidentReport`: -created_at, status, severity, cluster_id, location (6 indexes)

### Spatial Indexes
PostGIS automatically creates GIST indexes for geometry fields.

---

## GIS Review

### Current Implementation
- **PostGIS**: Used for AlertZone polygons, spatial queries
- **H3**: v4 API (h3.latlng_to_cell, h3.cells_to_geo, h3.geo_to_h3shape)
- **GeoJSON**: Zone boundaries, H3 cells for map rendering
- **Leaflet**: Frontend map integration

### Missing Features
- Resolution auto-selection based on density
- Neighboring cell lookups (h3.grid_ring, h3.grid_disk)
- Flood propagation modeling

---

## API Endpoints

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | /api/v1/zones/ | Optional | Zone list with bbox filter |
| POST | /api/v1/zones/{id}/manual_override/ | Authority | Toggle override |
| POST | /api/v1/zones/{id}/dispatch_alert/ | Authority | Send alerts |
| GET | /api/v1/readings/ | Optional | Readings list |
| GET | /api/v1/readings/predict/ | Optional | Zone prediction |
| GET/POST | /api/v1/safe-route/ | Public | Route planning |
| GET | /api/v1/stats/ | Public | Basic stats |
| GET | /api/v1/impact/ | Public | Impact stats |
| GET | /api/v1/milestones/ | Public | Project achievements |
| POST | /api/v1/ai-analysis/ | Authenticated | AI analysis |
| GET | /api/v1/data-sources/ | Authority | Source status |
| GET | /api/v1/h3-cells/ | Public | H3 risk cells |
| POST | /api/v1/reports/ | Public | Submit report |

---

## Scheduled Tasks (CELERY_BEAT_SCHEDULE)

| Task | Schedule | Purpose |
|------|----------|---------|
| fetch-flood-api | 15 min | Multi-source data collection |
| run-risk-scoring | 15 min | Risk calculation |
| generate-7day-forecasts | 6 hours | Prediction generation |
| cluster-incident-reports | 3 hours | Geographic clustering |
| expire-overrides | 5 min | Override cleanup |
| sync-dynamic-zones | 1 hour | Zone maintenance |
| update-h3-risk | 15 min | H3 cache update |

---

## Security Configuration

- CSRF: CsrfViewMiddleware enabled
- Rate limiting: 500/hr anon, 5000/hr user, 10/hr AI
- Authentication: Session + Token
- Permissions: IsAuthenticated, IsAuthority

---

## Production Readiness Checklist

- [x] .env.example updated with all required variables
- [x] Security settings configurable
- [ ] Redis connection (local Redis not running)
- [ ] GraphHopper API key validation (returns 400)
- [ ] Google Earth Engine (requires service account JSON)
- [x] All tests passing (84/84)