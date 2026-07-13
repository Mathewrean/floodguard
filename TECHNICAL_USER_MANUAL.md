# FloodGuard Technical User Manual

## Version 1.0 | July 2026

---

## 1. Application Launch Guide

### Prerequisites

- Python 3.11+
- PostgreSQL database (configured in `.env`)
- Redis server (for Celery)
- Node.js for frontend assets (optional if using CDN)

### Launch Procedure

```bash
# 1. Activate virtual environment
source floodguard-env/bin/activate  # Linux/macOS
# OR
floodguard-env\Scripts\activate      # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Initialize database
python manage.py migrate

# 4. Create global zones (recommended for worldwide coverage)
python manage.py populate_global_zones --skip-confirmation

# 5. For Nairobi-specific data with Open-Meteo integration
python manage.py init_db --skip-confirmation

# 6. Run development server
python manage.py runserver

# 7. (Optional) Start Celery worker for background tasks
celery -A floodguard worker -l info
```

Access URL: `http://127.0.0.1:8000`

---

## 2. System Navigation

### Public Navigation (Unauthenticated Users)

- **Home** (`/`) — Landing page with hero stats, AI summary, and map preview
- **GIS Dashboard** (`/gis/`) — Interactive flood risk map with H3 cells
- **Safe Route** (`/safe-route/`) — Route planning avoiding flood zones
- **About** (`/about/`) — System information

### Authenticated User Navigation

- **Dashboard** (`/dashboard/`) — Redirects to role-appropriate dashboard
- **Submit Report** (`/reports/submit/`) — Citizen flood report submission

### Role-Based Dashboards

#### Citizen Dashboard (`/dashboard/citizen/`)

- My reports table with status tracking
- Global flood search
- AI-powered flood intelligence
- Reports map showing user's submitted reports

#### Authority Dashboard (`/dashboard/authority/`)

- Pending reports requiring review (real-time via WebSocket)
- Flood zones overview with risk visualization
- Zone risk table with live updates

#### Admin Dashboard (`/dashboard/admin/`)

- System health indicators (DB, Redis, Celery)
- Data source status configuration
- Global zone management table
- User management tab
- Audit log (superuser only)

### Key UI Controls

- **Mobile Menu** — Hamburger icon on top-right for small screens
- **Dark Mode** — Moon/sun icon next to mobile menu
- **Location Button** — "My Location" or GPS button to center map on user
- **Search** — Location search with geocoding support
- **Zone Clicks** — Clicking zones on map shows risk details in side panel

---

## 3. Authentication

### Default Test Users

| Role      | Username    | Password       | Access                                |
| --------- | ----------- | -------------- | ------------------------------------- |
| Admin     | `admin`     | `admin123`     | Full admin panel, all zones           |
| Authority | `responder` | `responder123` | Report review, zone management        |
| Citizen   | `citizen`   | `citizen123`   | Report submission, personal dashboard |

### Role Access Matrix

| Feature         | Public | Citizen | Authority | Admin |
| --------------- | ------ | ------- | --------- | ----- |
| View Map        | ✓      | ✓       | ✓         | ✓     |
| Safe Route      | ✓      | ✓       | ✓         | ✓     |
| Submit Report   | ✓      | ✓       | ✓         | ✓     |
| My Reports      | —      | ✓       | ✓         | ✓     |
| Verify Reports  | —      | —       | ✓         | ✓     |
| Zone Management | —      | —       | ✓         | ✓     |
| Data Sources    | —      | —       | ✓         | ✓     |
| Admin Panel     | —      | —       | —         | ✓     |

---

## 4. Location-Specific Data Integration (Nairobi)

### Data Sources

The system integrates real-time flood intelligence from:

- **Open-Meteo** — River discharge data
- **Weather APIs** — Rainfall, humidity, wind speed
- **NASA GPM** — Satellite precipitation
- **Google Earth Engine** — Terrain and water extent analysis

### Nairobi Internal Site Workflow

When a user is within Nairobi's configured
bounds (bounded by `DEFAULT_GEO_BOUNDS` in settings):

