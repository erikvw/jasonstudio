import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from encrypted_fields.fields import (
    EncryptedCharField,
    EncryptedEmailField,
    EncryptedTextField,
)
from simple_history.models import HistoricalRecords


# ---------------------------------------------------------------------------
# Audit mixin — date_created, date_modified, user_created, user_modified
# ---------------------------------------------------------------------------


class AuditFieldsMixin(models.Model):
    """Non-editable audit fields on every document."""

    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)
    user_created = models.CharField(
        max_length=150,
        blank=True,
        default="",
        editable=False,
        help_text="Username of the user who created this record.",
    )
    user_modified = models.CharField(
        max_length=150,
        blank=True,
        default="",
        editable=False,
        help_text="Username of the user who last modified this record.",
    )

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Customer and PhotographerProfile
# ---------------------------------------------------------------------------


class Customer(AuditFieldsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customer_profile",
    )
    company_name = models.CharField(max_length=200, blank=True, default="")
    phone = EncryptedCharField(max_length=20, blank=True, null=True, default="")
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["user__last_name", "user__first_name"]

    def __str__(self) -> str:
        return f"{self.user.get_full_name() or self.user.username}"


class PhotographerProfile(AuditFieldsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="photographer_profile",
    )
    business_name = models.CharField(max_length=200, blank=True, default="")
    phone = EncryptedCharField(max_length=20, blank=True, null=True, default="")
    email = EncryptedEmailField(blank=True, null=True, default="")
    address = EncryptedTextField(
        blank=True, null=True, default="", help_text="Business address."
    )
    payment_instructions = EncryptedTextField(
        blank=True,
        null=True,
        default="",
        help_text="Payment details shown on invoices (bank, Venmo, etc.).",
    )
    payment_terms = models.CharField(
        max_length=100,
        blank=True,
        default="Due within 30 days",
        help_text="e.g. 'Due within 30 days', 'Due on receipt'.",
    )
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Tax percentage (e.g. 13.00 for 13%).",
    )
    invoice_notes = models.TextField(
        blank=True,
        default="",
        help_text="Default terms/notes shown at the bottom of invoices.",
    )
    email_subject_template = models.CharField(
        max_length=200,
        blank=True,
        default='Your photos from "{event_name}" are ready',
        help_text=(
            "Subject line for download emails. "
            "Placeholders: {customer_name}, {event_name}, {photographer_name}"
        ),
    )
    email_body_template = models.TextField(
        blank=True,
        default=(
            "Hi {customer_name},\n\n"
            'Your photos from "{event_name}" are ready for download.\n\n'
            "Click the link below to download your photos:\n\n"
            "{download_url}\n\n"
            "Thank you for choosing {photographer_name}."
        ),
        help_text=(
            "Body for download emails. "
            "Placeholders: {customer_name}, {event_name}, "
            "{photographer_name}, {download_url}"
        ),
    )

    def __str__(self) -> str:
        return self.business_name or str(self.user)


# ---------------------------------------------------------------------------
# Quotation → Order → Invoice → Payment
# ---------------------------------------------------------------------------


class Quotation(AuditFieldsMixin):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        EXPIRED = "expired", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quote_number = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        help_text="Auto-generated quote number.",
    )
    event = models.ForeignKey(
        "gallery.Event",
        on_delete=models.CASCADE,
        related_name="quotations",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="quotations",
    )
    date = models.DateField(
        help_text="Date of the quotation.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    valid_until = models.DateField(
        null=True,
        blank=True,
        help_text="Quote expires after this date.",
    )
    deposit_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Deposit required before the shoot.",
    )
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes = models.TextField(blank=True, default="")
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Who accepted: 'customer' or 'photographer'.",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["-date_created"]
        unique_together = [("event", "customer")]

    def __str__(self) -> str:
        return f"{self.quote_number} — {self.customer}"

    def save(self, *args, **kwargs) -> None:
        if not self.date:
            self.date = timezone.now().date()
        if not self.quote_number:
            last = (
                Quotation.objects.exclude(quote_number="")
                .order_by("-date_created")
                .first()
            )
            next_num = 1
            if last and last.quote_number:
                try:
                    next_num = int(last.quote_number.replace("QUO-", "")) + 1
                except ValueError:
                    next_num = Quotation.objects.count() + 1
            self.quote_number = f"QUO-{next_num:05d}"
        super().save(*args, **kwargs)

    @property
    def is_expired(self) -> bool:
        if self.valid_until:
            return timezone.now().date() > self.valid_until
        return False

    def accept(self, by: str = "customer") -> "Order":
        """Accept the quotation and create an Order from it."""
        self.status = self.Status.ACCEPTED
        self.accepted_at = timezone.now()
        self.accepted_by = by
        self.save(
            update_fields=[
                "status",
                "accepted_at",
                "accepted_by",
                "date_modified",
            ]
        )

        order, _created = Order.objects.get_or_create(
            event=self.event,
            customer=self.customer,
            defaults={"quotation": self, "date": timezone.now().date()},
        )
        if not _created:
            order.quotation = self
            order.save(update_fields=["quotation", "date_modified"])
        return order


class QuotationLineItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quotation = models.ForeignKey(
        Quotation,
        on_delete=models.CASCADE,
        related_name="line_items",
    )
    service = models.ForeignKey(
        "gallery.Service",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quotation_items",
    )
    sort_order = models.PositiveIntegerField(default=0)
    description = models.CharField(max_length=300)
    qty = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self) -> str:
        return self.description


class Order(AuditFieldsMixin):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In Progress"
        DELIVERED = "delivered", "Delivered"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ref = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        help_text="Short reference code for this order.",
    )
    quotation = models.OneToOneField(
        Quotation,
        on_delete=models.PROTECT,
        related_name="order",
    )
    event = models.ForeignKey(
        "gallery.Event",
        on_delete=models.CASCADE,
        related_name="orders",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="orders",
    )
    date = models.DateField(
        help_text="Date of the order.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
    )
    download_count = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True, default="")
    drive_url = models.URLField(
        max_length=500,
        blank=True,
        default="",
        help_text="Google Drive download link for customer delivery.",
    )

    history = HistoricalRecords()

    class Meta:
        unique_together = [("event", "customer")]
        ordering = ["-date_created"]

    def __str__(self) -> str:
        return f"{self.event.name} — {self.customer} ({self.get_status_display()})"

    def clean(self) -> None:
        super().clean()
        if self.date and self.quotation_id:
            quotation_date = self.quotation.date
            if quotation_date and self.date < quotation_date:
                raise ValidationError(
                    {
                        "date": (
                            f"Order date ({self.date}) cannot be before "
                            f"the quotation date ({quotation_date})."
                        )
                    }
                )

    def save(self, *args, **kwargs) -> None:
        if not self.date:
            self.date = timezone.now().date()
        if not self.ref:
            last = Order.objects.order_by("-date_created").first()
            next_num = 1
            if last and last.ref:
                try:
                    next_num = int(last.ref.replace("ORD-", "")) + 1
                except ValueError:
                    next_num = Order.objects.count() + 1
            self.ref = f"ORD-{next_num:05d}"
        super().save(*args, **kwargs)

    @property
    def is_paid(self) -> bool:
        """Order is paid when its latest invoice has a payment recorded."""
        invoice = self.invoices.order_by("-date_created").first()
        if invoice and invoice.status == Invoice.Status.PAID:
            return True
        return False

    @property
    def paid_at(self) -> timezone.datetime | None:
        """Return the date/time of the first payment on the latest invoice."""
        invoice = self.invoices.order_by("-date_created").first()
        if invoice:
            payment = invoice.payments.order_by("date_created").first()
            if payment:
                return payment.date_created
        return None

    @property
    def download_expires_at(self):
        if self.paid_at:
            return self.paid_at + timedelta(days=30)
        return None

    @property
    def download_available(self) -> bool:
        if not self.is_paid:
            return False
        if not self.paid_at:
            return True
        return timezone.now() <= self.paid_at + timedelta(days=30)


