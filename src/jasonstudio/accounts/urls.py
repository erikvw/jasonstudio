from django.urls import path

from . import views

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("dashboard/", views.customer_dashboard, name="customer_dashboard"),
    path("customers/", views.customer_list, name="customer_list"),
    path("customers/add/", views.customer_add, name="customer_add"),
    path(
        "customers/<str:customer_id>/edit/", views.customer_edit, name="customer_edit"
    ),
    path(
        "customers/<str:customer_id>/toggle-active/",
        views.customer_toggle_active,
        name="customer_toggle_active",
    ),
    path(
        "customers/<str:customer_id>/delete/",
        views.customer_delete,
        name="customer_delete",
    ),
]
