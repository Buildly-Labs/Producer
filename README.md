# Producer — Podcast & Media Production Platform

A Django application for managing shows, episodes, transcripts, media assets, AI-assisted content generation, and publishing workflows. Part of the Buildly Foundry ecosystem.

## Quick Start (Docker — recommended)

Producer runs as part of the ForgeMarketing multi-service container. From the repo root:

```bash
git clone --recurse-submodules https://github.com/Buildly-Marketplace/ForgeMarketing.git
cd ForgeMarketing
docker build -t forgemarketing .
docker run -p 8080:8080 forgemarketing
```

Then open **http://localhost:8080/producer/**

### Default Login

| Field    | Value                |
|----------|----------------------|
| Email    | `admin@example.com`  |
| Password | `changeme123`        |

The default admin is created automatically on first startup.  
Override with environment variables:

| Variable                  | Default              |
|---------------------------|----------------------|
| `PRODUCER_ADMIN_EMAIL`    | `admin@example.com`  |
| `PRODUCER_ADMIN_PASSWORD` | `changeme123`        |

Django admin is available at **/producer/admin/**.

## Architecture

Producer is one of three services behind a shared nginx reverse proxy:

| Service        | Internal Port | URL Path       |
|----------------|---------------|----------------|
| Gateway        | 5000          | `/`            |
| Marketing Hub  | 8002          | `/marketing/`  |
| **Producer**   | 8001          | `/producer/`   |

Nginx listens on port **8080** and routes requests. All three services run under supervisord in a single Docker container.

### Startup Sequence

1. `python manage.py migrate --no-input` — apply database migrations
2. `python manage.py loadinitialdata` — create default admin user and seed episode types
3. `gunicorn -b 127.0.0.1:8001 -w 2 --timeout 120 logic_service.wsgi` — start the app

### Key Settings (Docker)

| Setting               | Value                             |
|-----------------------|-----------------------------------|
| `DJANGO_SETTINGS_MODULE` | `logic_service.settings.docker` |
| `FORCE_SCRIPT_NAME`  | `/producer`                       |
| `STATIC_URL`          | `/producer/static/`              |
| `DATABASE`            | SQLite (default) or PostgreSQL    |
| `ALLOWED_HOSTS`       | `['*']`                           |
| `CSRF_TRUSTED_ORIGINS`| `['https://*.ondigitalocean.app']`|

## Features

- **Shows & Episodes** — Create podcast series, plan episodes with segments, guest prep, and run-of-show
- **Guest Management** — Contact details, consent tracking, quote approval workflows
- **Media Assets** — Upload/link audio and video with SHA256 checksums and chain-of-custody tracking
- **Transcripts** — Versioned transcripts with confidence scoring
- **Clip Moments** — Mark and tag moments for social-ready clips
- **AI Artifacts** — AI-generated drafts (show notes, social posts) with full provenance tracking and approval gates
- **Show Notes** — Draft → approve → finalize workflow
- **Export** — JSON, Markdown, CSV clips, guest briefs, full episode packages
- **Pre-Publish Checklists** — Required gate items before episodes go live
- **Control Room** — Live studio mode for recording sessions
- **RBAC** — Role-based access per show (Host, Producer, Editor, Guest Coordinator, Researcher, Reviewer)
- **Multi-Tenant** — All models scoped to `organization_uuid`
- **REST API** — Full DRF-powered API at `/producer/api/` with Swagger docs at `/producer/docs/`

## URL Structure

| Path                                    | Description                    |
|-----------------------------------------|--------------------------------|
| `/producer/`                            | Landing page                   |
| `/producer/auth/login/`                 | Login                          |
| `/producer/auth/logout/`                | Logout                         |
| `/producer/admin/`                      | Django admin                   |
| `/producer/ledger/`                     | Dashboard                      |
| `/producer/ledger/shows/`              | Show list                      |
| `/producer/ledger/shows/create/`       | Create show                    |
| `/producer/ledger/shows/<id>/`         | Show detail                    |
| `/producer/ledger/episodes/<id>/`      | Episode detail (tabbed UI)     |
| `/producer/api/`                        | REST API root                  |
| `/producer/docs/`                       | Swagger API docs               |

## Local Development (without Docker)

```bash
cd Producer
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py loadinitialdata
python manage.py runserver 0.0.0.0:8001
```

Note: Without the nginx proxy, access the app directly at `http://localhost:8001/`.
Set `FORCE_SCRIPT_NAME=""` if running standalone.

### Environment Variables

| Variable              | Description                      | Default                    |
|-----------------------|----------------------------------|----------------------------|
| `DJANGO_SETTINGS_MODULE` | Settings module to use        | `logic_service.settings.docker` |
| `DATABASE_ENGINE`     | `postgresql` or blank for SQLite | (blank → SQLite)           |
| `DATABASE_NAME`       | Database name                    | `logic_service`            |
| `DATABASE_USER`       | Database user                    | `root`                     |
| `DATABASE_PASSWORD`   | Database password                | `root`                     |
| `DATABASE_HOST`       | Database host                    | `localhost`                |
| `DATABASE_PORT`       | Database port                    | `5432`                     |
| `PRODUCER_ADMIN_EMAIL`| Seed admin email                 | `admin@example.com`        |
| `PRODUCER_ADMIN_PASSWORD`| Seed admin password           | `changeme123`              |
| `SECRET_KEY`          | Django secret key                | (hardcoded dev default)    |
| `ALLOWED_HOSTS`       | Comma-separated hosts            | `*` (docker)               |
| `FORCE_SCRIPT_NAME`   | URL prefix behind proxy          | `/producer`                |
| `STATIC_URL`          | Static files URL path            | `/producer/static/`        |

## Data Models

| Model             | Purpose                                              |
|-------------------|------------------------------------------------------|
| Show              | Podcast series / brand                               |
| EpisodeType       | Categorization (Interview, Deep Dive, News, etc.)    |
| Episode           | Single episode with status workflow                  |
| Segment           | Run-of-show segment within an episode                |
| Guest             | Reusable guest/expert profile                        |
| EpisodeGuest      | Guest appearance on a specific episode               |
| MediaAsset        | Audio/video files with integrity tracking            |
| Transcript        | Versioned episode transcripts                        |
| ClipMoment        | Tagged moments for social clips                      |
| AIArtifact        | AI-generated content with provenance and approval    |
| ShowNoteDraft     | Draft show notes (potentially AI-generated)          |
| ShowNoteFinal     | Approved, finalized show notes                       |
| ChecklistItem     | Pre-publish gate items                               |
| ExportRecord      | Track generated export files                         |
| ShowRoleAssignment| User role on a show (RBAC)                          |
| EpisodeRoleOverride| Per-episode role override                           |

## Dependencies

- Django 5.1.x
- Django REST Framework 3.15
- drf-yasg (Swagger/OpenAPI)
- django-filter
- django-cors-headers
- django-allauth
- django-import-export
- gunicorn
- psycopg2-binary (PostgreSQL adapter)

## License

GPL v3 — see [LICENSE.md](LICENSE.md)

* Hat tip to anyone whose code was used
* Inspiration
* etc
