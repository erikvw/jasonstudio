import uuid

from django.db import models

from accounts.models import Customer


def photo_upload_path(instance: "Photo", filename: str) -> str:
    return f"photos/{instance.event.id}/{filename}"


def thumbnail_upload_path(instance: "Photo", filename: str) -> str:
    return f"photos/{instance.event.id}/thumbnails/{filename}"


def watermarked_upload_path(instance: "Photo", filename: str) -> str:
    return f"photos/{instance.event.id}/watermarked/{filename}"


class Event(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customers = models.ManyToManyField(
        Customer, related_name="events", blank=True,
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
        return self.name

    @property
    def photo_count(self) -> int:
        return self.photos.count()


class Photo(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="photos")
    original = models.ImageField(upload_to=photo_upload_path, max_length=300)
    thumbnail = models.ImageField(
        upload_to=thumbnail_upload_path, blank=True, default="",
        max_length=300,
        help_text="Resized watermarked version for gallery browsing.",
    )
    watermarked = models.ImageField(
        upload_to=watermarked_upload_path, blank=True, default="",
        max_length=300,
        help_text="Full-resolution watermarked version.",
    )
    title = models.CharField(max_length=200, blank=True, default="")
    caption = models.TextField(blank=True, default="", help_text="Custom legend by photographer.")
    filename = models.CharField(max_length=300, blank=True, default="")
    file_size = models.PositiveIntegerField(default=0, help_text="Original file size in bytes.")
    image_width = models.PositiveIntegerField(default=0)
    image_height = models.PositiveIntegerField(default=0)
    camera_model = models.CharField(max_length=200, blank=True, default="")
    date_taken = models.DateTimeField(null=True, blank=True)
    focal_length = models.CharField(max_length=50, blank=True, default="")
    aperture = models.CharField(max_length=50, blank=True, default="")
    shutter_speed = models.CharField(max_length=50, blank=True, default="")
    iso = models.CharField(max_length=50, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "uploaded_at"]

    def __str__(self) -> str:
        return self.title or self.original.name


class Selection(models.Model):
    class Choice(models.TextChoices):
        DIGITAL = "digital", "Digital"
        BOTH = "both", "Print & Digital"
        REJECT = "reject", "Reject"

    class PrintSize(models.TextChoices):
        SIZE_4X6 = "4x6", "4×6"
        SIZE_5X7 = "5x7", "5×7"
        SIZE_8X10 = "8x10", "8×10"
        SIZE_4X4 = "4x4", "4×4"
        SIZE_8X8 = "8x8", "8×8"
        SIZE_4X5_3 = "4x5.3", "4×5.3"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    photo = models.ForeignKey(
        Photo, on_delete=models.CASCADE, related_name="selections"
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="selections"
    )
    choice = models.CharField(max_length=20, choices=Choice.choices, default=Choice.DIGITAL)
    print_size = models.CharField(
        max_length=10,
        choices=PrintSize.choices,
        default=PrintSize.SIZE_4X6,
        blank=True,
        help_text="Print size, only applicable when choice is Print & Digital.",
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("photo", "customer")]

    def __str__(self) -> str:
        return f"{self.photo} — {self.get_choice_display()}"


class Service(models.Model):
    """Reusable service catalog item with default rates."""

    class UnitType(models.TextChoices):
        PER_HOUR = "per_hour", "Per Hour"
        PER_IMAGE = "per_image", "Per Image"
        PER_KM = "per_km", "Per Km"
        FLAT = "flat", "Flat Fee"
        EACH = "each", "Each"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    default_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit_type = models.CharField(
        max_length=20, choices=UnitType.choices, default=UnitType.PER_HOUR
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_unit_type_display()})"


class ShareLink(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(
        "accounts.Order", on_delete=models.CASCADE, related_name="share_link",
    )
    code = models.CharField(max_length=8, unique=True)
    is_active = models.BooleanField(default=True)
    download_count = models.PositiveIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self) -> str:
        return f"{self.code} — {self.order.ref}"

    @property
    def is_valid(self) -> bool:
        return (
            self.is_active
            and self.order.download_available
            and self.order.event.status != "archived"
        )

    @staticmethod
    def generate_code() -> str:
        import secrets
        import string

        alphabet = string.ascii_uppercase + string.digits
        while True:
            code = "".join(secrets.choice(alphabet) for _ in range(6))
            if not ShareLink.objects.filter(code=code).exists():
                return code
