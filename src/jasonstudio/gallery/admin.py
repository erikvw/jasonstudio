from django.contrib import admin

from .models import (
    Event,
    Photo,
    Selection,
    Service,
    ShareLink,
)


class PhotoInline(admin.TabularInline):
    model = Photo
    extra = 1
    fields = ["original", "title", "sort_order"]
    readonly_fields: list[str] = []


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["name", "date", "status", "photo_count", "customer_list"]
    list_filter = ["status", "date"]
    search_fields = ["name"]
    filter_horizontal = ["customers"]
    inlines = [PhotoInline]

    def photo_count(self, obj: Event) -> int:
        return obj.photos.count()

    def customer_list(self, obj: Event) -> str:
        return ", ".join(str(c) for c in obj.customers.all())

    customer_list.short_description = "Customers"


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ["__str__", "event", "sort_order", "uploaded_at"]
    list_filter = ["event"]


@admin.register(Selection)
class SelectionAdmin(admin.ModelAdmin):
    list_display = ["photo", "customer", "choice", "created"]
    list_filter = ["choice"]


@admin.register(ShareLink)
class ShareLinkAdmin(admin.ModelAdmin):
    list_display = ["code", "order", "is_active", "download_count", "created"]
    list_filter = ["is_active"]
    search_fields = ["code", "order__ref"]
    readonly_fields = ["code", "download_count"]


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ["name", "default_rate", "unit_type", "is_active", "sort_order"]
    list_filter = ["unit_type", "is_active"]
    list_editable = ["default_rate", "sort_order", "is_active"]
    search_fields = ["name"]
