# Getting Started

## Requirements

- Python 3.14+
- uv (package manager)

## Installation

```bash
git clone https://github.com/yourorg/jasonstudio.git
cd jasonstudio
uv sync --dev
```

## Database Setup

```bash
uv run python manage.py migrate
uv run python manage.py createsuperuser
```

## Initial Configuration

### 1. Photographer Profile

1. Log in to the Django admin at `/admin/`
2. Create a **Photographer Profile** linked to your superuser account
3. Set your business name, tax rate, payment terms, and payment instructions

### 2. Service Catalog

Set up your reusable services at `/photographer/services/`:

| Service | Unit Type | Rate |
|---------|-----------|------|
| Photography | Per Hour | $150.00 |
| Image Processing | Per Image | $2.00 |
| Travel | Per Km | $0.55 |
| Gallery Hosting | Flat Fee | $50.00 |

These appear as quick-add buttons when creating quotations.

### 3. Customers

Add customers at `/photographer/customers/`. Each customer gets a Django user account for logging in to view galleries and accept quotes.

## Typical Workflow

1. **Create services** in the catalog (one-time setup)
2. **Add a customer** and **create an event**
3. **Prepare a quotation** from the service catalog
4. Customer **accepts the quote** → Order is auto-created
5. **Upload photos** to the event after the shoot
6. Customer **makes selections** (digital, print, reject)
7. **Generate invoice** and **record payment**
8. Customer **downloads** digital photos (30-day window)

## Running the Server

```bash
uv run python manage.py runserver
```

## Running Tests

```bash
uv run --dev pytest
```

## Building Documentation

```bash
uv run --dev sphinx-build docs docs/_build/html
```
