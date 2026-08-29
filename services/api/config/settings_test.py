from .settings_common import *  # noqa: F403


SECRET_KEY = "splitbind-obvious-fixed-test-key-not-for-production"
ENVIRONMENT = "test"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
