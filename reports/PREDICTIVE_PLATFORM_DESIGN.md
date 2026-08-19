# FloodGuard predictive early-warning platform — technical design

## 1. Scope and compatibility

This design adds predictive flood intelligence without removing the current Django, Leaflet, H3, GraphHopper, reporting, authority-dashboard, or alert functions. Existing `AlertZone` records remain authority-managed operational zones. Predictions are stored separately and rendered as an opt-in time-based overlay; they do not overwrite observed risk.

### Target architecture

```text
Open-Meteo QPF ─┐                         ┌─> PostGIS prediction vectors ─> Leaflet time slider
WeatherAPI      ├─> weather-ingestor ─> PostgreSQL/Timescale ─> ML inference ─┤
Gauge/sensor logs┘       (container)             │                    │        └─> H3 risk overlay
                                                  │                    v
Citizen locations ─> PostGIS geofence query ─> Redis stream ─> Celery workers ─> FCM / Twilio
Citizen reports ──────────────────────────────────────────────────────> responder WebSocket refresh
```

## 2. Phase 1 — weather ingestion

Create a `weather-ingestor` container with its own service module and a Celery Beat schedule. It requests Open-Meteo using `hourly=precipitation,rain`; WeatherAPI is used only after retryable Open-Meteo failure, timeout, malformed payload, or rate-limit response.

Rules:

- Validate UTC timestamps, unit `mm`, array lengths, and no future horizon above 16 days.
- Store source, request time, response checksum, and fallback reason for auditability.
- Use an idempotency key of `(source, grid_cell, forecast_time, model_run_time)`.
- Keep raw payloads in object storage or compressed JSON for replay; keep normalized series in PostgreSQL.
- Exponential retry: 30 s, 2 min, 10 min; trip a circuit breaker for a failing provider and publish a health metric.

Example Open-Meteo request:

```text
GET /v1/forecast?latitude=-1.2921&longitude=36.8219&hourly=precipitation,rain&forecast_days=16&timezone=UTC
```

Normalized forecast model (TimescaleDB hypertable if available; standard PostgreSQL partitioning otherwise):

```sql
CREATE TABLE weather_forecast_hourly (
  id BIGSERIAL PRIMARY KEY,
  grid_h3 VARCHAR(32) NOT NULL,
  forecast_time TIMESTAMPTZ NOT NULL,
  model_run_time TIMESTAMPTZ NOT NULL,
  precipitation_mm NUMERIC(7,2) NOT NULL CHECK (precipitation_mm >= 0),
  rain_mm NUMERIC(7,2) NOT NULL CHECK (rain_mm >= 0),
  provider VARCHAR(32) NOT NULL,
  quality VARCHAR(16) NOT NULL DEFAULT 'validated',
  UNIQUE (grid_h3, forecast_time, model_run_time, provider)
);
CREATE INDEX weather_forecast_h3_time_idx ON weather_forecast_hourly(grid_h3, forecast_time DESC);
SELECT create_hypertable('weather_forecast_hourly', 'forecast_time', if_not_exists => TRUE);

CREATE TABLE gauge_observation_hourly (
  id BIGSERIAL PRIMARY KEY,
  gauge_id VARCHAR(80) NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL,
  rainfall_mm NUMERIC(7,2), water_level_m NUMERIC(8,3),
  location geometry(Point, 4326) NOT NULL,
  source VARCHAR(32) NOT NULL,
  UNIQUE (gauge_id, observed_at)
);
CREATE INDEX gauge_observation_location_gix ON gauge_observation_hourly USING GIST(location);
```

Mock response contract:

```json
{
  "hourly": {
    "time": ["2026-08-19T12:00", "2026-08-19T13:00"],
    "precipitation": [1.2, 4.7],
    "rain": [1.2, 4.7]
  }
}
```

## 3. Phase 2 — time-series ML

Start with a baseline (gradient boosting or persistence model) and promote to an LSTM or Temporal Fusion Transformer only after a back-test proves material improvement. PyTorch Forecasting TFT is preferred when static categorical/spatial context and missing covariates are significant.

