# FloodGuard

A real-time flood monitoring and early warning system built with Django, PostGIS, and modern web technologies.

## Features

- Real-time flood risk assessment using machine learning
- Interactive maps with Leaflet.js
- WebSocket-powered live alerts
- Citizen reporting system
- Emergency team dashboard
- Admin panel for system management
- RESTful API with Django REST Framework
- GIS-enabled database with PostGIS

## Prerequisites

- Python 3.11+
- PostgreSQL 15+ with PostGIS extension
- Redis server
- Node.js (for frontend assets, if applicable)

## Local Development Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd FloodGuard
```

### 2. Create Virtual Environment

```bash
python -m venv floodguard_env
source floodguard_env/bin/activate  # On Windows: floodguard_env\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Environment Configuration

Create a `.env` file in the project root:

```bash
SECRET_KEY=django-insecure-please-change-this-in-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,testserver

# Database Configuration
DB_NAME=floodguard
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379

# Africa's Talking SMS (for production)
AFRICASTALKING_USERNAME=your_username
AFRICASTALKING_API_KEY=your_api_key
```

### 5. Database Setup

#### Install and Configure PostgreSQL

```bash
# Update package list
sudo apt update

# Install PostgreSQL and PostGIS
sudo apt install postgresql postgresql-contrib postgis postgresql-18-postgis-3

# Start PostgreSQL service
sudo systemctl start postgresql

# Enable PostgreSQL to start on boot
sudo systemctl enable postgresql
```

#### Create Database and User

```bash
# Switch to postgres user
sudo -u postgres psql

# In PostgreSQL shell:
CREATE DATABASE floodguard;
CREATE USER floodguard_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE floodguard TO floodguard_user;
ALTER USER floodguard_user CREATEDB;
\q
```

#### Enable PostGIS Extension

```bash
# Connect to your database
sudo -u postgres psql -d floodguard

# Enable PostGIS
CREATE EXTENSION postgis;
SELECT PostGIS_version();
\q
```

### 6. Redis Setup

```bash
# Install Redis
sudo apt install redis-server

# Start Redis service
sudo systemctl start redis-server

# Enable Redis to start on boot
sudo systemctl enable redis-server

# Verify Redis is running
redis-cli ping
```

### 7. Django Setup

```bash
# Run database migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Collect static files
python manage.py collectstatic --noinput
```

### 8. Load Initial Data (Optional)

```bash
# Create emergency team group
python manage.py shell -c "
from django.contrib.auth.models import Group
Group.objects.get_or_create(name='EmergencyTeam')
print('Emergency team group created')
"
```

### 9. Run Development Server

```bash
# Start Django development server
python manage.py runserver

# The application will be available at http://127.0.0.1:8000/
```

### 10. Access the Application

- **Landing Page**: http://127.0.0.1:8000/
- **Admin Panel**: http://127.0.0.1:8000/admin/
- **API Documentation**: http://127.0.0.1:8000/api/v1/

## Troubleshooting

### PostgreSQL Connection Issues

```bash
# Check PostgreSQL service status
sudo systemctl status postgresql

# Check if PostgreSQL is listening on port 5432
sudo netstat -tlnp | grep 5432

# Check PostgreSQL configuration
sudo cat /etc/postgresql/18/main/postgresql.conf | grep -E "(listen_addresses|port)"

# Test database connection
psql -h localhost -p 5432 -U postgres -d floodguard

# List all databases
sudo -u postgres psql -c "\l"
```

### Redis Connection Issues

```bash
# Check Redis service status
sudo systemctl status redis-server

# Test Redis connection
redis-cli ping
```

### Django Issues

```bash
# Check Django settings
python manage.py check

# Test database connection
python manage.py dbshell

# View applied migrations
python manage.py showmigrations

# Run specific migration if needed
python manage.py migrate core
```

## Project Structure

```
FloodGuard/
├── core/                    # Main application
│   ├── models.py           # Database models
│   ├── views.py            # View functions
│   ├── urls.py             # URL routing
│   ├── serializers.py      # API serializers
│   ├── permissions.py      # Custom permissions
│   ├── tasks.py            # Celery tasks
│   ├── analytics/          # ML and analytics
│   └── consumers.py        # WebSocket consumers
├── templates/              # HTML templates
├── static/                 # Static files (CSS, JS)
├── tests/                  # Test suite
├── floodguard/             # Project configuration
│   ├── settings.py         # Django settings
│   ├── urls.py             # Main URL configuration
│   └── routing.py          # WebSocket routing
├── requirements.txt        # Python dependencies
├── pytest.ini             # Test configuration
└── .env                   # Environment variables
```

## API Endpoints

### Zones API
- `GET /api/v1/zones/` - List all flood zones
- `POST /api/v1/zones/` - Create new zone (admin only)
- `GET /api/v1/zones/{id}/` - Zone details

### Readings API
- `GET /api/v1/readings/` - List flood readings
- `POST /api/v1/readings/` - Create reading (admin only)

### Reports API
- `GET /api/v1/reports/` - List citizen reports
- `POST /api/v1/reports/` - Submit new report

### Alerts API
- `GET /api/v1/alerts/` - List alert history

## Development Commands

```bash
# Run tests
pytest

# Run specific test file
pytest tests/integration/test_celery.py

# Run with coverage
pytest --cov=core --cov-report=html

# Format code
black .
isort .

# Lint code
flake8 .
```

## Deployment

For production deployment, see the deployment documentation.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support, please open an issue on GitHub or contact the development team.