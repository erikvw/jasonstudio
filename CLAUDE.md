# CLAUDE.md — jasonstudio

## Project overview

Photography studio management app built with Django 6 and Python 3.14.
Photographers create events, upload photos, prepare quotations, manage orders/invoices, and share galleries with customers.

## Stack

- **Framework**: Django 6.0.6
- **Python**: 3.14+
- **Package manager**: uv
- **Frontend**: Bootstrap 5, HTMX, Font Awesome
- **Image processing**: Pillow (watermarking, thumbnails, EXIF extraction)
- **Database**: SQLite (dev), MySQL (production)
- **Docs**: Sphinx with furo theme

## Project layout

```
jasonstudio/          # Django project settings
gallery/              # Main app: models, views, admin, urls
accounts/             # Customer account management
templates/gallery/    # Templates (incl. partials/)
static/               # Static assets
tests/                # pytest test suite
docs/                 # Sphinx documentation
```

## Common commands

```bash
# Run dev server
uv run python manage.py runserver

# Run tests
uv run --dev pytest

# Run a single test file
uv run --dev pytest tests/test_models.py -x

# Make migrations
uv run python manage.py makemigrations gallery

# Apply migrations
uv run python manage.py migrate

# Build docs
uv run --dev sphinx-build docs docs/_build/html

# Lint (no ruff config yet — use defaults)
uv run --dev ruff check .
```

## Test suite

- Uses **pytest** with **pytest-django** (not Django TestCase)
- Config in `pyproject.toml` under `[tool.pytest.ini_options]`
- `DJANGO_SETTINGS_MODULE = "jasonstudio.settings"`
- Fixtures in `tests/conftest.py`: `photographer_user`, `customer_user`, `customer`, `event`, `photos`, `order`, `paid_order`
- Test files: `test_models.py`, `test_views.py`, `test_build_invoice.py`, `test_accounts.py`, `test_quotation.py`

## Key models (gallery/models.py)

- **Event**: photo shoot with status (draft/published/archived), linked to customers
- **Photo**: original + watermarked + thumbnail, EXIF metadata
- **Selection**: customer picks (digital/print/reject) per photo, optional PrintSize
- **Service**: reusable service catalog (per hour, per image, per km, flat, each)
- **Quotation / QuotationLineItem**: quote from service catalog, auto-generates Order on accept
- **Order**: linked to event + customer, optional quotation FK, deposit_amount
- **Invoice / InvoiceLineItem**: auto-built from order selections, deposit reduces amount_due
- **Payment**: recorded against an invoice
- **ShareLink**: time-limited gallery access codes

## Key patterns

- `_build_invoice(order)` in views.py creates/updates Invoice + line items from order selections
- `_build_quotation_totals(quotation)` recalculates quote subtotal/tax/total
- `Quotation.accept(by)` auto-creates an Order with hours/rate/deposit pre-filled
- Chunked uploads: JS sends files in batches of 20 via fetch() to avoid file descriptor limits
- Tax is calculated on full subtotal (not reduced by deposit)
- `amount_due = subtotal - deposit + tax`

## Django conventions

- Do not assume empty CharField is `""` — it may be `None`
- Never use `fields = "__all__"` on user-facing ModelForms
- System audit fields (created, modified, user_created, etc.) are never shown to users
- `PhotographerProfile` stores tax_rate and payment terms; accessed via `request.user.photographerprofile`
- `WATERMARK_TEXT` — watermark overlay text (default: `"PROOF"`)
- `WATERMARK_OPACITY` — watermark transparency, 0 (invisible) to 255 (solid) (default: `64`)
- `DATA_UPLOAD_MAX_NUMBER_FILES = 500` in settings for bulk uploads

## Git workflow

- Never push directly to `develop` or `main`
- Create a feature branch and open a PR: `gh pr create --base develop --fill`

## Code standards

- Type hints on all function signatures
- All code should pass ruff checks
