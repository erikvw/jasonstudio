# Configuration

## Django Settings

The app uses standard Django settings in `jasonstudio/settings.py`.

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

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Django secret key | (dev key in settings) |
| `DEBUG` | Enable debug mode | `True` |
| `ALLOWED_HOSTS` | Comma-separated hosts | `[]` |

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
