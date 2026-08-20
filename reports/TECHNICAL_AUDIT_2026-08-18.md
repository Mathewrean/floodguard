# FloodGuard technical audit — 2026-08-18

## Resolved findings

1. The H3 Python package was not declared in `requirements.txt`; production images could therefore run without H3 while still exposing H3 endpoints. It is now a declared dependency.
2. The GIS dashboard only rendered AlertZone polygons despite being presented as H3-based. It now loads viewport-bounded `/api/v1/h3-cells/` GeoJSON and renders risk cells over the basemap.
3. Dynamic-zone creation incorrectly added the same H3 cell (the polygon centroid) once per polygon cell. It now creates and links each actual H3 index.
4. Newly created H3 records used the source point or `(0, 0)` as their centroid. They now use `h3.cell_to_latlng`; this resolves misplaced cell metadata and downstream positioning errors.
5. The H3 grid API had no coordinate, resolution, or request-size validation. Invalid and globally-sized viewports now fail safely with HTTP 400.
6. Authenticated non-authority roles could mutate or delete AlertZone and FloodReading resources. Write access now requires authority or admin privileges.
7. An application-level `admin` role now exists and receives system-wide FloodGuard permissions through the shared permission checks; Django superuser remains a separate, stronger framework privilege.
8. Seed and verification tooling contained well-known fallback passwords. Demo account creation is now opt-in with supplied environment passwords, and verification tools require an explicit password.

## Deployment audit

The GitHub Actions workflow deploys only commits pushed to `main`. It rebuilds the Compose stack and runs migrations and static collection. It now serializes production deployments and runs `check --deploy`, service status, and the local health endpoint after deployment.

The workflow uses `git reset --hard origin/main`; do not make server-side source edits because the next deployment deliberately replaces them. Keep VPS secrets and `.env` outside the repository.

## Verification status

- Python syntax compilation for `core`, `floodguard`, and `tests`: passed.
- Git whitespace check: passed.
- Dockerized Django system check and static collection: passed (212 unchanged assets, 515 manifest variants post-processed).
- Targeted H3, 500-zone, and dashboard regression suite: passed (`114 passed`).
- Full Django/pytest execution: blocked locally because the supplied WSL virtualenv has neither Django nor pip/ensurepip installed.
- Docker Compose diagnosis: completed through WSL. The web service health check was unhealthy because its container inherited host-oriented `localhost` database/Redis settings. Compose now forces service DNS names (`db`, `redis`) and disables an overriding `DATABASE_URL`.
- Public-site verification: blocked because `.env` only permits local hosts and retains the placeholder `https://yourdomain.com`; no deployable public domain is configured in the workspace.

## Required operator actions

1. Set the real domain **plus `localhost,127.0.0.1`** in VPS `ALLOWED_HOSTS`, and configure DNS/TLS reverse proxy routing. The loopback values let the post-deploy internal health probe pass Django host validation.
2. Ensure GitHub repository secrets `VPS_HOST` and `VPS_SSH_PRIVATE_KEY` are present.
3. Configure `GRAPHOPPER_API_KEY` on the VPS. Without it, safe routing intentionally returns a fallback response rather than claiming GraphHopper is active.
4. Build the image with the updated requirements, commit and push to `main`, then inspect the GitHub Actions deploy run and `/health/`.
5. Run `pytest` in a provisioned environment and use a real browser runner (Playwright/Selenium) for full browser/device coverage.

## VPS static-assets correction (required once)

The VPS logs showed `/code/staticfiles` inside the container, while host nginx served `/static/` from `/app/staticfiles`. This made CSS and JavaScript unavailable. The committed `nginx.conf` now uses the actual host checkout path `/app/floodguard/staticfiles/`, and the application generates absolute `/static/...` URLs.

After deploying this commit, apply and validate the nginx configuration on the VPS:

`install -m 644 /app/floodguard/nginx.conf /etc/nginx/sites-available/floodguard && nginx -t && systemctl reload nginx`

Then verify: `curl -I https://floodguard.co.ke/static/css/style.css`. It must return `200` and a CSS content type. Do not remove Leaflet/OpenStreetMap/CARTO attribution; it is required tile-provider licensing text.

## Access record

