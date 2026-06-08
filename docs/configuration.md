# Configuration

## Django Settings

Settings are split across multiple files in `src/jasonstudio/settings/`:

| File | Purpose |
|------|---------|
| `base.py` | Shared settings (installed apps, middleware, templates, etc.) |
| `debug.py` | Local development (SQLite, DEBUG=True) |
| `ci.py` | CI testing (reads DATABASE_URL from `.env`) |
| `live.py` | Production (all secrets from env, HTTPS/HSTS enabled) |

The default `DJANGO_SETTINGS_MODULE` is `jasonstudio.settings.debug`.

### Media Files

Photos are stored using Django's media file handling. Configure `MEDIA_ROOT` and `MEDIA_URL` in settings:

```python
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"
```

For production, consider using `django-storages` with S3 or similar.

### Photographer Profile (Admin)

Configure invoice-related settings in the Django admin under **Photographer Profile**:

| Setting | Description |
|---------|-------------|
| business_name | Appears on invoice header |
| tax_rate | Percentage applied to invoice subtotal |
| payment_terms | e.g. "Due upon receipt", "Net 30" |
| payment_instructions | e.g. "E-transfer to studio@example.com" |
| invoice_notes | Terms & conditions shown on invoice |
| address | Business address on invoice header |

## Environment Variables

All secrets are read from a `.env` file in the project root via
[django-environ](https://django-environ.readthedocs.io/). Copy
`.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

| Variable | Required in | Description |
|----------|-------------|-------------|
| `DJANGO_SECRET_KEY` | debug, live | Django secret key. No default in debug/live -- must be set. |
| `DJANGO_SALT_KEY` | debug, live | Salt for Fernet field encryption. No default in debug/live -- must be set. |
| `DATABASE_URL` | ci, live | Database connection string (PostgreSQL or MySQL). |
| `DJANGO_ALLOWED_HOSTS` | live | Comma-separated allowed hosts. |

The CI settings provide safe defaults for `DJANGO_SECRET_KEY` and `DJANGO_SALT_KEY` so no
`.env` file is needed for the database connection URL (written by the CI workflow).

## Field Encryption

Sensitive personal data is encrypted at rest using
[django-fernet-encrypted-fields](https://github.com/jazzband/django-fernet-encrypted-fields).
Encryption is symmetric (AES via Fernet) and derived from `SECRET_KEY` + `SALT_KEY`.

### Encrypted fields

| Model | Field | Type |
|-------|-------|------|
| Customer | phone | EncryptedCharField |
| PhotographerProfile | phone | EncryptedCharField |
| PhotographerProfile | email | EncryptedEmailField |
| PhotographerProfile | address | EncryptedTextField |
| PhotographerProfile | payment_instructions | EncryptedTextField |
| Payment | reference | EncryptedCharField |

### Important notes

- Encrypted fields are stored as base64-encoded text. They **cannot** be filtered, searched,
  or ordered at the database level.
- Empty values are stored as `NULL` (not encrypted empty strings).
- Works with all database backends (SQLite, PostgreSQL, MySQL).

### Key rotation

To rotate `SALT_KEY`, convert it to a list with the new key first:

```python
SALT_KEY = [
    "new-salt-key",
    "old-salt-key",
]
```

New data is encrypted with the first key; decryption tries all keys in order.
Re-save existing records to re-encrypt with the new key.

For `SECRET_KEY` rotation (Django 4.1+), use `SECRET_KEY_FALLBACKS`:

```python
SECRET_KEY = "new-secret-key"
SECRET_KEY_FALLBACKS = ["old-secret-key"]
```

## Watermarking

Photos are watermarked on upload using Pillow. The watermark text is applied diagonally across the image. Two watermarked versions are generated:

1. **Thumbnail** (800px max width) — used in gallery browsing
2. **Full watermarked** — full resolution with watermark overlay

Originals are stored separately and only served via the download endpoint (after payment).

### Watermark Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `WATERMARK_TEXT` | Text overlaid on thumbnails and watermarked images | `"PROOF"` |
| `WATERMARK_OPACITY` | Transparency of the watermark, 0 (invisible) to 255 (solid white) | `64` |

Example:

```python
WATERMARK_TEXT = "PROOF"
WATERMARK_OPACITY = 75  # ~30% opacity
```

After changing these settings, use the **Regenerate Thumbnails** button on the upload page to re-process existing photos with the new watermark settings.

## Upload Settings

Uploads are sent from the browser in batches of 20 files via JavaScript `fetch()` to avoid hitting the OS file descriptor limit when uploading large shoots (400+ files). No special Django settings are required.
