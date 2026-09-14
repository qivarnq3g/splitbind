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
if [ "${SPLITBIND_FINGERPRINT_ENABLED:-false}" = "true" ]; then
    key="${SPLITBIND_DEMO_FINGERPRINT_KEY_HEX:-}"
    if [ ${#key} -ne 64 ]; then
        echo "INTEGRITY_FINGERPRINT_KEY_INVALID" >&2
        exit 78
    fi
    case "$key" in
        *[!0-9a-f]*)
            echo "INTEGRITY_FINGERPRINT_KEY_INVALID" >&2
            exit 78
            ;;
    esac
fi

exec python manage.py run_integrity_worker --poll-interval 1
