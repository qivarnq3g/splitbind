#!/bin/sh
set -eu

if [ "${SPLITBIND_RELEASE_MODE:-}" != "integrity_v1" ]; then
    echo "INTEGRITY_RELEASE_MODE_REQUIRED" >&2
    exit 78
fi

exec python manage.py migrate --noinput