Feature sets:

- Dynamic: 16-day hourly QPF, prior rainfall, gauge water level/discharge, satellite-water signals, sensor confidence.
- Static per H3 cell: DEM elevation, slope, flow accumulation, soil saturation proxy, impervious-surface ratio, distance to drainage/river.
- Labels: observed water level and/or validated flood extent for +6 h, +12 h, +24 h.

Version model artifacts, feature schema, training datasets, and calibration thresholds. Inference writes uncertainty, not just a point score. Predictions are rejected when input freshness or confidence falls below a configurable threshold.

```text
hourly features -> feature validation -> TFT/LSTM inference -> calibration
                -> H3-cell horizon predictions -> polygonization -> alert evaluation
```

## 4. Phase 3 — PostGIS prediction and geofencing

```sql
CREATE TABLE flood_prediction_run (
  id UUID PRIMARY KEY,
  model_version VARCHAR(80) NOT NULL,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  source_freshness_seconds INTEGER NOT NULL,
  status VARCHAR(20) NOT NULL CHECK (status IN ('running','ready','failed','superseded'))
);

CREATE TABLE flood_prediction_cell (
  id BIGSERIAL PRIMARY KEY,
  run_id UUID NOT NULL REFERENCES flood_prediction_run(id) ON DELETE CASCADE,
  h3_index VARCHAR(32) NOT NULL,
  horizon_hours SMALLINT NOT NULL CHECK (horizon_hours IN (6,12,24)),
  risk_score NUMERIC(4,3) NOT NULL CHECK (risk_score BETWEEN 0 AND 1),
  water_level_change_m NUMERIC(7,3),
  confidence NUMERIC(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  geom geometry(Polygon, 4326) NOT NULL,
  UNIQUE(run_id, h3_index, horizon_hours)
);
CREATE INDEX flood_prediction_cell_geom_gix ON flood_prediction_cell USING GIST(geom);
CREATE INDEX flood_prediction_cell_run_horizon_idx ON flood_prediction_cell(run_id, horizon_hours, risk_score DESC);

CREATE TABLE flood_prediction_area (
  id BIGSERIAL PRIMARY KEY,
  run_id UUID NOT NULL REFERENCES flood_prediction_run(id) ON DELETE CASCADE,
  horizon_hours SMALLINT NOT NULL CHECK (horizon_hours IN (6,12,24)),
  risk_level VARCHAR(16) NOT NULL,
  confidence NUMERIC(4,3) NOT NULL,
  geom geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX flood_prediction_area_geom_gix ON flood_prediction_area USING GIST(geom);

CREATE TABLE device_location_subscription (
  id UUID PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES auth_user(id) ON DELETE CASCADE,
  location geometry(Point, 4326) NOT NULL,
  accuracy_m NUMERIC(8,2), updated_at TIMESTAMPTZ NOT NULL,
  fcm_token TEXT, sms_opt_in BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX device_location_subscription_gix ON device_location_subscription USING GIST(location);
```

Optimized alert match: first use the GIST index bounding-box operator, then exact geometry. `ST_Covers` includes a user exactly on a threat boundary; use `ST_Contains` if boundary users must be excluded.

```sql
SELECT d.id, d.user_id, p.id AS prediction_area_id, p.horizon_hours, p.risk_level
FROM flood_prediction_area p
JOIN device_location_subscription d
  ON d.location && p.geom
 AND ST_Covers(p.geom, d.location)
WHERE p.run_id = $1
  AND p.horizon_hours = $2
  AND p.risk_level IN ('high', 'critical')
  AND d.updated_at > now() - interval '30 minutes';
```

Polygonization groups neighboring high-risk H3 cells by horizon and risk band, unions them with `ST_UnaryUnion`, validates using `ST_MakeValid`, and stores a `MultiPolygon` only after an area/minimum-confidence check.

## 5. Phase 4 — asynchronous alerts

