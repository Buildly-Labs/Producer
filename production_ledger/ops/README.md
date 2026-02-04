# Production Ledger Ops Documentation

This folder contains operational documentation for the `production_ledger` Django app.

## Contents

- [setup.md](setup.md) - Installation and initial setup
- [env.md](env.md) - Environment variables and configuration
- [usage.md](usage.md) - Day-to-day usage guide
- [security.md](security.md) - Security considerations and RBAC

## Quick Start

```bash
# 1. Apply migrations
python manage.py migrate

# 2. Load sample fixtures (optional)
python manage.py loaddata production_ledger/fixtures/sample_data.json

# 3. Access the app
# UI: http://localhost:8000/ledger/
# API: http://localhost:8000/api/ledger/
```
