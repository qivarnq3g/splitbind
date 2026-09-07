#!/bin/sh
set -eu

if [ "${SPLITBIND_RELEASE_MODE:-}" != "integrity_v1" ]; then
    echo "INTEGRITY_RELEASE_MODE_REQUIRED" >&2
    exit 78
fi
if [ "${WORKER_CONCURRENCY:-}" != "1" ]; then
    echo "INTEGRITY_WORKER_CONCURRENCY_INVALID" >&2
    exit 78
fi
if [ ! -r "${SPLITBIND_MANIFEST_SIGNING_KEY_FILE:-}" ]; then
    echo "INTEGRITY_SIGNING_KEY_UNREADABLE" >&2
    exit 78
fi
if [ ! -r "${SPLITBIND_MANIFEST_SIGNING_KEY_PASSPHRASE_FILE:-}" ]; then
    echo "INTEGRITY_SIGNING_KEY_PASSPHRASE_UNREADABLE" >&2
    exit 78
fi

exec python manage.py run_integrity_worker --poll-interval 1
