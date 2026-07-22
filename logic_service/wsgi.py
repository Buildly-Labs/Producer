"""
WSGI config for logic_service project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/2.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

if "DJANGO_SETTINGS_MODULE" not in os.environ:
	running_in_docker = os.getenv("RUNNING_IN_DOCKER", "").lower() in ("1", "true", "yes")
	default_settings = "logic_service.settings.docker" if running_in_docker else "logic_service.settings.production"
	os.environ.setdefault("DJANGO_SETTINGS_MODULE", default_settings)

application = get_wsgi_application()
