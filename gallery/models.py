import uuid

from django.db import models

from accounts.models import Customer


def photo_upload_path(instance: "Photo", filename: str) -> str:
    return f"photos/{instance.event.customer.id}/{instance.event.id}/{filename}"


def watermarked_upload_path(instance: "Photo", filename: str) -> str:
    return f"photos/{instance.event.customer.id}/{instance.event.id}/watermarked/{filename}"


class Event(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="events"
    )
    name = models.CharField(max_length=200)
    date = models.DateField()
    location = models.CharField(max_length=300, blank=True, default="")
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"{self.name} — {self.customer}"

    @property
    def photo_count(self) -> int:
        return self.photos.count()


class Photo(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="photos")
    original = models.ImageField(upload_to=photo_upload_path)
    watermarked = models.ImageField(
        upload_to=watermarked_upload_path, blank=True, default=""
    )
    title = models.CharField(max_length=200, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "uploaded_at"]

    def __str__(self) -> str:
        return self.title or self.original.name


class Selection(models.Model):
    class SelectionType(models.TextChoices):
        PRINT = "print", "Print"
        DIGITAL = "digital", "Digital Library"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    photo = models.ForeignKey(
        Photo, on_delete=models.CASCADE, related_name="selections"
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="selections"
    )
    selection_type = models.CharField(
        max_length=20, choices=SelectionType.choices
    )
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("photo", "customer", "selection_type")]

    def __str__(self) -> str:
        return f"{self.photo} — {self.get_selection_type_display()}"