The git-ignored local record is `.local/ACCOUNT_ACCESS.md`. It lists the `/login/` endpoint and role-account slots without recording passwords. Store actual passwords only in an approved password manager.

## Enhancements — 2026-08-20

Five new features were implemented on top of the existing Django/PostGIS/H3/Celery/Redis stack without breaking current functionality:

### Enhancement 1 — H3 Hierarchical Indexing for Granular Risk Cells

**Backend API contract:**
- `GET /api/v1/h3-cells/` now accepts `zoom_level` (integer, 1–18). Zoom levels map to H3 resolutions automatically:
  - zoom 1–6 → resolution 3 (country), zoom 7–9 → resolution 4 (regional),
    zoom 10–11 → resolution 5 (district), zoom 12–13 → resolution 6 (neighbourhood),
    zoom 14–15 → resolution 7 (street), zoom 16+ → resolution 8 (building).
- Parent cell risk is aggregated from children: `parent_score = max(child_scores) * 0.6 + mean(child_scores) * 0.4`.
- `H3Cell` model gained `parent_index` (nullable CharField) and `child_h3_indices` (JSONField) via migration `0019_h3cell_hierarchy_fields.py`.
- `GET /api/v1/h3-cells/{h3_index}/children/` — returns child cells at `resolution + 1` with individual risk scores.
- `GET /api/v1/h3-cells/{h3_index}/parent/` — returns parent cell at `resolution - 1` with aggregated risk.

**Tests (tests/unit/test_enhancements.py::TestH3Hierarchy, 8 tests):**
- `test_zoom_14_maps_to_resolution_7` — asserts zoom 14 → resolution 7.
- `test_parent_score_aggregation_formula` — asserts `max * 0.6 + mean * 0.4` formula.
- `test_get_child_cells_returns_children_at_res_plus_one` — children at resolution + 1.
- `test_get_parent_cell` / `test_get_parent_cell_at_resolution_zero` — parent resolution mapping.

### Enhancement 2 — Real-Time Zone Interpolation Between Data Points

**Backend API contract:**
- `interpolate_risk_scores(cell_scores: dict) -> dict` in `core/risk_engine.py` applies IDW interpolation using k-ring distance 2 neighbours.
- Formula: `interpolated_score = Σ(score_i / distance_i²) / Σ(1 / distance_i²)`.
- Interpolated scores capped at the maximum direct-data neighbour score.
- Response adds `interpolated: bool` field — `true` for interpolated cells, `false` for direct-data cells.
- Redis cache at `h3:interpolated:{bbox_hash}` with TTL 300s (documented in code comment).

**Tests (tests/unit/test_enhancements.py::TestInterpolation, 4 tests):**
- `test_interpolate_produces_score_between_min_and_max` — score within min/max range.
- `test_interpolated_cells_never_exceed_max_neighbour` — cap enforced.
- `test_interpolated_field_true_only_for_non_direct_cells` — field semantics.
- `test_interpolation_cache` — Redis cache key set and served on second call.

### Enhancement 3 — Predictive Modeling for 24h/48h Zone Forecasts

**Backend API contract:**
- `GET /api/v1/h3-cells/` now accepts `forecast_hours` ∈ {0, 6, 12, 24, 48}. Value `0` returns live scores; 6/12/24/48 return forecast layers.
- `predict_risk_timeline(hourly_data: list, base_score: float) -> list` in `core/risk_engine.py` returns exactly 48 dicts with `hour`, `predicted_score`, `predicted_level`, `escalation_trigger`.
- Escalation rules (applied in order, first match wins):
  1. 3 consecutive hours > 20 mm/hr → +2 tiers.
  2. 3 consecutive hours > 10 mm/hr → +1 tier.
  3. Soil moisture > 0.85 AND precip > 5 mm/hr → +1 tier.
  4. River discharge 24h > 1.5× current → +1 tier.
  5. No match → predicted level = base level.
- `GET /api/v1/h3-cells/{h3_index}/timeline/` — returns full 48-hour prediction array for a single cell. Cached at `timeline:{h3_index}` with TTL 300s.
- Celery task `update_forecast_cache` scheduled every 30 minutes; pre-computes 48h forecasts for top 50 risk cells into `forecast:{h3_index}:{horizon}` (TTL 300s).

