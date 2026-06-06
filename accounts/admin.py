from django.contrib import admin

from .models import Customer, PhotographerProfile


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["__str__", "phone", "created"]
    search_fields = ["user__first_name", "user__last_name", "user__email"]


@admin.register(PhotographerProfile)
class PhotographerProfileAdmin(admin.ModelAdmin):
    list_display = ["__str__", "business_name"]
