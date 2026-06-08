from .base import *  # noqa: F401, F403
from .base import env

SECRET_KEY = env("DJANGO_SECRET_KEY", default="ci-test-secret-key-not-for-production")

DEBUG = False

ALLOWED_HOSTS: list[str] = ["localhost", "127.0.0.1"]

# --- Database (from DATABASE_URL) ---

DATABASES = {"default": env.db("DATABASE_URL")}
