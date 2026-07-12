#!/usr/bin/env python3
"""
Dynamic README.md Generator for FloodGuard

This script parses the project structure, dependencies, and code documentation
to automatically generate an up-to-date README.md file.

Usage:
    python scripts/generate_readme.py [--check] [--output README.md]

Options:
    --check     Only check if README needs updating (exit code 1 if outdated)
    --output    Output file path (default: README.md at project root)
"""

import os
import re
import sys
import json
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Project root (assumes script is in scripts/ directory)
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
README_PATH = PROJECT_ROOT / "README.md"


class ProjectParser:
    """Parses project structure and extracts metadata."""

    def __init__(self, root_path: Path):
        self.root = root_path
        self.data: Dict = {}

    def parse_requirements(self) -> Dict:
        """Parse requirements.txt to extract dependencies and versions."""
        req_file = self.root / "requirements.txt"
        if not req_file.exists():
            return {"error": "requirements.txt not found"}

        dependencies = []
        with open(req_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Handle version specifiers
                    match = re.match(r'^([a-zA-Z0-9_-]+)(.+)?$', line)
                    if match:
                        pkg = match.group(1)
                        version = match.group(2).strip() if match.group(2) else ""
                        dependencies.append({"name": pkg, "version": version})
                    else:
                        dependencies.append({"raw": line})

        return {
            "count": len(dependencies),
            "dependencies": dependencies
        }

    def parse_django_settings(self) -> Dict:
        """Extract key settings from Django settings.py."""
        settings_file = self.root / "floodguard" / "settings.py"
        if not settings_file.exists():
            return {}

        settings_content = settings_file.read_text()
        info = {}

        # Extract INSTALLED_APPS
        apps_match = re.search(
            r'INSTALLED_APPS\s*=\s*\[(.*?)\]',
            settings_content,
            re.DOTALL
        )
        if apps_match:
            apps_str = apps_match.group(1)
            apps = re.findall(r"'([^']+)'", apps_str)
            info["installed_apps"] = apps

        # Extract DATabases config
        db_match = re.search(
            r"DATABASES\s*=\s*\{.*?'default':\s*\{.*?'ENGINE':\s*'([^']+)'.*?'NAME':\s*'([^']+)'.*?\}",
            settings_content,
            re.DOTALL
        )
        if db_match:
            info["database_engine"] = db_match.group(1)
            info["database_name"] = db_match.group(2)

        # Extract middleware
        middleware_match = re.search(
            r'MIDDLEWARE\s*=\s*\[(.*?)\]',
            settings_content,
            re.DOTALL
        )
        if middleware_match:
            middleware_str = middleware_match.group(1)
            middleware = re.findall(r"'([^']+)'", middleware_str)
            info["middleware"] = middleware

        # Extract Channels config
        if "channels" in info.get("installed_apps", []):
            info["channels_enabled"] = True
            channel_layer_match = re.search(
                r"CHANNEL_LAYERS\s*=\s*\{(.*?)\}",
                settings_content,
                re.DOTALL
            )
            if channel_layer_match:
                info["channel_layer_config"] = True

        # Extract Celery config
        if "django_celery_beat" in info.get("installed_apps", []):
            info["celery_beat_enabled"] = True

        return info

    def parse_docker_compose(self) -> Dict:
        """Extract service definitions from docker-compose.yml."""
        compose_file = self.root / "docker-compose.yml"
        if not compose_file.exists():
            return {}

        import yaml
        try:
            with open(compose_file) as f:
                compose_data = yaml.safe_load(f)
            services = compose_data.get("services", {})
            return {
                "services": list(services.keys()),
                "service_count": len(services)
            }
        except ImportError:
            return {"error": "PyYAML not available"}
        except Exception as e:
            return {"error": str(e)}

    def count_files(self) -> Dict:
        """Count various file types in the project."""
        counts = {
            "python_files": 0,
            "html_templates": 0,
            "css_files": 0,
            "js_files": 0,
            "test_files": 0,
            "migration_files": 0
        }

        for path in self.root.rglob("*"):
            if path.is_file():
                suffix = path.suffix.lower()
                if suffix == ".py":
                    counts["python_files"] += 1
                    if "test" in path.name or "tests" in path.parts:
                        counts["test_files"] += 1
                    if "migrations" in path.parts and path.name != "__init__.py":
                        counts["migration_files"] += 1
                elif suffix == ".html":
                    counts["html_templates"] += 1
                elif suffix == ".css":
                    counts["css_files"] += 1
                elif suffix == ".js":
                    counts["js_files"] += 1

        return counts

    def parse_models(self) -> List[str]:
        """Extract model names from core/models.py."""
        models_file = self.root / "core" / "models.py"
        if not models_file.exists():
            return []

        content = models_file.read_text()
        # Find class definitions that inherit from models.Model
        model_pattern = r'class\s+(\w+)\s*\(\s*models\.Model\s*\)'
        models = re.findall(model_pattern, content)
        return models

    def parse_views(self) -> Dict:
        """Extract view/endpoint information from core/views.py."""
        views_file = self.root / "core" / "views.py"
        if not views_file.exists():
            return {}

        content = views_file.read_text()
        info = {
            "function_views": [],
            "class_views": [],
            "viewsets": []
        }

        # Function-based views
        func_pattern = r'^def\s+([a-zA-Z0-9_]+)\s*\('
        for match in re.finditer(func_pattern, content, re.MULTILINE):
            info["function_views"].append(match.group(1))

        # Class-based views and ViewSets
        class_pattern = r'^class\s+(\w+)\s*\(.*View.*\):'
        for match in re.finditer(class_pattern, content, re.MULTILINE):
            class_name = match.group(1)
            if "ViewSet" in content[match.start():match.start()+200]:
                info["viewsets"].append(class_name)
            else:
                info["class_views"].append(class_name)

        return info

    def parse_urls(self) -> List[str]:
        """Extract URL patterns from core/urls.py."""
        urls_file = self.root / "core" / "urls.py"
        if not urls_file.exists():
            return []

        content = urls_file.read_text()
        # Find path() and re_path() calls - extract route names/patterns
        url_patterns = []

        # Look for path(..., name='...') patterns
        name_pattern = r"path\(.*?name=['\"]([^'\"]+)['\"]"
        for match in re.finditer(name_pattern, content):
            url_patterns.append(match.group(1))

        return url_patterns

    def parse_docker_files(self) -> Dict:
        """Check for Docker-related configuration files."""
        docker_files = {}
        for fname in ["Dockerfile", "docker-compose.yml", ".dockerignore"]:
            path = self.root / fname
            if path.exists():
                docker_files[fname] = {"exists": True, "size": path.stat().st_size}
            else:
                docker_files[fname] = {"exists": False}

        return docker_files

    def get_git_info(self) -> Dict:
        """Get Git repository information if available."""
        try:
            # Check if git repo
            git_dir = self.root / ".git"
            if not git_dir.exists():
                return {"git_enabled": False}

            # Get current branch
            branch = subprocess.check_output(
                ["git", "branch", "--show-current"],
                cwd=self.root,
                text=True
            ).strip()

            # Get commit count
            commit_count = subprocess.check_output(
                ["git", "rev-list", "--count", "HEAD"],
                cwd=self.root,
                text=True
            ).strip()

            # Get latest commit message
            latest_msg = subprocess.check_output(
                ["git", "log", "-1", "--pretty=%s"],
                cwd=self.root,
                text=True
            ).strip()

            return {
                "git_enabled": True,
                "current_branch": branch,
                "commit_count": commit_count,
                "latest_commit": latest_msg
            }
        except (subprocess.CalledProcessError, FileNotFoundError):
            return {"git_enabled": False}

    def parse_all(self) -> Dict:
        """Run all parsers and collect data."""
        self.data = {
            "project": "FloodGuard",
            "generated_at": datetime.now().isoformat(),
            "structure": {},
            "dependencies": {},
            "settings": {},
            "docker": {},
            "git": {},
            "code_metrics": {},
            "features": {}
        }

        self.data["dependencies"] = self.parse_requirements()
        self.data["settings"] = self.parse_django_settings()
        self.data["docker"] = self.parse_docker_compose()
        self.data["git"] = self.get_git_info()
        self.data["code_metrics"] = self.count_files()
        self.data["structure"]["models"] = self.parse_models()
        self.data["structure"]["views"] = self.parse_views()
        self.data["structure"]["urls"] = self.parse_urls()

        # Feature detection based on file existence and code patterns
        self.data["features"] = {
            "gis": (self.root / "core" / "models.py").read_text().find("PointField") != -1,
            "websockets": (self.root / "floodguard" / "routing.py").exists(),
            "celery_tasks": (self.root / "core" / "tasks.py").exists(),
            "ml_model": (self.root / "ml_model").exists(),
            "real_time_alerts": (self.root / "core" / "consumers.py").exists(),
            "api": (self.root / "core" / "serializers.py").exists(),
            "tests": (self.root / "tests").exists(),
            "docker": (self.root / "docker-compose.yml").exists()
        }

        return self.data


class ReadmeGenerator:
    """Generates README.md content from parsed project data."""

    def __init__(self, data: Dict, project_root: Path):
        self.data = data
        self.root = project_root

    def generate(self) -> str:
        """Generate full README content."""
        sections = [
            self._generate_header(),
            self._generate_features(),
            self._generate_tech_stack(),
            self._generate_architecture(),
            self._generate_installation(),
            self._generate_usage(),
            self._generate_api_docs(),
            self._generate_testing(),
            self._generate_deployment(),
            self._generate_development(),
            self._generate_contributing(),
            self._generate_license(),
        ]

        return "\n\n".join(sections) + "\n"

    def _generate_header(self) -> str:
        """Generate project title and badge section."""
        data = self.data
        return f"""# FloodGuard

> AI-Powered Flood Prediction and Early Warning System

![ Django](https://img.shields.io/badge/Django-4.2.30-green?logo=django)
![ DRF](https://img.shields.io/badge/DRF-3.14.0-blue)
![ PostGIS](https://img.shields.io/badge/PostGIS-3.4-cyan?logo=postgresql)
![ Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![ License](https://img.shields.io/badge/license-MIT-green)

**Last updated:** {data['generated_at'][:10]}

A comprehensive flood monitoring and alert system leveraging geospatial analytics, machine learning, and real-time data processing to provide early warnings for potential flooding events.

---

"""

    def _generate_features(self) -> str:
        """Generate features section."""
        features = self.data["features"]
        feature_list = [
            "**Real-time Flood Monitoring** - Live sensor data ingestion and alerting",
            "**GIS-Enabled Mapping** - Interactive Leaflet maps with GeoDjango backend",
            "**Machine Learning Prediction** - scikit-learn based risk scoring engine",
            "**Multi-Channel Alerts** - SMS (Africa's Talking), email, and in-app notifications",
            "**Role-Based Access** - Citizen, Emergency Team, and Admin dashboards",
            "**WebSocket Streaming** - Real-time updates via Django Channels",
            "**Celery Task Queue** - Async processing of flood data and alerts",
            "**Comprehensive API** - RESTful endpoints for all resources",
            "**Mobile Responsive** - Works seamlessly on all devices",
            "**Offline Capable** - Progressive enhancement for low-connectivity areas"
        ]

        return "## Features\n\n" + "\n".join(f"- {f}" for f in feature_list) + "\n"

    def _generate_tech_stack(self) -> str:
        """Generate tech stack table."""
        deps = self.data["dependencies"]["dependencies"]

        # Categorize dependencies
        categories = {
            "Web Framework": ["django", "djangorestframework", "channels", "daphne"],
            "Database & GIS": ["psycopg2-binary", "GDAL"],
            "Async & Tasks": ["celery", "django-celery-beat", "redis"],
            "ML & Data": ["numpy", "scipy", "scikit-learn", "joblib"],
            "Testing": ["pytest", "pytest-django", "factory-boy", "Faker"],
            "Utilities": ["requests", "python-decouple", "pillow"]
        }

        table = "| Category | Technologies |\n|----------|--------------|\n"
        for cat, packages in categories.items():
            pkgs = []
            for dep in deps:
                if dep["name"].lower() in [p.lower() for p in packages]:
                    version = dep.get("version", "")
                    pkgs.append(f"`{dep['name']}{version}`")
            if pkgs:
                table += f"| {cat} | {' '.join(pkgs)} |\n"

        return "## Tech Stack\n\n" + table + "\n"

    def _generate_architecture(self) -> str:
        """Generate architecture overview."""
        features = self.data["features"]
        arch_components = []

        if features.get("gis"):
            arch_components.append("**GeoDjango + PostGIS** - Spatial database with geometric queries")
        if features.get("websockets"):
            arch_components.append("**Django Channels** - WebSocket support for real-time communication")
        if features.get("celery_tasks"):
            arch_components.append("**Celery + Redis** - Distributed task queue for background processing")
        if features.get("ml_model"):
            arch_components.append("**scikit-learn ML Model** - Flood risk prediction engine")
        if features.get("real_time_alerts"):
            arch_components.append("**Alert Consumer** - Real-time notification system")

        components_str = "\n    ".join(f"        - {c}" for c in arch_components)

        return f"""## Architecture

FloodGuard follows a modern, scalable architecture:

{components_str}

**Models:** {', '.join(self.data['structure'].get('models', []))}

**API:** RESTful endpoints powered by Django REST Framework with token authentication.

**Frontend:** HTML5, CSS3, vanilla JavaScript with Leaflet.js for mapping.

---

"""

    def _generate_installation(self) -> str:
        """Generate installation instructions."""
        return """## Installation

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
source floodguard-env/bin/activate  # On Windows: floodguard-env\\Scripts\\activate

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

"""

    def _generate_usage(self) -> str:
        """Generate usage documentation."""
        return """## Usage

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

"""

    def _generate_api_docs(self) -> str:
        """Generate API documentation."""
        urls = self.data["structure"]["urls"]
        viewsets = self.data["structure"]["views"].get("viewsets", [])

        return f"""## API Reference

FloodGuard provides a comprehensive REST API at `/api/`

### Endpoints

| Endpoint | Method | Description | Access |
|----------|--------|-------------|--------|
| `/api/zones/` | GET | List all flood zones | Public |
| `/api/zones/{{id}}/` | GET | Zone details | Public |
| `/api/zones/{{id}}/override/` | POST | Manual override (Authority/Admin) | Restricted |
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
curl -X POST http://localhost:8000/api-token-auth/ \\
  -H "Content-Type: application/json" \\
  -d '{{"username": "user", "password": "pass"}}'

# Use token
curl -H "Authorization: Token YOUR_TOKEN" http://localhost:8000/api/zones/
```

---

## Dynamic GPS Zones

FloodGuard defaults map views to Nairobi. When a user grants browser geolocation permission, the frontend captures `latitude`, `longitude`, and optional `accuracy` with `navigator.geolocation.getCurrentPosition()`, then sends the values to `POST /api/v1/dynamic-zone/` as JSON.

The backend validates the coordinate range and configured `GEO_BOUNDS`, checks whether an existing `AlertZone` covers the point, and only creates or refreshes a dynamic zone when no mapped zone already applies. `GET /api/v1/dynamic-zone/?lat=...&lon=...` remains read-only for live assessment and does not mutate stored zones.

Example request:

```bash
curl -X POST http://localhost:8000/api/v1/dynamic-zone/ \\
  -H "Content-Type: application/json" \\
  -d '{{"lat": -1.287, "lon": 36.821, "accuracy": 45}}'
```

Privacy and security notes:
- Browser permission denial falls back to Nairobi and does not send GPS data.
- Dynamic zone creation is rate limited and bounded by `GEO_BOUNDS`.
- Exact GPS coordinates are sent only to the same-origin API; CSP already allows `connect-src 'self'`.
- `Permissions-Policy: geolocation=(self)` allows location access only for the FloodGuard origin.
- Use HTTPS in production, because browser geolocation is restricted to secure contexts.

---

"""

    def _generate_testing(self) -> str:
        """Generate testing documentation."""
        counts = self.data["code_metrics"]
        return f"""## Testing

FloodGuard has comprehensive test coverage with {counts.get('test_files', 0)} test files.

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
{self._list_test_files()}

---

"""

    def _list_test_files(self) -> str:
        """List test files from the tests directory."""
        test_dir = self.root / "tests"
        files = []
        for path in sorted(test_dir.rglob("test_*.py")):
            rel = path.relative_to(self.root)
            files.append(f"  - `{rel}`")
        return "\n".join(files) if files else "  (None found)"

    def _generate_deployment(self) -> str:
        """Generate deployment documentation."""
        docker_info = self.data["docker"]
        if isinstance(docker_info, dict) and docker_info.get("service_count"):
            services = ", ".join(docker_info["services"])
            return f"""## Deployment

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

"""
        else:
            return """## Deployment

See `docker-compose.yml` for container orchestration.

Manual deployment requires:
- PostgreSQL with PostGIS
- Redis server
- Gunicorn + Nginx
- Celery worker + beat processes

Refer to `docs/deployment.md` for detailed production setup.

---

"""

    def _generate_development(self) -> str:
        """Generate development workflow documentation."""
        return """## Development

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

"""

    def _generate_contributing(self) -> str:
        return """## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Reporting Issues

Report bugs and request features via GitHub Issues.

---

"""

    def _generate_license(self) -> str:
        return """## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

"""


def generate_readme(check_only: bool = False, output_path: Optional[Path] = None) -> int:
    """Generate README and optionally compare/write.

    Args:
        check_only: Only check if README would change (returns 1 if outdated)
        output_path: Path to write README (default: project root README.md)

    Returns:
        0 if up-to-date or written successfully, 1 if outdated (check-only)
    """
    if output_path is None:
        output_path = PROJECT_ROOT / "README.md"

    # Parse project
    parser = ProjectParser(PROJECT_ROOT)
    data = parser.parse_all()

    # Generate new content
    generator = ReadmeGenerator(data, PROJECT_ROOT)
    new_content = generator.generate()

    if check_only:
        if not output_path.exists():
            print("README.md does not exist - needs generation")
            return 1
        existing = output_path.read_text()
        if existing != new_content:
            print("README.md is outdated - needs regeneration")
            return 1
        print("README.md is up-to-date")
        return 0

    # Write new README
    output_path.write_text(new_content)
    print(f"README.md generated at {output_path}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Generate dynamic README.md from project structure"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if README is outdated (exit code 1 if so)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: PROJECT_ROOT/README.md)"
    )

    args = parser.parse_args()
    sys.exit(generate_readme(check_only=args.check, output_path=args.output))


if __name__ == "__main__":
    main()
