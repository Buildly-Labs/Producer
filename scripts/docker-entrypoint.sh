#!/usr/bin/env bash

set -e

# Keep management commands and Gunicorn on the same settings module.
# If not explicitly provided by the environment, default to production.
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-logic_service.settings.production}"

echo $(date -u) "- Using settings: ${DJANGO_SETTINGS_MODULE}"

echo $(date -u) "- Migrating"
python manage.py makemigrations
python manage.py migrate

echo $(date -u) "- Load Initial Data"
python manage.py loadinitialdata

# export env variable from file
if [ -e /JWT_PRIVATE_KEY_RSA_BUILDLY ]
then
  export JWT_PRIVATE_KEY_RSA_BUILDLY=`cat /JWT_PRIVATE_KEY_RSA_BUILDLY`
fi

if [ -e /JWT_PUBLIC_KEY_RSA_BUILDLY ]
then
  export JWT_PUBLIC_KEY_RSA_BUILDLY=`cat /JWT_PUBLIC_KEY_RSA_BUILDLY`
fi

echo $(date -u) "- Collect Static"
python manage.py collectstatic --no-input

echo $(date -u) "- Running the server"
gunicorn -b 0.0.0.0:8080 --config logic_service/gunicorn_conf.py logic_service.wsgi
