# FloodGuard

> AI-Powered Flood Prediction and Early Warning System

![ Django](https://img.shields.io/badge/Django-4.2.30-green?logo=django)
![ DRF](https://img.shields.io/badge/DRF-3.14.0-blue)
![ PostGIS](https://img.shields.io/badge/PostGIS-3.4-cyan?logo=postgresql)
![ Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![ License](https://img.shields.io/badge/license-MIT-green)

**Last updated:** 2026-07-13

A comprehensive flood monitoring and alert system leveraging geospatial analytics, machine learning, and real-time data processing to provide early warnings for potential flooding events.

---



## Features

- **Real-time Flood Monitoring** - Live sensor data ingestion and alerting
- **GIS-Enabled Mapping** - Interactive Leaflet maps with GeoDjango backend
- **Machine Learning Prediction** - scikit-learn based risk scoring engine
- **Multi-Channel Alerts** - SMS (Africa's Talking), email, and in-app notifications
- **Role-Based Access** - Citizen, Emergency Team, and Admin dashboards
- **WebSocket Streaming** - Real-time updates via Django Channels
- **Celery Task Queue** - Async processing of flood data and alerts
- **Comprehensive API** - RESTful endpoints for all resources
- **Mobile Responsive** - Works seamlessly on all devices
- **Offline Capable** - Progressive enhancement for low-connectivity areas


## Tech Stack

| Category | Technologies |
|----------|--------------|
| Web Framework | `Django==4.2.30` `djangorestframework>=3.15.0` `channels==4.1.0` `daphne==4.1.0` |
| Database & GIS | `psycopg2-binary==2.9.12` |
| Async & Tasks | `redis==7.4.0` `celery==5.4.0` `django-celery-beat==2.5.0` |
| ML & Data | `joblib==1.5.3` `numpy==2.4.4` `scipy==1.17.1` `scikit-learn==1.5.0` |
| Testing | `pytest-django==4.8.0` `factory-boy==3.3.1` `Faker==33.1.0` |
| Utilities | `pillow==12.2.0` `python-decouple==3.8` `requests==2.33.1` |



## Architecture

FloodGuard follows a modern, scalable architecture:

        - **GeoDjango + PostGIS** - Spatial database with geometric queries
            - **Django Channels** - WebSocket support for real-time communication
            - **Celery + Redis** - Distributed task queue for background processing
            - **scikit-learn ML Model** - Flood risk prediction engine
            - **Alert Consumer** - Real-time notification system

**Models:** AlertZone, FloodReading, IncidentReport, AlertLog, UserProfile, FloodPrediction, AlertZoneActivity

**API:** RESTful endpoints powered by Django REST Framework with token authentication.

**Frontend:** HTML5, CSS3, vanilla JavaScript with Leaflet.js for mapping.

---



## Installation

### Prerequisites

- Python 3.11.x
- PostgreSQL 18+ with PostGIS extension
- Redis 7+ (for caching and Celery broker)
- Git

### Quick Start (Development)

```bash
# Clone the repository
git clone https://github.com/your-org/floodguard.git
cd floodguard

# One-command setup and startup
scripts/init_project.sh
```

The initializer creates `.env` from `.env.example` when needed, provisions `floodguard-env`, installs dependencies, starts PostgreSQL/Redis or Docker Compose services, runs migrations, collects static files, and starts Django/Celery.

Useful variants:

```bash
# Validate local prerequisites without starting services
scripts/init_project.sh --check-only

# Force Docker Compose mode
scripts/init_project.sh --mode docker

# Force local virtualenv/system-service mode
scripts/init_project.sh --mode local --detach
```

### Manual Setup

```bash
# Create virtual environment
python3.11 -m venv floodguard-env
source floodguard-env/bin/activate  # On Windows: floodguard-env\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your database and API credentials

# Set up database (PostgreSQL with PostGIS)
# Ensure PostgreSQL is running and PostGIS extension is enabled
sudo -u postgres psql -c "CREATE DATABASE floodguard;"
sudo -u postgres psql -d floodguard -c "CREATE EXTENSION postgis;"

# Apply migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic

# Create superuser (optional, for admin access)
python manage.py createsuperuser

# Run development server
python manage.py runserver

# In separate terminals, start Celery worker and beat
celery -A floodguard worker -l info
celery -A floodguard beat -l info
```

Visit http://localhost:8000

### Docker Setup (Recommended)

```bash
# Use Docker Compose for full stack (PostgreSQL, Redis, Django, Celery)
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

---



## Usage

### User Roles

1. **Citizen** - View flood alerts, submit incident reports, access public dashboard
2. **Emergency Team** - Monitor zones, acknowledge incidents, manage alerts
3. **Admin** - Full system access, user management, zone configuration

### Key Operations

#### View Interactive Map
Navigate to `/map` to see live flood zones and risk levels.

#### Submit Incident Report
Citizens can report flooding via the report form with GPS coordinates.

#### Monitor Dashboard
Each role has a dedicated dashboard with relevant metrics and controls.

#### Real-time Alerts
WebSocket connections push alerts instantly to connected clients.

---



## API Reference

FloodGuard provides a comprehensive REST API at `/api/`

### Endpoints

| Endpoint | Method | Description | Access |
|----------|--------|-------------|--------|
| `/api/zones/` | GET | List all flood zones | Public |
| `/api/zones/{id}/` | GET | Zone details | Public |
| `/api/zones/{id}/override/` | POST | Manual override (Authority/Admin) | Restricted |
| `/api/readings/` | GET | Latest flood readings | Public |
| `/api/reports/` | GET/POST | Incident reports (POST unauthenticated) | Public/Citizen |
| `/api/alerts/` | GET | Alert history | Authenticated |
| `/api/stats/` | GET | Dashboard statistics | Authenticated |
| `/api/v1/dynamic-zone/` | GET | Read-only live assessment for submitted coordinates | Public |
| `/api/v1/dynamic-zone/` | POST | Create or refresh a dynamic zone from browser GPS coordinates | Public, rate limited |

### WebSocket Endpoints

- `ws://localhost:8000/ws/alerts/` - Real-time alert stream
- `ws://localhost:8000/ws/flood-map/` - Live map updates

### Authentication

API uses Token Authentication for protected endpoints.

```bash
# Obtain token
curl -X POST http://localhost:8000/api-token-auth/ \
  -H "Content-Type: application/json" \
  -d '{"username": "user", "password": "pass"}'

# Use token
curl -H "Authorization: Token YOUR_TOKEN" http://localhost:8000/api/zones/
```

---

## Dynamic GPS Zones

FloodGuard defaults map views to Nairobi. When a user grants browser geolocation permission, the frontend captures `latitude`, `longitude`, and optional `accuracy` with `navigator.geolocation.getCurrentPosition()`, then sends the values to `POST /api/v1/dynamic-zone/` as JSON.

The backend validates the coordinate range and configured `GEO_BOUNDS`, checks whether an existing `AlertZone` covers the point, and only creates or refreshes a dynamic zone when no mapped zone already applies. `GET /api/v1/dynamic-zone/?lat=...&lon=...` remains read-only for live assessment and does not mutate stored zones.

Example request:

```bash
curl -X POST http://localhost:8000/api/v1/dynamic-zone/ \
  -H "Content-Type: application/json" \
  -d '{"lat": -1.287, "lon": 36.821, "accuracy": 45}'
```

Privacy and security notes:
- Browser permission denial falls back to Nairobi and does not send GPS data.
- Dynamic zone creation is rate limited and bounded by `GEO_BOUNDS`.
- Exact GPS coordinates are sent only to the same-origin API; CSP already allows `connect-src 'self'`.
- `Permissions-Policy: geolocation=(self)` allows location access only for the FloodGuard origin.
- Use HTTPS in production, because browser geolocation is restricted to secure contexts.

---



## Testing

FloodGuard has comprehensive test coverage with 1537 test files.

### Running Tests

```bash
# Run all tests with coverage report
pytest --cov=core --cov-report=html

# Run unit tests only
pytest tests/unit/

# Run integration tests
pytest tests/integration/

# Run end-to-end tests
pytest tests/e2e/

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/unit/test_models.py
```

### Test Coverage

- **Unit Tests** - Model validation, serializers, permissions, utilities
- **Integration Tests** - API endpoints, Celery tasks, database operations
- **E2E Tests** - Full user workflows across all roles

Current test files:
  - `tests/e2e/test_dashboard.py`
  - `tests/integration/test_api.py`
  - `tests/integration/test_celery.py`
  - `tests/unit/test_audit_fixes.py`
  - `tests/unit/test_data_sources.py`
  - `tests/unit/test_emergency_acknowledgment.py`
  - `tests/unit/test_geographic_clustering.py`
  - `tests/unit/test_manual_override.py`
  - `tests/unit/test_models.py`
  - `tests/unit/test_permissions.py`
  - `tests/unit/test_registration.py`
  - `tests/unit/test_serializers.py`
  - `tests/unit/test_sms_delivery_tracking.py`
  - `tests/unit/test_zone_boundary_validation.py`

---



## Deployment

### Production Deployment with Docker

FloodGuard is containerized for easy deployment.

```bash
# Build and start all services
docker-compose -f docker-compose.yml up -d

# Scale workers as needed
docker-compose scale celery=3

# View service status
docker-compose ps

# Monitor logs
docker-compose logs -f django
docker-compose logs -f celery
```

**Services:**
- PostgreSQL + PostGIS (port 5432)
- Redis (port 6379)
- Django/Gunicorn (port 8000)
- Celery Worker
- Celery Beat (scheduler)

### Environment Variables

Configure these in production:

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Django secret key | (required) |
| `DEBUG` | Debug mode | False |
| `DB_NAME` | PostgreSQL database name | floodguard |
| `DB_USER` | Database user | postgres |
| `DB_PASSWORD` | Database password | (required) |
| `DB_HOST` | Database host | db |
| `REDIS_URL` | Redis connection | redis://redis:6379/0 |
| `AFRICASTALKING_USERNAME` | SMS API username | (required for SMS) |
| `AFRICASTALKING_API_KEY` | SMS API key | (required for SMS) |
| `GEO_BOUNDS` | Allowed dynamic-zone bounds as min_lon,min_lat,max_lon,max_lat | 33.0,-5.0,42.0,5.0 |

---



## Development

### Project Structure

```
floodguard/
├── core/                   # Main Django application
│   ├── models.py          # Database models (GIS-enabled)
│   ├── views.py           # View functions and ViewSets
│   ├── serializers.py     # DRF serializers
│   ├── urls.py            # URL routing
│   ├── tasks.py           # Celery async tasks
│   ├── signals.py         # Django signals
│   ├── consumers.py       # WebSocket consumers
│   ├── alerts/            # Alert messaging module
│   ├── analytics/         # ML risk scoring engine
│   └── management/commands/  # Custom Django commands
├── floodguard/            # Django project config
│   ├── settings.py        # All configuration
│   ├── urls.py            # Root URL config
│   ├── asgi.py            # ASGI entry point
│   ├── wsgi.py            # WSGI entry point
│   ├── routing.py         # WebSocket routing
│   └── cel

ery.py       # Celery app setup
├── templates/            # HTML templates
│   ├── base.html
│   ├── landing/
│   ├── auth/
│   ├── dashboard/
│   ├── reports/
│   └── alerts/
├── static/               # Static assets
│   ├── css/style.css
│   ├── js/ (main.js, dashboard.js, map.js, etc.)
│   └── img/
├── tests/                # Test suite
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── ml_model/             # Trained ML model (flood_model.pkl)
├── scripts/              # Utility scripts
├── requirements.txt      # Python dependencies
├── docker-compose.yml    # Docker services
├── manage.py             # Django CLI
└── README.md            # This file

### Code Style

- Follow PEP 8 guidelines
- Use type hints where practical
- Write docstrings for all functions/classes
- Keep models, views, serializers in their respective files

### Adding a New Model

1. Define model in `core/models.py`
2. Create serializer in `core/serializers.py` (if API exposure needed)
3. Add ViewSet or views in `core/views.py`
4. Register URLs in `core/urls.py`
5. Create and apply migration: `python manage.py makemigrations && python manage.py migrate`
6. Add unit tests in `tests/unit/test_models.py`

### Adding a New API Endpoint

1. Add serializer (if needed)
2. Extend appropriate ViewSet in `core/views.py`
3. Update router registration in `core/urls.py`
4. Document in API section of this README
5. Write integration tests in `tests/integration/test_api.py`

---



## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Reporting Issues

Report bugs and request features via GitHub Issues.

---



## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---


