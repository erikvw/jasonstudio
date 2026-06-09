[![pypi](https://img.shields.io/pypi/v/jasonstudio.svg)](https://pypi.python.org/pypi/jasonstudio)
[![actions](https://github.com/erikvw/jasonstudio/actions/workflows/ci.yml/badge.svg)](https://github.com/erikvw/jasonstudio/actions/workflows/ci.yml)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

# jasonstudio

A simple photography studio management application built with Django.

Documentation: [jasonstudio.readthedocs.io](https://jasonstudio.readthedocs.io)

## Quickstart

```bash
git clone https://github.com/erikvw/jasonstudio.git
cd jasonstudio
uv sync --dev
cp .env.example .env
# Edit .env — set DJANGO_SECRET_KEY and DJANGO_SALT_KEY
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

## Running tests

```bash
uv run --dev pytest
```