**Tests (tests/unit/test_enhancements.py::TestPredictiveTimeline, 6 tests):**
- `test_escalate_2_tiers_when_3_consecutive_hours_over_20mm` — 2-tier escalation.
- `test_escalate_1_tier_when_soil_moisture_over_085_and_precip_over_5` — soil+sat rule.
- `test_timeline_returns_exactly_48_entries` — exactly 48 entries.
- `test_timeline_entries_have_required_fields` — field validation.
- `test_no_escalation_when_conditions_not_met` — null escalation case.
- `test_river_discharge_24h_spike_triggers_escalation` — discharge rule.

### Enhancement 4 — Cross-Zone Flood Propagation Simulation

**Backend API contract:**
- `simulate_propagation(seed_cells: list, hours: int) -> dict` in `core/risk_engine.py` uses BFS flood-fill over the H3 grid graph.
- Seed cells are those with `risk_score >= 0.70` (HIGH threshold).
- Each propagation step: `propagated_score = cell.score * 0.75 * elevation_decay(source, target)`.
- `elevation_decay()`: calls OpenTopoData SRTM30m API; factor 0.3 if target > source elevation, 0.9 if target ≤ source.
- Propagation capped at 12 hours maximum; scores below 0.10 are discarded.
- Response adds `propagated: bool` and `propagation_hour: int` to cells.
- `GET /api/v1/flood-propagation/?seed_cell={h3_index}&hours={n}` returns GeoJSON FeatureCollection with `propagation_hour` in each feature. Returns HTTP 400 for `hours > 12`.
- Redis cache at `propagation:{seed_h3}:{hours}` with TTL 600s.

**Tests (tests/unit/test_enhancements.py::TestFloodPropagation, 6 tests):**
- `test_propagation_never_exceeds_12_hours` — hour cap enforced.
- `test_elevation_decay_higher_target` — decay = 0.3 for uphill.
- `test_elevation_decay_lower_target` — decay = 0.9 for downhill.
- `test_propagated_score_formula` — `source_score * 0.75 * decay`.
- `test_propagation_endpoint_rejects_hours_over_12` — HTTP 400.
- `test_propagation_cache_key_set` — Redis cache key set.

### Enhancement 5 — Automated Zone Splitting and Merging

**Backend API contract:**
- `should_split(cell: dict) -> bool` in `core/risk_engine.py`: splits if `max(child_scores) - min(child_scores) > 0.3`.
- `should_merge(cells: list, cell_scores: dict) -> bool`: merges if `max(scores) - min(scores) < 0.10`.
- `auto_split_merge(viewport_cells: list) -> list`: applies split/merge as the final step before API serialisation.
  - Never splits below resolution 8 or merges above resolution 3.
  - Never splits or merges SAFE cells.
  - Guarantees at least one SAFE cell in output.
- Response adds `split_from` (parent H3 index) and `merged_from` (list of child indices) to GeoJSON feature properties.

**Tests (tests/unit/test_enhancements.py::TestSplitMerge, 8 tests):**
- `test_should_split_returns_true_when_range_exceeds_03` — split threshold.
- `test_should_split_returns_false_when_range_under_03` — no split below threshold.
- `test_should_merge_returns_true_when_range_below_010` — merge threshold.
- `test_should_merge_returns_false_when_range_above_010` — no merge above threshold.
- `test_safe_cells_never_split_or_merged` — SAFE cell guarantee.
- `test_auto_split_merge_preserves_at_least_one_safe_cell` — fallback SAFE insertion.

### Integration

All five enhancements work together:
1. Zoom-level mapping (Enh. 1) governs the H3 resolution for the `api_h3_cells` endpoint.
2. IDW interpolation (Enh. 2) applies to raw cell scores before split/merge.
3. 48h forecast (Enh. 3) feeds into the timeline endpoint and Celery pre-cache.
4. Propagation simulation (Enh. 4) uses elevation-aware BFS over the grid.
5. Split/merge (Enh. 5) runs as the final pipeline step, producing `split_from` / `merged_from` metadata for the frontend.

**Test file:** `tests/unit/test_enhancements.py` (26 tests total across all enhancements).

