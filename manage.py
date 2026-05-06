#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    if "DJANGO_SETTINGS_MODULE" not in os.environ:
        running_in_docker = os.getenv("RUNNING_IN_DOCKER", "").lower() in ("1", "true", "yes")
        default_settings = "logic_service.settings.docker" if running_in_docker else "logic_service.settings.dev"
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", default_settings)
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)
