from .base import *  # noqa: F401, F403
from .base import BASE_DIR, env

SECRET_KEY = env("DJANGO_SECRET_KEY")
SALT_KEY = env("DJANGO_SALT_KEY")

DEBUG = False

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

# --- Database ---
# Set DATABASE_URL in .env:
#   postgres://user:pass@host:5432/jasonstudio
#   mysql://user:pass@host:3306/jasonstudio

DATABASES = {"default": env.db("DATABASE_URL")}

# --- Static files (collected for nginx) ---

STATIC_ROOT = BASE_DIR / "staticfiles"

# --- HTTPS / Security (behind nginx) ---

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_HSTS_SECONDS = 31_536_000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SECURE_CONTENT_TYPE_NOSNIFF = True
