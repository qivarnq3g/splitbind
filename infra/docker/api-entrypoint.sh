#!/bin/sh
set -eu

if [ "${SPLITBIND_RELEASE_MODE:-}" != "integrity_v1" ]; then
    echo "INTEGRITY_RELEASE_MODE_REQUIRED" >&2
    exit 78
fi

exec python -m gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --threads 2 \
    --timeout 90 \
    --graceful-timeout 30 \
    --access-logfile - \
    --error-logfile -
