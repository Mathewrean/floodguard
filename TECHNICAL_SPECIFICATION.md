# FloodGuard — Technical Specification Document

**Version:** 1.0  
**Date:** 2026-08-20  
**Source:** Complete source-code extraction (Django 4.2.30 / DRF / GeoDjango / PostGIS 3.4 / Celery 5.4 / Redis / Channels 4.1 / H3 v4 / scikit-learn / Groq LLM)  
**Prepared for:** Patent/utility-model specification basis  
**Project Path:** `C:\Users\SoftClansUser\Desktop\floodstu\floodguard`  
**Repository:** `https://github.com/Mathewrean/floodguard.git`

---

## 1. System Overview & Scope

FloodGuard is an AI-powered, near-real-time flood prediction and early-warning platform. It ingests heterogeneous meteorological and hydrological data from multiple external APIs, computes location-specific flood risk scores using a weighted analytics engine, dynamically partitions terrain into H3-hexagon-based risk zones, generates flood-propagation paths, dispatches multi-channel alerts to affected populations and emergency responders, and exposes a REST/WebSocket API for web, mobile, and administrative dashboards.

**Domain:** Disaster risk reduction / climate-tech SaaS.  
**Primary stakeholders:** Citizens (end-users), EmergencyTeam (first responders), GovernmentTeam (policy/ops), MeteorologicalTeam (data analysts), NGOs (relief coordinators), Researchers (data consumers), Admins (platform operators).

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Client Layer                                │
│   ┌──────────────┐   ┌─────────────────┐   ┌──────────────────┐ │
│   │  Web (HTML)  │   │  Mobile App    │   │  Admin Dashboard  │ │
│   └──────┬───────┘   └────────┬────────┘   └────────┬───────────┘ │
└──────────┼──────────────────┼──────────────────────┼─────────────┘
           │ HTTP/REST          │ WebSocket             │ Admin API
┌──────────▼──────────────────▼──────────────────────▼─────────────┐
│                    API Gateway / Load Balancer                  │
│                          (Nginx)                                  │
└──────────┬──────────────────┬──────────────────────┬─────────────┘
           │ HTTPS              │ WebSocket (wss)     │ TLS
┌──────────▼──────────────────▼──────────────────────▼─────────────┐
│                     Application Layer                             │
│  ┌────────────┐ ┌────────────┐ ┌──────────┐ ┌────────┐ ┌────────┐  │
│  │  Django     │ │ DRF API    │ │ Channels │ │ Celery │ │ Celery │  │
│  │  Core       │ │ (Views)    │ │ (WS)     │ │ Worker │ │ Beat   │  │
│  └────┬───────┘ └────┬───────┘ └────┬─────┘ └────┬───┘ └────┬───┘  │
└───────┼──────────────┼──────────────┼────────────┼────────────┘   │
        │ Internal APIs│              │            │                │
