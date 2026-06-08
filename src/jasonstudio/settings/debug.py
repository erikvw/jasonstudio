from .base import *  # noqa: F401, F403
from .base import BASE_DIR, PACKAGE_DIR, env

SECRET_KEY = env("DJANGO_SECRET_KEY")
SALT_KEY = env("DJANGO_SALT_KEY")

DEBUG = True

ALLOWED_HOSTS: list[str] = ["localhost", "127.0.0.1"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

STATICFILES_DIRS = [PACKAGE_DIR / "static"]
