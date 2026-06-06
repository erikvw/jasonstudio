from django.contrib import admin

from .models import Event, Photo, Selection


class PhotoInline(admin.TabularInline):
    model = Photo
    extra = 1
    fields = ["original", "title", "sort_order"]
    readonly_fields: list[str] = []


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["name", "customer", "date", "status", "photo_count"]
    list_filter = ["status", "date"]
    search_fields = ["name", "customer__user__first_name", "customer__user__last_name"]
    inlines = [PhotoInline]

    def photo_count(self, obj: Event) -> int:
        return obj.photos.count()


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ["__str__", "event", "sort_order", "uploaded_at"]
    list_filter = ["event__customer"]


@admin.register(Selection)
class SelectionAdmin(admin.ModelAdmin):
    list_display = ["photo", "customer", "selection_type", "created"]
    list_filter = ["selection_type"]