┌───────▼──────────────▼──────────────▼────────────▼────────────────▼
│                     Data & Infrastructure Layer                     │
│  ┌──────────────┐ ┌──────────────┐ ┌────────┐ ┌────────┐ ┌────────┐ │
│  │ PostgreSQL + │ │  Redis       │ │ H3     │ │ File   │ │ Object │ │
│  │ PostGIS        │ │ (Caching +  │ │ Index  │ │ Storage│ │ Store  │ │
│  │                │ │  Queue)     │ │        │ │        │ │ (S3)   │ │
│  └──────────────┘ └──────────────┘ └────────┘ └────────┘ └────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                          │                              │
┌─────────────────────────▼──────┐   ┌────────────────────▼──────────┐
│  External Data Sources         │   │  External Services            │
│  (Async Parallel Fetch)        │   │                                │
│  Open-Meteo, OpenWeather,      │   │  Groq (LLM),                   │
│  Tomorrow.io, NASA GPM,        │   │  Twilio (SMS),                 │
│  Google Earth Engine,          │   │  SMTP (Email),                 │
│  WeatherAPI                     │   │  Push Notification Gateway     │
└────────────────────────────────┘   └───────────────────────────────┘
```

**Architecture style:** Distributed, event-driven, microservices-tinged monolith (single Django project with modular apps).  
**Deployment:** Docker Compose (production) with multi-stage Dockerfile; Nginx reverse proxy with TLS termination; separate containers for web, worker, beat, and PostgreSQL.

---

## 3. Technology Stack

| Layer | Technology | Version |
|---|---|---|
| Web Framework | Django | 4.2.30 |
| API Framework | Django REST Framework | (bundled) |
| Database | PostgreSQL + PostGIS | 3.4 |
| GIS Library | GeoDjango | (Django built-in) |
| Geospatial Index | H3 | v4 |
| Async Task Queue | Celery | 5.4 |
| Message Broker | Redis | (cached) |
| Real-time | Django Channels | 4.1 |
| ML / Data Processing | scikit-learn, NumPy, Pandas, Requests | (bundled) |
| LLM Provider | Groq | llama-3.1-8b-instant |
| Containerization | Docker, Docker Compose | — |
| Reverse Proxy | Nginx | — |
| WSGI Server | Gunicorn | — |
| SMS Gateway | Twilio | (API) |
| Object Storage | AWS S3 / S3-compatible | — |

---

## 4. Core Functional Domains

The application is organized into modular Django apps under the root `floodguard/` package:

- **`core`** — Main domain logic: models, views, serializers, URLs, permissions, signals, consumers, middleware, cache keys.
- **`core/data_sources/`** — Multi-source weather/hydrology data ingestion engine (7 adapters + aggregator).
- **`core/analytics/`** — Risk-scoring engine, configuration, AI prompt templates.
- **`core/zoning/`** — Dynamic zoning, H3 intelligence, location engine, propagation, search, lifecycle.
- **`core/alerts/`** — Alert message generation and multi-channel delivery (email, SMS, push).
- **`floodguard/`** — Project configuration: settings, Celery app, ASGI routing, URLs.

---

## 5. Data Model Schema (ORM)

### 5.1 Key Entities (from `core/models.py`)

| Model | Purpose | Key Fields |
|---|---|---|
| `AlertZone` | Static or dynamic flood-risk zone | `name`, `geometry (Polygon)`, `risk_level`, `population`, `is_dynamic` |
| `FloodReading` | Raw reading from a data source | `zone`, `timestamp`, `water_level`, `rainfall_mm`, `source`, `confidence` |
| `IncidentReport` | User-reported flood incident | `location`, `description`, `severity`, `confirmed`, `reported_by` |
| `AlertLog` | Record of sent alerts | `zone`, `alert_type`, `message`, `status`, `recipients`, `sent_at` |
| `FloodPrediction` | ML-generated prediction | `zone`, `predicted_level`, `probability`, `model_version`, `timestamp` |
| `DynamicZone` | H3-backed dynamic zone | `h3_index`, `risk_score`, `geometry`, `valid_from`, `valid_to` |
| `H3Cell` | Single H3 hexagon record | `h3_index`, `resolution`, `parent`, `children`, `center_lat`, `center_lng` |
| `H3CellRelationship` | Adjacency/neighbor relationships | `from_cell`, `to_cell`, `relationship_type` |
| `FloodPropagation` | Simulated flow path | `source_cell`, `target_cell`, `time_to_reach`, `probability` |
| `AdministrativeBoundary` | Country/region/boundary | `name`, `type`, `geometry`, `population` |
| `ZoneLifecycleLog` | Zone state history | `zone`, `action`, `timestamp`, `actor`, `metadata` |
| `UserProfile` | Extended user profile | `user`, `role`, `phone`, `language`, `preferred_channel` |

### 5.2 Relationships

```
AlertZone 1—* FloodReading
AlertZone 1—* FloodPrediction
AlertZone 1—* AlertLog
AlertZone 1—* IncidentReport
AlertZone 1—* ZoneLifecycleLog
DynamicZone 1—1 H3Cell (h3_index)
H3Cell 1—* H3CellRelationship
H3Cell 1—* FloodPropagation
AdministrativeBoundary 1—* AlertZone
User 1—1 UserProfile
```

### 5.3 Database Schema (Migrations)

18 migrations in `core/migrations/` defining the full PostgreSQL schema with PostGIS geometry types, spatial indexes, and foreign-key constraints.

---

## 6. Core Analytics Engine

### 6.1 Weighted Risk Scoring (`core/analytics/scoring.py`)

The scoring engine (`compute_zone_risk`) computes a composite flood risk score (0–100) per zone using these weighted factors:

| Factor | Weight | Source |
|---|---|---|
| Rainfall accumulation (72-h weighted) | 30% | Data sources |
| Water-level trend slope | 25% | Sensor readings |
| Elevation & slope (DEM) | 15% | Static GIS data |
| Drainage capacity | 10% | Infrastructure DB |
| Proximity to water bodies | 8% | OSM + satellite |
| H3 neighbor amplification | 7% | Propagation engine |
| Historical incident density | 5% | IncidentReports |

Score → categorical bucket: `LOW (0–30)`, `MODERATE (31–50)`, `HIGH (51–70)`, `CRITICAL (71–100)`.

### 6.2 Configuration (`core/analytics/config.py`)

Central parameter configuration for thresholds, time windows, weights, and model constants. All tunable hyperparameters live here to enable operational adjustment without code changes.

### 6.3 AI Prompt Templates (`core/analytics/prompts.py`)

Prompt templates fed to the Groq LLM (`llama-3.1-8b-instant`) for:
- Narrative alert message generation (localized, multi-language).
- Incident report triage and severity classification.
- Summarization of multi-source data discrepancies.
- Validation of AI-generated content against schema constraints.

---

## 7. Data Ingestion Pipeline

### 7.1 Multi-Source Aggregator (`core/data_sources/aggregator.py`)

The `DataAggregator` class orchestrates parallel, asynchronous fetching from all registered data sources using `asyncio.gather`:

- **Sources:** Open-Meteo, OpenWeather, Tomorrow.io, NASA GPM, Google Earth Engine, WeatherAPI.
- **Strategy:** Each source adapter implements a unified `fetch(zone_geometry, time_range)` interface. The aggregator normalizes all responses into `FloodReading` objects.
- **Fallback:** If a primary source fails, fallback sources are tried in priority order.
- **Validation:** Each reading is validated against schema and sanity bounds before persistence.

### 7.2 Individual Adapters (`core/data_sources/`)

| Adapter | API | Key Output |
|---|---|---|
| `open_meteo.py` | Open-Meteo REST | Forecast rainfall, river levels |
| `openweather.py` | OpenWeather API | Current conditions, 5-day forecast |
| `tomorrow_io.py` | Tomorrow.io API | High-resolution precipitation, pollen |
| `nasa_gpm.py` | NASA GPM API | Satellite rainfall estimates |
| `gee.py` | Google Earth Engine | Satellite-derived flood extent |
| `weather_api.py` | WeatherAPI.com | Historical conditions |

### 7.3 Ingestion Tasks (Celery)

Defined in `core/tasks.py`:
- `fetch_and_store_readings()` — runs every 5 minutes (Beat schedule).
- `update_elevation_data()` — runs daily.
- `sync_historical_data()` — runs hourly.
- Each task dispatches to the aggregator, processes results, and persists to DB with confidence scoring.

---

## 8. Geospatial Processing & Dynamic Zoning

### 8.1 H3 Spatial Indexing (`core/zoning/h3_intelligence.py`)

The system uses **H3 v4** (hexagonal hierarchical spatial index) for geospatial partitioning:

- Terrain is tessellated into H3 cells at resolutions 6–9 depending on zone granularity.
- Each `DynamicZone` maps to one `H3Cell` record.
- Neighbor relationships are pre-computed and stored in `H3CellRelationship`.
- Parent/child hierarchies enable progressive refinement and aggregation.

### 8.2 Dynamic Zoning Engine (`core/zoning/dynamic_zoning.py`)

The `DynamicZoningEngine` recomputes zone boundaries and risk scores based on incoming data:

- Re-runs scoring per H3 cell every ingestion cycle.
- Merges adjacent low-risk cells into larger zones; splits high-risk cells into smaller sub-zones.
- Updates `DynamicZone.risk_score` and emits `ZoneLifecycleLog` entries for state changes.

### 8.3 Location Engine (`core/zoning/location_engine.py`)

Reverse-geocodes user coordinates to the appropriate H3 cell and `AlertZone` for personalized risk queries.

### 5.4 Flood Propagation Model (`core/zoning/propagation.py`)

Simulates downstream flood spread using a graph-based propagation algorithm over the H3 cell adjacency graph:

- `FloodPropagation` records store `source_cell → target_cell` with `time_to_reach` and `probability`.
- Algorithm: weighted BFS using elevation delta, flow direction, and downstream connectivity.
- Propagation is triggered when a cell's risk score crosses the CRITICAL threshold.

### 8.5 Search Engine (`core/zoning/search_engine.py`)

Full-text + spatial search over zones, incidents, and predictions. Supports filters by date range, risk level, region, and incident type.

### 8.6 Zone Lifecycle (`core/zoning/lifecycle.py`)

Manages state transitions of dynamic zones: `ACTIVE → FADING → ARCHIVED`. Emits lifecycle log records.

---

## 9. Alerting System

### 9.1 Alert Trigger Logic (`core/views.py`, `core/alerts/messages.py`)

Alerts are generated when:
- A zone's risk score crosses from `MODERATE`/`HIGH` → `CRITICAL`.
- A `FloodPrediction` probability exceeds 80% and projected level exceeds the evacuation threshold.
- An `IncidentReport` is confirmed by a moderator.

### 9.2 Message Generation (`core/alerts/messages.py`)

Constructs human-readable alert messages with:
- Zone name and risk level.
- Estimated arrival time.
- Recommended actions (evacuate, shelter, avoid).
- Localized to user's preferred language.

### 9.3 Multi-Channel Delivery (`core/alerts/email.py`, Twilio integration)

- **Email:** Django `send_mail` with HTML templates + SMTP backend.
- **SMS:** Twilio API integration for high-priority alerts.
- **Push Notifications:** WebSocket broadcast to connected clients via Channels.
- **In-app:** Real-time via WebSocket (`core/consumers.py`).

### 9.4 Alert Log

All alerts are persisted to `AlertLog` with status tracking (`QUEUED`, `SENT`, `DELIVERED`, `FAILED`).

---

## 10. API Layer

### 10.1 REST API (DRF — `core/views.py`)

Key endpoints grouped by resource:

| Resource | Endpoint | Method | Description |
|---|---|---|---|
| Zones | `/api/zones/` | GET | List all alert zones (with geometry) |
| Zones | `/api/zones/<id>/` | GET | Zone detail + current risk |
| Zones | `/api/zones/<id>/readings/` | GET | Historical readings for a zone |
| Predictions | `/api/predictions/` | GET | Active flood predictions |
| Incidents | `/api/incidents/` | POST | Report a flood incident |
| Incidents | `/api/incidents/` | GET | List incidents (admin/filtered) |
| Search | `/api/search/` | GET | Text + spatial search |
| User | `/api/user/profile/` | GET/PUT | Self-profile management |
| Auth | `/api/auth/token/` | POST | JWT token obtain |
| Auth | `/api/auth/token/refresh/` | POST | Token refresh |

### 10.2 WebSocket API (`core/consumers.py`, `floodguard/routing.py`)

- **`/ws/alerts/`** — Real-time alert broadcasts to subscribed zones.
- **`/ws/predictions/`** — Live prediction updates.
- **`/ws/incidents/`** — Live incident feeds.
- Consumers use DRF authentication (JWT in query params).

### 10.3 URL Routing (`core/urls.py`, `floodguard/urls.py`)

REST routes in `core/urls.py` (versioned under `/api/v1/`). WebSocket routes in `floodguard/routing.py` (ASGI).

---

## 11. Authentication & Authorization

### 11.1 Authentication

- **JWT tokens** via `rest_framework_simplejwt` (customized in views).
- Token obtained at `/api/auth/token/`, refreshed at `/api/auth/token/refresh/`.
- WebSocket authentication via query-param token.

### 11.2 Authorization (RBAC)

Defined in `core/permissions.py`. Custom permission classes:

| Class | Access |
|---|---|
| `IsCitizen` | Public zone read, incident reporting |
| `IsEmergencyTeam` | All zones + predictions + incident moderation |
| `IsGovernmentTeam` | All zones + historical data + export |
| `IsMeteorologicalTeam` | Data source management + prediction overrides |
| `IsResearcher` | Read-only historical data + analytics exports |
| `IsAdmin` | Full CRUD on all resources |

### 11.3 User Profile

`UserProfile` (one-to-one with Django `User`) stores: `role`, `phone_number`, `language`, `preferred_alert_channel`, `organization`.

---

## 12. Background Processing (Celery)

### 12.1 Celery App (`floodguard/celery.py`)

Standard Celery app with Django settings integration. Worker hostname, concurrency, and queues configured via environment variables.

### 12.2 Beat Schedule (`floodguard/settings.py`, `core/tasks.py`)

```python
CELERY_BEAT_SCHEDULE = {
    "fetch-and-store-readings": {
        "task": "core.tasks.fetch_and_store_readings",
        "schedule": crontab(minute="*/5"),
    },
    "update-elevation-data": {
        "task": "core.tasks.update_elevation_data",
        "schedule": crontab(hour=2, minute=0),
    },
    "sync-historical-data": {
        "task": "core.tasks.sync_historical_data",
        "schedule": crontab(minute="0"),
    },
    "evaluate-propagation-paths": {
        "task": "core.tasks.evaluate_propagation_paths",
        "schedule": crontab(minute="*/15"),
    },
    "send-digest-emails": {
        "task": "core.tasks.send_digest_emails",
        "schedule": crontab(hour=8, minute=0),
    },
}
```

### 12.3 Async Tasks (from `core/tasks.py`)

| Task | Description | Schedule |
|---|---|---|
| `fetch_and_store_readings` | Fetch + store readings from all sources | Every 5 min |
| `update_elevation_data` | Refresh DEM data | Daily @ 2AM |
| `sync_historical_data` | Backfill historical data | Hourly |
| `evaluate_propagation_paths` | Recompute flood spread | Every 15 min |
| `send_digest_emails` | Daily summary to subscribers | Daily @ 8AM |
| `send_alert_notification` | Send a single alert | On-demand (chain) |
| `generate_ai_summary` | LLM summary of multi-source data | On-demand (chain) |
| `cleanup_expired_zones` | Archive old dynamic zones | Daily @ 3AM |
| `update_h3_neighbors` | Recompute H3 adjacency graph | Daily @ 4AM |
| `reindex_search` | Rebuild search index | Daily @ 5AM |

### 12.4 Worker Hooks

Custom worker startup hooks in `floodguard/celery.py` warm caches and validate connections on boot.

---

## 13. Caching Strategy

### 13.1 Cache Backend

Redis with SHA-256 deterministic key generation in `core/cache_keys.py`.

### 13.2 Cached Entities

| Cache Key Function | TTL | Purpose |
|---|---|---|
| `zone_risk_cache_key(zone_id)` | 3600s | Cached risk score |
| `zone_readings_cache_key(zone_id, hours)` | 7200s | Recent readings |
| `prediction_cache_key(zone_id)` | 1800s | Active predictions |
| `propagation_cache_key(cell_id)` | 5400s | Propagation path |
| `search_cache_key(query_hash)` | 3600s | Search results |
| `user_profile_cache_key(user_id)` | 86400s | Profile data |

### 13.3 Cache Invalidation

- **Signals:** `core/signals.py` invalidates caches on model save/delete (e.g., when `FloodReading` is saved, the corresponding zone cache is cleared).
- **Warmup:** `app_ready` signal warms critical caches at startup.
- **Selective invalidation:** Zone-level granularity — only the affected zone's cache is invalidated.

---

## 14. Middleware & Request Lifecycle

### 14.1 Custom Middleware

- **`SecurityHeadersMiddleware`** — Adds CSP, X-Frame-Options, X-Content-Type-Options, Strict-Transport-Security headers.
- **`RequestLoggingMiddleware`** — Structured logging of all requests (method, path, duration, status, user).
- **`MaintenanceModeMiddleware`** — Returns 503 when `MAINTENANCE_MODE` env var is true.
- **`TenantMiddleware`** (planned) — Multi-tenant routing (not yet active).

### 14.2 Context Processors

`core/context_processors.py` injects global site-wide context (e.g., site name, current alert count) into Django templates.

---

## 15. Signals

### 15.1 `core/signals.py`

| Signal | Trigger | Action |
|---|---|---|
| `post_save UserProfile` | User login / profile creation | Auto-create profile if missing |
| `post_save FloodReading` | New reading saved | Invalidate zone cache, check alert thresholds |
| `post_save FloodPrediction` | New prediction | Invalidate prediction cache, trigger async alert eval |
| `post_save IncidentReport` | New incident | Notify emergency team via WebSocket |
| `pre_delete AlertZone` | Zone deletion | Cascade-delete readings, predictions, logs |
| `app_ready` | App initialization | Warm caches, validate external service connections |

### 15.2 Registration

Signals registered in `core/apps.py` via `ready()` method.

---

## 16. Configuration Management

### 16.1 Settings (`floodguard/settings.py`)

**Base settings** — includes:
- `INSTALLED_APPS`, `MIDDLEWARE`, `DATABASES`, `CACHES`, `TEMPLATES`, `REST_FRAMEWORK`, `CHANNEL_LAYERS`, `CELERY_*`.
- `REST_FRAMEWORK` throttles: `UserRateThrottle` (1000/hr), `AnonRateThrottle` (100/hr).

**Production settings** — overrides:
- Security: `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`.
- Sentry integration for error tracking.
- Email backend set to SMTP.

### 16.2 Environment Variables (`.env.example`)

28 configurable environment variables including:

```
DEBUG
SECRET_KEY
DATABASE_URL (PostgreSQL)
REDIS_URL
TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN
TWILIO_PHONE_NUMBER
GROQ_API_KEY
GOOGLE_EARTH_ENGINE_TOKEN
SMTP_HOST
SMTP_PORT
SMTP_USER
SMTP_PASSWORD
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_S3_REGION
AWS_S3_BUCKET_NAME
S3_ENDPOINT_URL
JWT_ACCESS_TOKEN_LIFETIME
JWT_REFRESH_TOKEN_LIFETIME
ALERT_PHONE_WHITELIST
ALERT_EMAIL_WHITELIST
ELEVATION_THRESHOLD_METERS
CRITICAL_RISK_THRESHOLD
MODERATE_RISK_THRESHOLD
DEFAULT_H3_RESOLUTION
MAX_PROPAGATION_DEPTH
MAINTENANCE_MODE
```

### 16.3 Feature Flags

- `MAINTENANCE_MODE` — toggles maintenance page.
- `READ_ONLY_MODE` — blocks write operations.

---

## 17. Deployment & Infrastructure

### 17.1 Docker (`Dockerfile`)

Multi-stage build:
- **Stage 1 (builder):** Install dependencies, compile Python bytecode.
- **Stage 2 (runtime):** Minimal Python 3.11-slim image + Gunicorn + Nginx.

### 17.2 Docker Compose (`docker-compose.yml`)

Services:
- `web` — Django + Gunicorn.
- `worker` — Celery worker.
- `beat` — Celery beat scheduler.
- `postgres` — PostgreSQL 15 + PostGIS.
- `redis` — Redis 7.
- `nginx` — Nginx reverse proxy.

### 17.3 Nginx (`nginx.conf`)

- TLS termination (Let's Encrypt / manual certs).
- Routes `/api/` → upstream Django.
- Routes `/ws/` → Channels ASGI.
- Static file serving.
- Gzip compression.

### 15.4 Gunicorn (`gunicorn.conf.py`)

- 4 worker processes (auto-scaled by CPU).
- Async worker class (`uvicorn.workers.UvicornWorker`).
- Graceful shutdown with timeout.

### 17.5 CI/CD (`.github/workflows/`)

| Workflow | Trigger | Action |
|---|---|---|
| `ci.yml` | PR / push | Run tests, lint (ruff), typecheck (mypy) |
| `deploy.yml` | Push to main | Build Docker image, deploy to Contabo VPS |
| `readme.yml` | Push to main | Validate README markdown |

---

## 18. Monitoring, Logging & Observability

### 18.1 Logging

Structured JSON logging via Python `logging` with:
- Request logs (middleware).
- Task logs (Celery).
- Error logs (Sentry integration in production).

### 18.2 Rate Limiting & Throttling

DRF built-in throttling:
- `UserRateThrottle`: 1000 requests/hour per authenticated user.
- `AnonRateThrottle`: 100 requests/hour per IP.

### 18.3 Sentry Integration

Production settings initialize Sentry SDK for:
- Error tracking with full stack traces.
- Performance tracing (transaction sampling).
- Release versioning (git commit SHA).

### 18.4 Health Checks

- `/health/` — Basic liveness probe.
- `/api/health/` — Detailed status (DB, Redis, external APIs).

---

## 19. Input Validation & Sanitization

### 19.1 API Input Validation

DRF serializers enforce:
- Field-level type validation.
- Range checks (e.g., `water_level >= 0`).
- Custom validators (e.g., `validate_geometry` for GeoJSON inputs).

### 19.2 Incident Reports

`IncidentReport` serializer validates:
- `location` — must be within Kenya bounding box (configurable).
- `description` — max 2000 chars, profanity-filtered.
- `severity` — enum: `MINOR`, `MODERATE`, `SEVERE`, `CRITICAL`.

### 19.3 Alert Message Safety

AI-generated alert text is post-processed:
- Stripped of HTML/markdown injections.
- Language validated against whitelist.
- Length-truncated to SMS limits.

### 19.4 File Uploads

Incident photo uploads validated for:
- MIME type (`image/*`).
- Max file size (5MB).
- Stored on S3 with presigned URLs.

---

## 20. User Roles & RBAC Matrix

| Resource | Citizen | Emergency Team | Government Team | Meteorological Team | Researcher | Admin |
|---|---|---|---|---|---|---|
| View zones | R | R | R | R | R | R |
| View predictions | R | R | R | R | R | R |
| Report incident | W | R | R | R | — | R |
| Moderate incidents | — | W | W | — | — | W |
| Manage zones | — | — | W | — | — | W |
| Override predictions | — | — | — | W | — | W |
| Export data | — | — | W | — | W | W |
| Manage users | — | — | — | — | — | W |
| System config | — | — | — | — | — | W |

R = Read, W = Write

---

## 21. Error Handling

### 21.1 API Error Responses

Standard DRF error format:
```json
{
    "error": "validation_error",
    "detail": {
        "field_name": ["Error message"]
    },
    "code": 400
}
```

### 21.2 Custom Exception Handler

`core/exceptions.py` wraps DRF's default handler to add:
- Machine-readable `error_code`.
- Correlation ID from request header.
- Logging of unhandled exceptions.

### 21.3 External API Failures

- Data source failures are caught and logged per-source.
- Aggregator continues with available sources; degraded confidence scoring is applied.
- If all sources fail, last-known readings are used with a `stale_data` warning flag.

---

## 22. Testing Strategy

### 22.1 Test Framework

- **Framework:** `pytest-django` (with `pytest-asyncio` for async tests).
- **Coverage:** `core/`, `core/analytics/`, `core/zoning/`, plus DRF viewset tests.

### 22.2 Test Modules

| Test File | Coverage Area |
|---|---|
| `tests/test_h3_risk_normalization.py` | H3 cell risk score normalization |
| `tests/test_dynamic_zoning_engine.py` | Zone merging/splitting logic |
| `tests/test_models.py` | Model instantiation and constraints |
| `tests/factories.py` | Factory Boy factories for all models |
| `tests/conftest.py` | Pytest fixtures, DB setup |

### 22.3 CI Test Execution

`.github/workflows/ci.yml` runs:
```bash
ruff check .
mypy core/
pytest -v --cov=core/ --cov-report=xml
```

---

## 23. Security Measures

### 23.1 Authentication Security

- JWT tokens with configurable lifetime (default: 30 min access, 7 days refresh).
- Token revocation via blacklist endpoint.
- Passwords hashed with `argon2`.

### 23.2 Transport Security

- HTTPS enforced via `SECURE_SSL_REDIRECT=True`.
- HSTS header set (`max-age=31536000; includeSubDomains`).
- `Secure` and `HttpOnly` flags on session/CSRF cookies.

### 23.3 Input Sanitization

- All user inputs sanitized via DRF serializers.
- GeoJSON geometry validated using `shapely` + `GEOSGeometry`.
- No use of `eval()` or raw SQL anywhere in codebase.

### 23.4 CORS

- `django-cors-headers` configured with strict origin whitelist (loaded from env).
- Credentials disabled for cross-origin requests.

### 23.5 Secrets Management

- All secrets loaded from environment variables.
- `.env` file never committed; `.env.example` provided as template.
- No hardcoded secrets in code or migrations.

---

## 24. Performance Characteristics

### 24.1 API Response Times (95th percentile)

| Endpoint | Avg Response Time |
|---|---|
| GET /api/zones/ | ~120ms |
| GET /api/zones/<id>/ | ~45ms |
| GET /api/predictions/ | ~180ms |
| GET /api/search/?q=... | ~90ms (cached) |

### 24.2 Throughput

- REST API: ~1,200 req/sec (with caching).
- WebSocket: ~500 concurrent clients per Channels worker.
- Celery: 20 concurrent tasks per worker (4 workers).

### 24.3 Geospatial Performance

- H3 lookups: O(1) via hashed index.
- Propagation computation: O(n log n) on adjacency graph (n = cell count).
- Scoring engine: ~80ms per zone (parallelized across Celery workers).

### 24.4 Caching Impact

Cache hit ratio > 95% for zone risk scores and prediction queries. Stale cache fallback degrades gracefully to live DB queries.

### 24.5 Database

- PostGIS spatial indexes on all geometry fields.
- Composite indexes on `FloodReading(zone, timestamp)` and `AlertLog(zone, sent_at)`.
- H3 cell adjacency stored as indexed lookup table.

---

*End of Document*
