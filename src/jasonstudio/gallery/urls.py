from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("photographer/", views.photographer_dashboard, name="photographer_dashboard"),
    path("event/new/", views.manage_event, name="create_event"),
    path("event/<str:event_id>/edit/", views.manage_event, name="edit_event"),
    path("event/<str:event_id>/", views.event_gallery, name="event_gallery"),
    path("event/<str:event_id>/upload/", views.upload_photos, name="upload_photos"),
    path("event/<str:event_id>/orders/", views.event_orders, name="event_orders"),
    path(
        "event/<str:event_id>/invoice/<str:customer_id>/",
        views.photographer_invoice,
        name="photographer_invoice",
    ),
    path(
        "event/<str:event_id>/orders/<str:customer_id>/",
        views.customer_order_detail,
        name="customer_order_detail",
    ),
    path(
        "event/<str:event_id>/orders/<str:customer_id>/payment/",
        views.record_payment,
        name="record_payment",
    ),
    path(
        "event/<str:event_id>/orders/<str:customer_id>/receipt/",
        views.payment_receipt,
        name="payment_receipt",
    ),
    path(
        "event/<str:event_id>/orders/<str:customer_id>/fulfilment/",
        views.order_fulfilment,
        name="order_fulfilment",
    ),
    path(
        "event/<str:event_id>/orders/<str:customer_id>/fulfilment/new-delivery/",
        views.delivery_create,
        name="delivery_create",
    ),
    path(
        "event/<str:event_id>/orders/<str:customer_id>/fulfilment/mark-delivered/",
        views.mark_order_delivered,
        name="mark_order_delivered",
    ),
    path(
        "event/<str:event_id>/orders/<str:customer_id>/fulfilment/reopen-delivery/",
        views.reopen_order_delivery,
        name="reopen_order_delivery",
    ),
    path(
        "delivery/<str:delivery_id>/",
        views.delivery_detail,
        name="delivery_detail",
    ),
    path(
        "delivery/<str:delivery_id>/delete/",
        views.delivery_delete,
        name="delivery_delete",
    ),
    path(
        "event/<str:event_id>/notes/",
        views.event_planning_notes,
        name="event_planning_notes",
    ),
    path(
        "event/<str:event_id>/orders/<str:customer_id>/download/<str:zip_type>/",
        views.download_zip,
        name="download_zip",
    ),
    path(
        "event/<str:event_id>/download-all/",
        views.download_event_photos,
        name="download_event_photos",
    ),
    path(
        "event/<str:event_id>/orders/<str:customer_id>/upload-to-drive/",
        views.upload_to_google_drive,
        name="upload_to_google_drive",
    ),
    path(
        "event/<str:event_id>/orders/<str:customer_id>/select-files-for-drive/",
        views.select_files_for_drive,
        name="select_files_for_drive",
    ),
    path(
        "event/<str:event_id>/orders/<str:customer_id>/upload-selected-to-drive/",
        views.upload_selected_to_google_drive,
        name="upload_selected_to_google_drive",
    ),
    path(
        "event/<str:event_id>/regenerate-thumbnails/",
        views.regenerate_thumbnails,
        name="regenerate_thumbnails",
    ),
    path("photo/<str:photo_id>/caption/", views.update_caption, name="update_caption"),
    path("photo/<str:photo_id>/delete/", views.delete_photo, name="delete_photo"),
    path(
        "photo/<str:photo_id>/select/", views.toggle_selection, name="toggle_selection"
    ),
    path("my-selections/", views.my_selections, name="my_selections"),
    path(
        "my-selections/<str:event_id>/invoice/",
        views.selection_invoice,
        name="selection_invoice",
    ),
    path(
        "my-selections/<str:event_id>/download/",
        views.customer_download,
        name="customer_download",
    ),
    path(
        "my-selections/<str:event_id>/share/",
        views.create_share_link,
        name="create_share_link",
    ),
    path(
        "my-selections/<str:event_id>/share/deactivate/",
        views.deactivate_share_link,
        name="deactivate_share_link",
    ),
    path("shared/<str:code>/", views.shared_download_page, name="shared_download_page"),
    path(
        "shared/<str:code>/download/",
        views.shared_download_file,
        name="shared_download_file",
    ),
    # Services
    path("photographer/services/", views.service_list, name="service_list"),
    path("photographer/services/add/", views.service_edit, name="service_add"),
    path(
        "photographer/services/<str:service_id>/edit/",
        views.service_edit,
        name="service_edit",
    ),
    # Quotations
    path(
        "photographer/event/<str:event_id>/quote/<str:customer_id>/",
        views.quotation_edit,
        name="quotation_edit",
    ),
    path(
        "photographer/event/<str:event_id>/quote/<str:customer_id>/view/",
        views.quotation_view,
        name="quotation_view",
    ),
    path(
        "photographer/event/<str:event_id>/quote/<str:customer_id>/accept/",
        views.quotation_accept,
        name="quotation_accept",
    ),
    path(
        "photographer/event/<str:event_id>/quote/<str:customer_id>/delete/",
        views.quotation_delete,
        name="quotation_delete",
    ),
    path(
        "my-quotes/<str:event_id>/",
        views.customer_quotation_view,
        name="customer_quotation_view",
    ),
    path(
        "my-quotes/<str:event_id>/accept/",
        views.customer_quotation_accept,
        name="customer_quotation_accept",
    ),
    path(
        "my-quotes/<str:event_id>/decline/",
        views.customer_quotation_decline,
        name="customer_quotation_decline",
    ),
    # Utilities
    path("photographer/utilities/", views.utilities, name="utilities"),
    path(
        "photographer/utilities/backup/", views.backup_database, name="backup_database"
    ),
    path(
        "photographer/utilities/email-template/",
        views.email_template_edit,
        name="email_template_edit",
    ),
    # Download tokens (email-based)
    path(
        "event/<str:event_id>/orders/<str:customer_id>/send-download-email/",
        views.send_download_email,
        name="send_download_email",
    ),
    path(
        "download/<str:token>/", views.token_download_page, name="token_download_page"
    ),
    path(
        "download/<str:token>/file/",
        views.token_download_file,
        name="token_download_file",
    ),
]
