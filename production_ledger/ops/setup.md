# Setup Guide

## Prerequisites

- Python 3.10+
- Django 5.1+
- PostgreSQL (recommended) or SQLite for development
- The host Buildly/Producer project running

## Installation

The `production_ledger` app is already integrated into the Producer project. No additional installation steps are needed.

### Database Migrations

```bash
# Generate migrations (if models changed)
python manage.py makemigrations production_ledger

# Apply migrations
python manage.py migrate
```

### Initial Data

Load sample data for testing:

```bash
python manage.py loaddata production_ledger/fixtures/sample_data.json
```

## Configuration

### Required Settings

The app is automatically added to `INSTALLED_APPS` in `logic_service/settings/base.py`:

```python
INSTALLED_APPS_LOCAL = [
    'logic',
    'production_ledger',  # Podcast/media production ledger
]
```

### URL Configuration

Routes are configured in `logic_service/urls.py`:

- UI routes: `/ledger/`
- API routes: `/api/ledger/`

### AI Provider Configuration

Set the AI provider in your environment:

```bash
# Use mock provider (default, no external dependencies)
export AI_PROVIDER=mock

# Future: Use OpenAI (requires OPENAI_API_KEY)
# export AI_PROVIDER=openai
# export OPENAI_API_KEY=sk-...
```

## Verification

After setup, verify the installation:

1. Run the development server:
   ```bash
   python manage.py runserver
   ```

2. Access the dashboard:
   - http://localhost:8000/ledger/

3. Check the API docs:
   - http://localhost:8000/docs/

4. Run tests:
   ```bash
   python manage.py test production_ledger
   ```

## Docker Setup

If using Docker, the app is automatically included in the container. No additional configuration needed.

```bash
docker-compose up -d
docker-compose exec web python manage.py migrate
```
