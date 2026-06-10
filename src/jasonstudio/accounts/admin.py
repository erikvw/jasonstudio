from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import (
    Customer,
    Invoice,
    InvoiceLineItem,
    Order,
    Payment,
    PhotographerProfile,
    Quotation,
    QuotationLineItem,
)


class PhotographerProfileInline(admin.StackedInline):
    model = PhotographerProfile
    can_delete = True
    verbose_name = "Photographer profile"
    verbose_name_plural = "Photographer profile"
    extra = 0


class CustomerInline(admin.StackedInline):
    model = Customer
    can_delete = True
    verbose_name = "Customer profile"
    verbose_name_plural = "Customer profile"
    extra = 0


class UserAdmin(BaseUserAdmin):
    inlines = list(BaseUserAdmin.inlines) + [
        PhotographerProfileInline,
        CustomerInline,
    ]


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["__str__", "phone", "date_created"]
    search_fields = ["user__first_name", "user__last_name", "user__email"]


@admin.register(PhotographerProfile)
class PhotographerProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "business_name", "phone", "email", "date_created"]
    search_fields = ["user__username", "user__first_name", "user__last_name"]
    fieldsets = [
        (None, {"fields": ["user", "business_name"]}),
        ("Contact", {"fields": ["phone", "email", "address"]}),
        (
            "Invoice Settings",
            {
                "fields": [
                    "payment_terms",
                    "payment_instructions",
                    "tax_rate",
                    "invoice_notes",
                ]
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Quotation, Order, Invoice, Payment admin
# ---------------------------------------------------------------------------


class QuotationLineItemInline(admin.TabularInline):
    model = QuotationLineItem
    extra = 1
    fields = ["sort_order", "service", "description", "qty", "unit_cost", "price"]


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = [
        "quote_number",
        "event",
        "customer",
        "status",
        "total",
        "valid_until",
        "date_created",
    ]
    list_filter = ["status"]
    search_fields = ["quote_number", "customer__user__username", "event__name"]
    readonly_fields = ["quote_number", "accepted_at", "accepted_by"]
    inlines = [QuotationLineItemInline]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "ref",
        "event",
        "customer",
        "status",
        "download_count",
        "date_created",
    ]
    list_filter = ["status", "event"]
    search_fields = ["ref", "customer__user__username", "event__name"]
    readonly_fields = ["ref", "download_count", "drive_url"]


class InvoiceLineItemInline(admin.TabularInline):
    model = InvoiceLineItem
    extra = 0
    fields = ["sort_order", "description", "filename", "qty", "unit_cost", "price"]


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 1
    fields = ["amount", "method", "reference", "date", "notes"]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = [
        "invoice_number",
        "order",
        "status",
        "amount_due",
        "issued_at",
        "date_created",
    ]
    list_filter = ["status"]
    search_fields = ["invoice_number", "order__ref"]
    readonly_fields = [
        "invoice_number",
        "subtotal",
        "deposit",
        "tax_rate",
        "tax_amount",
        "amount_due",
    ]
    inlines = [InvoiceLineItemInline, PaymentInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["receipt_number", "invoice", "amount", "method", "date"]
    list_filter = ["method"]
    search_fields = ["receipt_number", "invoice__invoice_number"]
    readonly_fields = ["receipt_number"]
