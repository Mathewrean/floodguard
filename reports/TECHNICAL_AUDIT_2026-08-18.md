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
- Full Django/pytest execution: blocked locally because the supplied WSL virtualenv has neither Django nor pip/ensurepip installed.
- Docker Compose validation: blocked locally because Docker is not installed on this workstation.
- Public-site verification: blocked because `.env` only permits local hosts and retains the placeholder `https://yourdomain.com`; no deployable public domain is configured in the workspace.

## Required operator actions

1. Set the real domain **plus `localhost,127.0.0.1`** in VPS `ALLOWED_HOSTS`, and configure DNS/TLS reverse proxy routing. The loopback values let the post-deploy internal health probe pass Django host validation.
2. Ensure GitHub repository secrets `VPS_HOST` and `VPS_SSH_PRIVATE_KEY` are present.
3. Configure `GRAPHOPPER_API_KEY` on the VPS. Without it, safe routing intentionally returns a fallback response rather than claiming GraphHopper is active.
4. Build the image with the updated requirements, commit and push to `main`, then inspect the GitHub Actions deploy run and `/health/`.
5. Run `pytest` in a provisioned environment and use a real browser runner (Playwright/Selenium) for full browser/device coverage.

## Access record

The git-ignored local record is `.local/ACCOUNT_ACCESS.md`. It lists the `/login/` endpoint and role-account slots without recording passwords. Store actual passwords only in an approved password manager.
