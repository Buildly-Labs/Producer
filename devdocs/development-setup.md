# Development Setup Guide

## Prerequisites

Before setting up the Logic Service for development, ensure you have the following installed:

### Required Software
- **Docker**: Version 20.0 or higher
- **Docker Compose**: Version 1.29 or higher
- **Git**: For version control
- **Code Editor**: VS Code recommended with Python extension

### Optional but Recommended
- **Python 3.11+**: For local development without Docker
- **PostgreSQL**: For local database development
- **Postman or similar**: For API testing

## Quick Start with Docker

### 1. Clone the Repository
```bash
git clone https://github.com/buildly-marketplace/logic_service.git
cd logic_service
```

### 2. Build and Run the Service
```bash
# Build the Docker image
docker-compose -f docker-compose.dev.yml build

# Start the service
docker-compose -f docker-compose.dev.yml up
```

### 3. Access the Service
- **API**: http://localhost:8080
- **Admin Panel**: http://localhost:8080/admin (admin/admin)
- **API Documentation**: http://localhost:8080/docs/

## Local Development Setup (without Docker)

### 1. Python Environment Setup
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Linux/Mac:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements-dev.txt
```

### 2. Database Setup
```bash
# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Load sample data (if available)
python manage.py loaddata fixtures/sample_data.json
```

### 3. Run Development Server
```bash
python manage.py runserver 0.0.0.0:8000
```

## Development Workflow

### 1. Environment Configuration
Create a `.env` file in the project root:
```bash
# Development settings
DEBUG=True
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0

# Database settings (for local PostgreSQL)
DB_NAME=logic_service_dev
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432
```

### 2. Code Organization
```
logic_service/
├── logic/                  # Main application
│   ├── models.py          # Data models
│   ├── serializers.py     # API serializers
│   ├── views.py           # API views
│   ├── admin.py           # Django admin
│   ├── urls.py            # URL routing
│   └── tests/             # Unit tests
├── logic_service/         # Django project
│   ├── settings/          # Environment settings
│   │   ├── base.py       # Base settings
│   │   ├── dev.py        # Development settings
│   │   └── production.py # Production settings
│   └── urls.py           # Main URL configuration
└── scripts/              # Utility scripts
```

### 3. Running Tests
```bash
# Run all tests
python manage.py test

# Run with coverage
coverage run --source='.' manage.py test
coverage report
coverage html  # Generate HTML coverage report

# Run tests in Docker
docker-compose -f docker-compose.dev.yml run --rm --entrypoint 'bash scripts/run-tests.sh' logic_service
```

### 4. Database Migrations
```bash
# Create new migration
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Check migration status
python manage.py showmigrations
```

## Development Tools and Utilities

### 1. Code Formatting and Linting
```bash
# Install development tools
pip install black flake8 isort

# Format code
black .

# Sort imports
isort .

# Check code quality
flake8 .
```

### 2. API Testing
```bash
# Install HTTPie for API testing
pip install httpie

# Test API endpoints
http GET http://localhost:8000/api/v1/entities/
http POST http://localhost:8000/api/v1/entities/ name="Test Entity" description="Test"
```

### 3. Database Management
```bash
# Access Django shell
python manage.py shell

# Create database backup
python manage.py dumpdata > backup.json

# Load data from backup
python manage.py loaddata backup.json

# Reset database
python manage.py flush
```

## Docker Development Commands

### Common Docker Operations
```bash
# Build services
docker-compose -f docker-compose.dev.yml build

# Start services in background
docker-compose -f docker-compose.dev.yml up -d

# View logs
docker-compose -f docker-compose.dev.yml logs -f

# Stop services
docker-compose -f docker-compose.dev.yml down

# Remove volumes (reset database)
docker-compose -f docker-compose.dev.yml down -v
```

### Debugging in Docker
```bash
# Access container shell
docker-compose -f docker-compose.dev.yml exec web bash

# Run management commands in container
docker-compose -f docker-compose.dev.yml exec web python manage.py migrate
docker-compose -f docker-compose.dev.yml exec web python manage.py createsuperuser
```

## IDE Configuration

### VS Code Setup
Create `.vscode/settings.json`:
```json
{
    "python.defaultInterpreterPath": "./venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "python.formatting.provider": "black",
    "python.sortImports.args": ["--profile", "black"],
    "[python]": {
        "editor.formatOnSave": true,
        "editor.codeActionsOnSave": {
            "source.organizeImports": true
        }
    }
}
```

### Recommended VS Code Extensions
- Python
- Django
- REST Client
- Docker
- GitLens
- Python Docstring Generator

## Environment Variables

### Development Environment
```bash
# Django settings
DJANGO_SETTINGS_MODULE=logic_service.settings.dev
DEBUG=True
SECRET_KEY=development-secret-key

# Database
DB_ENGINE=django.db.backends.sqlite3
DB_NAME=db.sqlite3

# CORS (allow all origins in development)
CORS_ALLOW_ALL_ORIGINS=True

# Logging
LOG_LEVEL=DEBUG
```

### Testing Environment
```bash
# Use in-memory database for faster tests
DB_ENGINE=django.db.backends.sqlite3
DB_NAME=:memory:

# Disable migrations for faster tests
DJANGO_SETTINGS_MODULE=logic_service.settings.test
```

## Troubleshooting

### Common Issues and Solutions

1. **Port Already in Use**
   ```bash
   # Find process using port 8000
   lsof -i :8000
   # Kill the process
   kill -9 <PID>
   ```

2. **Database Connection Issues**
   ```bash
   # Reset database in Docker
   docker-compose down -v
   docker-compose up --build
   ```

3. **Permission Errors in Docker**
   ```bash
   # Fix file permissions
   sudo chown -R $USER:$USER .
   ```

4. **Python Package Issues**
   ```bash
   # Clear pip cache
   pip cache purge
   # Reinstall requirements
   pip install -r requirements-dev.txt --force-reinstall
   ```

## Performance Optimization

### Development Performance Tips
1. **Use SQLite for development** - Faster than PostgreSQL for local dev
2. **Enable Django debug toolbar** - Monitor query performance
3. **Use select_related/prefetch_related** - Optimize database queries
4. **Cache API responses** - Reduce database load during testing

### Debugging Performance
```python
# Add to settings/dev.py
INSTALLED_APPS += ['debug_toolbar']
MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
INTERNAL_IPS = ['127.0.0.1', '0.0.0.0']

# Monitor database queries
import logging
logging.getLogger('django.db.backends').setLevel(logging.DEBUG)
```

## Development Best Practices

1. **Write tests first** - Follow TDD principles
2. **Use meaningful commit messages** - Follow conventional commits
3. **Keep branches focused** - One feature per branch
4. **Review code regularly** - Use pull requests for all changes
5. **Document as you code** - Update documentation with changes
6. **Monitor performance** - Regular performance testing
7. **Security first** - Regular dependency updates

## Getting Help

- **Documentation**: Check the `/devdocs` folder
- **Issues**: Create GitHub issues for bugs
- **Community**: Join the Buildly Slack community
- **Email**: team@buildly.io

## Next Steps

After setup:
1. Read the [Architecture Guide](./architecture.md)
2. Review [API Guidelines](./api-guidelines.md)  
3. Check the [Testing Guide](./testing-guide.md)
4. Explore the existing codebase
5. Start contributing!