```text
User Location Request
        ↓
1. Browser Geolocation API
   - Returns lat/lon coordinates
   - Accuracy radius provided
        ↓
2. Backend Processing
   - POST /api/v1/dynamic-zone/ with coordinates
   - Feature vector built from all available sources
   - Risk score calculated via ML model
        ↓
3. Zone Matching/Fallback
   - Check existing zones for point inclusion
   - If no zone exists → live assessment only
   - If zone exists → overlay zone data on map
        ↓
4. Real-time Response
   - Zone risk level (CRITICAL/HIGH/MODERATE/LOW)
   - Last update timestamp
   - Recommended actions
        ↓
5. Map Visualization
   - User marker (pulsing blue dot)
   - Accuracy circle (if < 2000m)
   - Risk popup at location
   - Emergency banner if risk ≥ 70%
```

### NAIROBI_LOCATIONS Configuration

The system seeds 8 key Nairobi locations:

1. Westlands
2. South B
3. Kibera
4. Mathare
5. Karen
6. Eastleigh
7. Ruiru
8. Athi River

Each location generates:

- 0.03° × 0.03° polygon zone (~3.5km × 3.5km)
- Initial FloodReading with discharge data
- Risk score based on multi-source features

---

## 5. Zonal Logic and Future Implementation

### Conceptual Framework

Zones in FloodGuard represent geographic areas
with unified flood risk characteristics. Each zone contains:

```text
AlertZone {
    name: string,
    polygon: GeoJSON,              // Multi-polygon boundary
    centroid: Point,               // Map center
    risk_score: float (0.0-1.0),   // Current risk assessment
    risk_threshold: float (0.0-1.0), // Alert trigger threshold
    sources: array,                // Active data sources
    updated: datetime              // Last assessment
}
```

### Risk Classification Bands

| Band     | Score Range | Color              | Action Required |
| -------- | ----------- | ------------------ | --------------- |
| SAFE     | 0.00-0.39   | Green (#16a34a)    | None            |
| MODERATE | 0.40-0.69   | Amber (#ca8a04)    | Monitor         |
| HIGH     | 0.70-0.84   | Red (#ea580c)      | Prepare         |
| CRITICAL | 0.85-1.00   | Dark Red (#dc2626) | Evacuate        |

### Current Status

**Zonal features are ACTIVE and visible.** Zones are created via:

- `populate_global_zones` — Static global city zones
- `init_db` — Nairobi zones with live data
- Admin interface — Manual zone creation
- API — Dynamic zone assessment for user location

### Future Enhancements

- H3 hierarchical indexing for granular risk cells
- Real-time zone interpolation between data points
- Predictive modeling for 24h/48h zone forecasts
- Cross-zone flood propagation simulation
- Automated zone splitting/merging based on risk heterogeneity

---

## API Endpoints Reference

| Endpoint                       | Method   | Auth            | Description                    |
| ------------------------------ | -------- | --------------- | ------------------------------ |
| `/api/v1/zones/`               | GET      | Public          | List all flood zones           |
| `/api/v1/zones/{id}/`          | GET      | Public          | Zone detail                    |
| `/api/v1/readings/`            | GET      | Public          | Flood readings                 |
| `/api/v1/stats/`               | GET      | Public          | System statistics              |
| `/api/v1/geocode/`             | GET      | Public          | Location search                |
| `/api/v1/dynamic-zone/`        | GET/POST | Public          | Risk assessment by coordinates |
| `/api/v1/safe-route/`          | GET/POST | Public          | Route calculation              |
| `/api/v1/reports/`             | GET/POST | Authenticated   | Incident reports               |
| `/api/v1/reports/{id}/verify/` | PATCH    | Authority/Admin | Update report status           |
| `/api/v1/data-sources/`        | GET      | Authority/Admin | Source status                  |
| `/api/v1/ai-analysis/`         | POST     | Authenticated   | Flood intelligence             |

---

## Troubleshooting

### Database Issues

```bash
# Reset database
python manage.py migrate core zero
python manage.py migrate
python manage.py populate_global_zones --skip-confirmation
```

### Redis Connection

Redis is required for:

- WebSocket connections
- Alert broadcasting
- Celery task queue
- Cache fallback on rate limits

Start Redis: `redis-server`

### Map Not Loading

- Check Leaflet CSS/JS includes in template
- Verify `/api/v1/zones/` returns data
- Check browser console for CORS errors

### Tests Failing

```bash
python -m pytest tests/ --ignore=postgres_data -q
```
