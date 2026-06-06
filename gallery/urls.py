from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("photographer/", views.photographer_dashboard, name="photographer_dashboard"),
    path("event/new/", views.manage_event, name="create_event"),
    path("event/<str:event_id>/edit/", views.manage_event, name="edit_event"),
    path("event/<str:event_id>/", views.event_gallery, name="event_gallery"),
    path("event/<str:event_id>/upload/", views.upload_photos, name="upload_photos"),
    path("photo/<str:photo_id>/select/", views.toggle_selection, name="toggle_selection"),
    path("my-selections/", views.my_selections, name="my_selections"),
]
