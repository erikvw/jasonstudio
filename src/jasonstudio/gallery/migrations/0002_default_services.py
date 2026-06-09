"""Populate the Service catalog with sensible defaults."""

import uuid

from django.db import migrations

DEFAULT_SERVICES = [
    {
        "name": "Photography",
        "description": "On-location or studio photography session.",
        "unit_type": "per_hour",
        "sort_order": 0,
    },
    {
        "name": "Post-processing",
        "description": "Colour correction, retouching, and export of final images.",
        "unit_type": "per_image",
        "sort_order": 1,
    },
    {
        "name": "Online gallery hosting (30 days)",
        "description": "Private online gallery for viewing and selecting photos, hosted for 30 days.",
        "unit_type": "flat",
        "sort_order": 2,
    },
    {
        "name": "Travel",
        "description": "Mileage to and from the shoot location.",
        "unit_type": "per_km",
        "sort_order": 3,
    },
    {
        "name": "Second photographer",
        "description": "Additional photographer for the session.",
        "unit_type": "per_hour",
        "sort_order": 4,
    },
    {
        "name": "Prints",
        "description": "Professional lab prints in the selected size.",
        "unit_type": "each",
        "sort_order": 5,
    },
    {
        "name": "Rush delivery",
        "description": "Expedited turnaround for edited images within 48 hours.",
        "unit_type": "flat",
        "sort_order": 6,
    },
    {
        "name": "Rideshare transport",
        "description": "Uber, Lyft, or similar rideshare to and from the shoot location.",
        "unit_type": "flat",
        "sort_order": 7,
    },
    {
        "name": "Equipment rental",
        "description": "Speciality lighting, backdrop, or lens hire for the session.",
        "unit_type": "flat",
        "sort_order": 8,
    },
]


def create_default_services(apps, schema_editor):
    Service = apps.get_model("gallery", "Service")
    for svc in DEFAULT_SERVICES:
        Service.objects.get_or_create(
            name=svc["name"],
            defaults={
                "id": uuid.uuid4(),
                "description": svc["description"],
                "default_rate": 0,
                "unit_type": svc["unit_type"],
                "is_active": True,
                "sort_order": svc["sort_order"],
            },
        )


def remove_default_services(apps, schema_editor):
    Service = apps.get_model("gallery", "Service")
    Service.objects.filter(
        name__in=[s["name"] for s in DEFAULT_SERVICES],
        default_rate=0,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("gallery", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            create_default_services,
            reverse_code=remove_default_services,
        ),
    ]