class Invoice(AuditFieldsMixin):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ISSUED = "issued", "Issued"
        PAID = "paid", "Paid"
        VOID = "void", "Void"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        help_text="Auto-generated invoice number.",
    )
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="invoices")
    date = models.DateField(
        help_text="Date of the invoice.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    issued_at = models.DateTimeField(null=True, blank=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deposit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Deposit amount credited from the order.",
    )
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Tax percentage at time of invoice.",
    )
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_due = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes = models.TextField(blank=True, default="")

    history = HistoricalRecords()

    class Meta:
        ordering = ["-date_created"]

    def __str__(self) -> str:
        return f"{self.invoice_number} — {self.order.ref}"

    def clean(self) -> None:
        super().clean()
        if self.date and self.order_id:
            order_date = self.order.date
            if order_date and self.date < order_date:
                raise ValidationError(
                    {
                        "date": (
                            f"Invoice date ({self.date}) cannot be before "
                            f"the order date ({order_date})."
                        )
                    }
                )

    def save(self, *args, **kwargs) -> None:
        if not self.date:
            self.date = timezone.now().date()
        if not self.invoice_number:
            last = (
                Invoice.objects.exclude(invoice_number="")
                .order_by("-date_created")
                .first()
            )
            next_num = 1
            if last and last.invoice_number:
                try:
                    next_num = int(last.invoice_number.replace("INV-", "")) + 1
                except ValueError:
                    next_num = Invoice.objects.count() + 1
            self.invoice_number = f"INV-{next_num:05d}"
        if self.status == self.Status.ISSUED and not self.issued_at:
            self.issued_at = timezone.now()
        super().save(*args, **kwargs)


class InvoiceLineItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="line_items"
    )
    sort_order = models.PositiveIntegerField(default=0)
    description = models.CharField(max_length=300)
    filename = models.CharField(max_length=300, blank=True, default="")
    qty = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self) -> str:
        return self.description


class Payment(AuditFieldsMixin):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        ETRANSFER = "etransfer", "E-Transfer"
        CREDIT_CARD = "credit_card", "Credit Card"
        CHEQUE = "cheque", "Cheque"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    receipt_number = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        help_text="Auto-generated receipt number.",
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    date = models.DateField(
        help_text="Date the payment was received.",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(
        max_length=20,
        choices=Method.choices,
        default=Method.ETRANSFER,
    )
    reference = EncryptedCharField(
        max_length=200,
        blank=True,
        null=True,
        default="",
        help_text="Transaction ID, cheque number, etc.",
    )
    notes = models.TextField(blank=True, default="")

    history = HistoricalRecords()

    class Meta:
        ordering = ["-date"]

    def __str__(self) -> str:
        return (
            f"{self.receipt_number} — ${self.amount} "
            f"({self.get_method_display()}) — {self.invoice.invoice_number}"
        )

    def clean(self) -> None:
        super().clean()
        if self.date and self.invoice_id:
            invoice_date = self.invoice.date
            if invoice_date and self.date < invoice_date:
                raise ValidationError(
                    {
                        "date": (
                            f"Payment date ({self.date}) cannot be before "
                            f"the invoice date ({invoice_date})."
                        )
                    }
                )

    def save(self, *args, **kwargs) -> None:
        if not self.date:
            self.date = timezone.now().date()
        if not self.receipt_number:
            last = (
                Payment.objects.exclude(receipt_number="")
                .order_by("-date_created")
                .first()
            )
            next_num = 1
            if last and last.receipt_number:
                try:
                    next_num = int(last.receipt_number.replace("REC-", "")) + 1
                except ValueError:
                    next_num = Payment.objects.count() + 1
            self.receipt_number = f"REC-{next_num:05d}"
        super().save(*args, **kwargs)
        # Mark invoice as paid when payment is recorded
        if self.invoice_id and self.invoice.status != Invoice.Status.PAID:
            self.invoice.status = Invoice.Status.PAID
            self.invoice.save(update_fields=["status", "date_modified"])


# ---------------------------------------------------------------------------
# Download tokens
# ---------------------------------------------------------------------------


def _generate_download_token() -> str:
    return secrets.token_urlsafe(32)


class DownloadToken(AuditFieldsMixin):
    """A unique, time-limited download link sent to a customer's email."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token = models.CharField(
        max_length=64,
        unique=True,
        default=_generate_download_token,
        editable=False,
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="download_tokens",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="download_tokens",
    )
    expires_at = models.DateTimeField(
        help_text="Token expires after this datetime.",
    )
    sent_to_email = EncryptedEmailField(
        blank=True,
        null=True,
        default="",
        help_text="Email address the link was sent to.",
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    download_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-date_created"]

    def __str__(self) -> str:
        return f"Download token for {self.order.ref} — {self.customer}"

    def save(self, *args, **kwargs) -> None:
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(
                days=getattr(settings, "DOWNLOAD_TOKEN_EXPIRY_DAYS", 30)
            )
        super().save(*args, **kwargs)

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def is_valid(self) -> bool:
        return not self.is_expired
