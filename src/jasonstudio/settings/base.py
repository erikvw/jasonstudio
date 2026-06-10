from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
PACKAGE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_htmx",
    "simple_history",
    "jasonstudio.accounts",
    "jasonstudio.gallery",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
]

ROOT_URLCONF = "jasonstudio.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [PACKAGE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "jasonstudio.accounts.context_processors.user_role",
            ],
        },
    },
]

WSGI_APPLICATION = "jasonstudio.wsgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
LOGIN_URL = "/accounts/login/"

WATERMARK_TEXT = "PROOF"
WATERMARK_OPACITY = 75

# Customer delivery method: "drive" (Google Drive link) or "email" (token-based link)
# "drive" shows Upload to Drive + mailto with Drive link.
# "email" shows the server-hosted token-based download email flow.
CUSTOMER_DELIVERY_METHOD = env("CUSTOMER_DELIVERY_METHOD", default="drive")

# Google Drive integration (for sharing download zips with customers)
# See docs/google_drive_setup.md for setup instructions.
# OAuth2 (personal Gmail) — set CLIENT_SECRETS_FILE
GOOGLE_DRIVE_CLIENT_SECRETS_FILE = env("GOOGLE_DRIVE_CLIENT_SECRETS_FILE", default="")
GOOGLE_DRIVE_TOKEN_FILE = env("GOOGLE_DRIVE_TOKEN_FILE", default="")
# Service account (Google Workspace + Shared Drives) — set CREDENTIALS_FILE
GOOGLE_DRIVE_CREDENTIALS_FILE = env("GOOGLE_DRIVE_CREDENTIALS_FILE", default="")
# Required for both modes
GOOGLE_DRIVE_FOLDER_ID = env("GOOGLE_DRIVE_FOLDER_ID", default="")