Use Redis Streams or RabbitMQ as the durable handoff between spatial matching and notification delivery. Celery workers must not execute the expensive PostGIS match in the request path.

```text
prediction-ready event
  -> geofence worker (PostGIS batches of 1,000)
  -> flood.alert.candidate stream (dedupe key: run/user/horizon)
  -> notification workers
       -> FCM push
       -> Twilio SMS fallback for opted-in/high-critical alerts
  -> delivery ledger and retry/dead-letter stream
```

Recommended workers: 2 geofence workers (bounded concurrency 2), 4 notification workers (concurrency 8 with provider-specific rate limits), and a separate retry worker. Persist idempotency/delivery state before calling FCM/Twilio. Use exponential retry and dead-letter messages; never retry an opt-out.

## 6. Phase 5 — frontend and refactoring

- Keep Leaflet and current H3/observed-risk layers unchanged.
- Add `PredictionOverlayLayer` with API parameters `run_id`, `horizon_hours`, and `risk_min`.
- Add a compact, mobile-safe time slider with +6 h, +12 h, +24 h. It is off by default and labelled “Forecast — not observed”.
- Persist only the selected horizon in local storage; never cache stale prediction geometry as current risk.
- Use CSS/HTML `divIcon` markers and inline SVG/CSS shapes for map controls—no low-resolution raster icons. Maintain 44×44 px mobile tap targets and descriptive labels.

Refactor service boundaries:

```text
core/services/weather_ingestion.py
core/services/forecast_features.py
core/services/prediction_inference.py
core/services/prediction_geometry.py
core/services/geofence.py
core/services/notification_dispatch.py
```

Views validate/request; services perform domain work; Celery tasks orchestrate asynchronous execution. Add explicit DTOs/Pydantic-style validation at service boundaries and replace broad `except Exception` blocks with observable, typed failures.

## 7. Phase 6 — quality assurance and release gates

| Layer | Required checks |
|---|---|
| Regression | Django unit/integration tests for map, H3, auth, RBAC, reports, GraphHopper contract; 90% coverage on new/refactored service modules |
| API resilience | `responses` mocks for Open-Meteo/WeatherAPI: success, timeout, 429, invalid JSON, mismatched arrays, fallback and circuit breaker |
| Spatial precision | Synthetic polygon test: inside point matches; point exactly on boundary follows documented `ST_Covers`; point 1 m outside does not match |
| E2E | Playwright desktop + mobile projects: register/login, GPS/pin report, authority live refresh, GIS legend/panel collapse, forecast slider, route availability/error state |
| Load/chaos | Locust/K6: 10,000 location updates; PostgreSQL timeout, Redis restart, provider outage; assert queue durability/idempotent delivery |
| Security | Secret scan, dependency scan, access-control and notification opt-out tests |

CI gates: migrations check, `manage.py check --deploy`, lint/type check, unit/integration suite, Playwright smoke suite, coverage threshold, container build, and staging deployment with synthetic alert verification. Production promotion requires a green staging report plus an approved model/version record.

## 8. Delivery roadmap

1. **Foundation (1–2 sprints):** migrations, forecast schemas, provider adapter, raw/normalized data retention, health metrics, mocked API tests.
2. **Baseline prediction (1 sprint):** feature pipeline, calibrated baseline, H3 output, forecast overlay API/UI, spatial precision suite.
3. **Alerting (1 sprint):** geofence worker, Redis/RabbitMQ stream, FCM/Twilio adapters, delivery ledger, dedupe and opt-out controls.
4. **Model upgrade (2+ sprints):** TFT/LSTM training/back-testing, model registry, drift monitoring, shadow-mode comparison against baseline.
5. **Hardening (continuous):** Playwright mobile matrix, load/chaos tests, runbooks, dashboards, SLOs, staged rollout by geography.

No prediction alerts should be enabled for the public until shadow-mode accuracy, latency, provider-fallback behavior, and boundary tests meet the agreed operational acceptance criteria.
