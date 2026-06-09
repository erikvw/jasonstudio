from io import BytesIO

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.db.models import F
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from PIL import Image, ImageOps

from jasonstudio.accounts.models import (
    DownloadToken,
    Invoice,
    InvoiceLineItem,
    Order,
    PhotographerProfile,
    Quotation,
    QuotationLineItem,
)

from .exif import extract_exif
from .models import (
    Event,
    Photo,
    Selection,
    Service,
    ShareLink,
)
from .watermark import apply_watermark, create_thumbnail


def _is_photographer(user) -> bool:
    try:
        return bool(user.photographer_profile)
    except Exception:
        return False


def _get_customer(user):
    try:
        return user.customer_profile
    except Exception:
        return None


def home(request: HttpRequest) -> HttpResponse:
    from jasonstudio.accounts.models import PhotographerProfile

    if request.user.is_authenticated:
        if _is_photographer(request.user):
            return redirect("photographer_dashboard")
        if _get_customer(request.user):
            return redirect("customer_dashboard")
    show_setup = (
        request.user.is_authenticated
        and request.user.is_superuser
        and not PhotographerProfile.objects.exists()
    )
    return render(request, "gallery/home.html", {"show_photographer_setup": show_setup})


@login_required
def event_gallery(request: HttpRequest, event_id: str) -> HttpResponse:
    customer = _get_customer(request.user)
    is_photographer = _is_photographer(request.user)

    if is_photographer:
        event = get_object_or_404(Event, pk=event_id)
    elif customer:
        event = get_object_or_404(
            Event, pk=event_id, customers=customer, status="published"
        )
    else:
        return redirect("home")

    all_photos = event.photos.all()
    selections = {}
    print_sizes_map = {}
    if customer:
        for sel in Selection.objects.filter(customer=customer, photo__event=event):
            selections[str(sel.photo_id)] = sel.choice
            print_sizes_map[str(sel.photo_id)] = sel.print_size

    # Filter by selection choice
    filter_by = request.GET.get("filter", "")
    valid_filters = {"digital", "both", "reject", "undecided"}
    if filter_by not in valid_filters:
        filter_by = ""

    if filter_by and customer:
        if filter_by == "undecided":
            decided_ids = set(selections.keys())
            photos = [p for p in all_photos if str(p.pk) not in decided_ids]
        else:
            photos = [p for p in all_photos if selections.get(str(p.pk)) == filter_by]
    else:
        photos = all_photos

    # Counts for filter tabs
    filter_counts = {"digital": 0, "both": 0, "reject": 0, "undecided": 0}
    if customer:
        decided_ids = set(selections.keys())
        for choice in selections.values():
            if choice in filter_counts:
                filter_counts[choice] += 1
        filter_counts["undecided"] = sum(
            1 for p in all_photos if str(p.pk) not in decided_ids
        )

    return render(
        request,
        "gallery/event_gallery.html",
        {
            "event": event,
            "photos": photos,
            "selections": selections,
            "print_sizes_map": print_sizes_map,
            "print_sizes": Selection.PrintSize.choices,
            "is_photographer": is_photographer,
            "is_customer": customer is not None,
            "current_filter": filter_by,
            "filter_counts": filter_counts,
            "total_count": len(all_photos)
            if isinstance(all_photos, list)
            else all_photos.count(),
        },
    )


@login_required
def upload_photos(request: HttpRequest, event_id: str) -> HttpResponse:
    if not _is_photographer(request.user):
        return redirect("home")

    event = get_object_or_404(Event, pk=event_id)

    if request.method == "POST":
        allowed_types = {
            "image/jpeg",
            "image/png",
            "image/gif",
            "image/webp",
            "image/tiff",
        }
        files = [
            f
            for f in request.FILES.getlist("photos")
            if f.content_type in allowed_types
        ]
        processed = 0
        new_photos: list[Photo] = []
        for f in files:
            # Extract EXIF before anything reads the file
            f.seek(0)
            exif_data = extract_exif(BytesIO(f.read()))

            # Transpose original to correct orientation
            f.seek(0)
            img = ImageOps.exif_transpose(Image.open(f))
            original_buf = BytesIO()
            fmt = "JPEG" if f.content_type == "image/jpeg" else "PNG"
            img.save(original_buf, format=fmt, quality=95)
            original_buf.seek(0)
            original_file = ContentFile(original_buf.read(), name=f.name)

            photo = Photo(
                event=event,
                original=original_file,
                filename=f.name,
                file_size=f.size,
                image_width=exif_data.get("image_width", 0),
                image_height=exif_data.get("image_height", 0),
                camera_model=exif_data.get("camera_model", ""),
                date_taken=exif_data.get("date_taken"),
                focal_length=exif_data.get("focal_length", ""),
                aperture=exif_data.get("aperture", ""),
                shutter_speed=exif_data.get("shutter_speed", ""),
                iso=exif_data.get("iso", ""),
            )
            photo.save()

            watermark_text = getattr(settings, "WATERMARK_TEXT", "PROOF")
            watermark_opacity = getattr(settings, "WATERMARK_OPACITY", 64)

            f.seek(0)
            thumb_buffer = create_thumbnail(
                BytesIO(f.read()),
                text=watermark_text,
                opacity=watermark_opacity,
            )
            photo.thumbnail.save(
                f"thumb_{f.name}", ContentFile(thumb_buffer.read()), save=False
            )

            f.seek(0)
            wm_buffer = apply_watermark(
                BytesIO(f.read()),
                text=watermark_text,
                opacity=watermark_opacity,
            )
            photo.watermarked.save(
                f"wm_{f.name}", ContentFile(wm_buffer.read()), save=False
            )

            photo.save()
            new_photos.append(photo)
            processed += 1

        # Default all uploaded photos to "Digital" for customers with an order
        if new_photos:
            from jasonstudio.accounts.models import Customer

            order_customers = Customer.objects.filter(
                orders__event=event,
            ).distinct()
            if order_customers:
                selections_to_create = [
                    Selection(
                        photo=photo,
                        customer=customer,
                        choice=Selection.Choice.DIGITAL,
                    )
                    for photo in new_photos
                    for customer in order_customers
                ]
                Selection.objects.bulk_create(
                    selections_to_create,
                    ignore_conflicts=True,
                )

        return JsonResponse({"processed": processed})

    photos = event.photos.all()
    return render(
        request,
        "gallery/upload.html",
        {"event": event, "photos": photos, "is_photographer": True},
    )


@login_required
@require_POST
def regenerate_thumbnails(request: HttpRequest, event_id: str) -> HttpResponse:
    if not _is_photographer(request.user):
        return JsonResponse({"error": "forbidden"}, status=403)

    event = get_object_or_404(Event, pk=event_id)
    watermark_text = getattr(settings, "WATERMARK_TEXT", "PROOF")
    watermark_opacity = getattr(settings, "WATERMARK_OPACITY", 64)

    # Accept optional list of photo IDs (for chunked requests)
    photo_ids = request.POST.getlist("photo_ids")
    if photo_ids:
        photos = event.photos.filter(pk__in=photo_ids)
    else:
        photos = event.photos.all()

    processed = 0
    skipped = 0
    for photo in photos:
        if not photo.original:
            skipped += 1
            continue

        try:
            photo.original.open("rb")
            original_bytes = photo.original.read()
            photo.original.close()
        except FileNotFoundError:
            skipped += 1
            continue

        filename = photo.filename or f"photo_{photo.pk}.jpg"

        thumb_buffer = create_thumbnail(
            BytesIO(original_bytes),
            text=watermark_text,
            opacity=watermark_opacity,
        )
        photo.thumbnail.save(
            f"thumb_{filename}",
            ContentFile(thumb_buffer.read()),
            save=False,
        )

        wm_buffer = apply_watermark(
            BytesIO(original_bytes),
            text=watermark_text,
            opacity=watermark_opacity,
        )
        photo.watermarked.save(
            f"wm_{filename}",
            ContentFile(wm_buffer.read()),
            save=False,
        )

        photo.save()
        processed += 1

    return JsonResponse({"processed": processed, "skipped": skipped})


@login_required
@require_POST
def update_caption(request: HttpRequest, photo_id: str) -> HttpResponse:
    if not _is_photographer(request.user):
        return redirect("home")

    photo = get_object_or_404(Photo, pk=photo_id)
    photo.caption = request.POST.get("caption", "")
    photo.save(update_fields=["caption"])

    return render(
        request,
        "gallery/partials/photo_caption.html",
        {"photo": photo, "is_photographer": True},
    )


@login_required
@require_POST
def delete_photo(request: HttpRequest, photo_id: str) -> HttpResponse:
    if not _is_photographer(request.user):
        return redirect("home")

    photo = get_object_or_404(Photo, pk=photo_id)
    event = photo.event

    if photo.original:
        photo.original.delete(save=False)
    if photo.thumbnail:
        photo.thumbnail.delete(save=False)
    if photo.watermarked:
        photo.watermarked.delete(save=False)
    photo.delete()

    if request.htmx:
        photos = event.photos.all()
        return render(
            request,
            "gallery/partials/photo_grid.html",
            {"photos": photos, "event": event, "is_photographer": True},
        )
    return redirect("event_gallery", event_id=event.pk)


@login_required
@require_POST
def toggle_selection(request: HttpRequest, photo_id: str) -> HttpResponse:
    customer = _get_customer(request.user)
    if not customer:
        return JsonResponse({"error": "Not a customer"}, status=403)

    photo = get_object_or_404(Photo, pk=photo_id)
    choice = request.POST.get("choice", "")
    valid_choices = {c.value for c in Selection.Choice}
    if choice not in valid_choices:
        return JsonResponse({"error": "Invalid choice"}, status=400)

    print_size = request.POST.get("print_size", Selection.PrintSize.SIZE_4X6)
    valid_sizes = {s.value for s in Selection.PrintSize}
    if print_size not in valid_sizes:
        print_size = Selection.PrintSize.SIZE_4X6

    existing = Selection.objects.filter(photo=photo, customer=customer).first()
    if existing and existing.choice == choice:
        # Clicking the active choice deselects it
        existing.delete()
        current_choice = ""
        current_print_size = Selection.PrintSize.SIZE_4X6
    elif existing:
        existing.choice = choice
        existing.print_size = print_size if choice == "both" else ""
        existing.save(update_fields=["choice", "print_size", "modified"])
        current_choice = choice
        current_print_size = existing.print_size
    else:
        sel = Selection.objects.create(
            photo=photo,
            customer=customer,
            choice=choice,
            print_size=print_size if choice == "both" else "",
        )
        current_choice = choice
        current_print_size = sel.print_size

    if request.htmx:
        from django.template.loader import render_to_string

        # Render selection buttons
        buttons_html = render_to_string(
            "gallery/partials/selection_buttons.html",
            {
                "photo": photo,
                "current_choice": current_choice,
                "current_print_size": current_print_size,
                "print_sizes": Selection.PrintSize.choices,
            },
            request=request,
        )

        # Compute updated filter counts
        event = photo.event
        all_photos = event.photos.all()
        sels = Selection.objects.filter(customer=customer, photo__event=event)
        selections_map = {str(s.photo_id): s.choice for s in sels}
        decided_ids = set(selections_map.keys())
        filter_counts = {"digital": 0, "both": 0, "reject": 0, "undecided": 0}
        for c in selections_map.values():
            if c in filter_counts:
                filter_counts[c] += 1
        filter_counts["undecided"] = sum(
            1 for p in all_photos if str(p.pk) not in decided_ids
        )
        total_count = all_photos.count()

        oob_context = {
            "event": event,
            "current_filter": "",
            "filter_counts": filter_counts,
            "total_count": total_count,
        }

        # Render filter tabs + summary OOB
        tabs_html = render_to_string(
            "gallery/partials/filter_tabs_oob.html",
            oob_context,
            request=request,
        )
        summary_html = render_to_string(
            "gallery/partials/selection_summary_oob.html",
            oob_context,
            request=request,
        )

        return HttpResponse(buttons_html + tabs_html + summary_html)
    return JsonResponse({"choice": current_choice, "print_size": current_print_size})


@login_required
def photographer_dashboard(request: HttpRequest) -> HttpResponse:
    if not _is_photographer(request.user):
        return redirect("home")
    events = Event.objects.prefetch_related("customers__user").all()
    return render(request, "gallery/photographer_dashboard.html", {"events": events})


@login_required
def manage_event(request: HttpRequest, event_id: str | None = None) -> HttpResponse:
    if not _is_photographer(request.user):
        return redirect("home")

    from .forms import EventForm

    if event_id:
        event = get_object_or_404(Event, pk=event_id)
    else:
        event = None

    if request.method == "POST":
        form = EventForm(request.POST, instance=event)
        if form.is_valid():
            form.save()
            return redirect("photographer_dashboard")
    else:
        form = EventForm(instance=event)

    return render(request, "gallery/manage_event.html", {"form": form, "event": event})


@login_required
def my_selections(request: HttpRequest) -> HttpResponse:
    customer = _get_customer(request.user)
    if not customer:
        return redirect("home")

    event_filter = request.GET.get("event", "")
    qs = Selection.objects.filter(customer=customer).exclude(choice="reject")
    if event_filter:
        qs = qs.filter(photo__event_id=event_filter)
    selections = qs.select_related("photo__event").order_by(
        "photo__event__name", "choice"
    )

    # Group by event, then by choice within each event
    from collections import OrderedDict

    grouped_by_event: dict[str, dict] = OrderedDict()
    for sel in selections:
        event = sel.photo.event
        event_key = str(event.pk)
        if event_key not in grouped_by_event:
            order = Order.objects.filter(event=event, customer=customer).first()
            grouped_by_event[event_key] = {
                "event": event,
                "order": order,
                "digital": [],
                "both": [],
            }
        grouped_by_event[event_key][sel.choice].append(sel)

    return render(
        request,
        "gallery/my_selections.html",
        {
            "grouped_by_event": list(grouped_by_event.values()),
            "event_filter": event_filter,
        },
    )


def _build_invoice(order: Order) -> Invoice:
    """Create or update an Invoice and its line items from the current order state."""
    from decimal import Decimal

    from jasonstudio.accounts.models import PhotographerProfile

    event = order.event
    customer = order.customer

    # Get or create invoice for this order
    invoice = order.invoices.order_by("-created").first()
    if not invoice:
        invoice = Invoice(order=order)

    selections = (
        Selection.objects.filter(customer=customer, photo__event=event)
        .exclude(choice="reject")
        .select_related("photo")
        .order_by("choice", "photo__sort_order")
    )

    digital_items = [s for s in selections if s.choice == "digital"]
    print_items = [s for s in selections if s.choice == "both"]

    photographer_fee = order.photographer_hours * order.photographer_rate

    # Build line items
    items = []
    items.append(
        {
            "sort_order": 0,
            "description": "Photography",
            "filename": "",
            "qty": order.photographer_hours,
            "unit_cost": order.photographer_rate,
            "price": photographer_fee,
        }
    )

    for i, s in enumerate(print_items):
        items.append(
            {
                "sort_order": i + 1,
                "description": f"Print & Digital — {s.get_print_size_display()}",
                "filename": s.photo.filename,
                "qty": Decimal("1"),
                "unit_cost": Decimal("0"),
                "price": Decimal("0"),
            }
        )

    digital_count = len(digital_items)
    if digital_count:
        items.append(
            {
                "sort_order": len(print_items) + 1,
                "description": "Digital images",
                "filename": "",
                "qty": Decimal(digital_count),
                "unit_cost": Decimal("0"),
                "price": Decimal("0"),
            }
        )

    # Compute totals
    subtotal = sum(item["price"] for item in items)
    deposit = order.deposit_amount
    photographer_profile = PhotographerProfile.objects.first()
    tax_rate = (
        Decimal(str(photographer_profile.tax_rate))
        if photographer_profile
        else Decimal("0")
    )
    tax_amount = subtotal * tax_rate / Decimal("100")
    amount_due = subtotal - deposit + tax_amount

    # Save invoice
    invoice.subtotal = subtotal
    invoice.deposit = deposit
    invoice.tax_rate = tax_rate
    invoice.tax_amount = tax_amount
    invoice.amount_due = amount_due
    invoice.save()

    # Replace line items
    invoice.line_items.all().delete()
    for item in items:
        InvoiceLineItem.objects.create(invoice=invoice, **item)

    return invoice


@login_required
def selection_invoice(request: HttpRequest, event_id: str) -> HttpResponse:
    customer = _get_customer(request.user)
    if not customer:
        return redirect("home")

    from jasonstudio.accounts.models import PhotographerProfile

    event = get_object_or_404(Event, pk=event_id, customers=customer)
    order = Order.objects.filter(event=event, customer=customer).first()
    if not order:
        return redirect("my_selections")

    invoice = _build_invoice(order)
    photographer = PhotographerProfile.objects.first()

    return render(
        request,
        "gallery/selection_invoice.html",
        {
            "event": event,
            "customer": customer,
            "order": order,
            "invoice": invoice,
            "photographer": photographer,
            "line_items": invoice.line_items.all(),
            "is_photographer_view": False,
        },
    )


@login_required
def photographer_invoice(
    request: HttpRequest, event_id: str, customer_id: str
) -> HttpResponse:
    """Photographer views the invoice for a customer's order."""
    if not _is_photographer(request.user):
        return redirect("home")

    from jasonstudio.accounts.models import Customer as CustomerModel
    from jasonstudio.accounts.models import PhotographerProfile

    event = get_object_or_404(Event, pk=event_id)
    customer = get_object_or_404(CustomerModel, pk=customer_id)
    order = get_object_or_404(Order, event=event, customer=customer)

    invoice = _build_invoice(order)
    photographer = PhotographerProfile.objects.first()

    return render(
        request,
        "gallery/selection_invoice.html",
        {
            "event": event,
            "customer": customer,
            "order": order,
            "invoice": invoice,
            "photographer": photographer,
            "line_items": invoice.line_items.all(),
            "is_photographer_view": True,
        },
    )


# --- Order Management (Photographer) ---


@login_required
def event_orders(request: HttpRequest, event_id: str) -> HttpResponse:
    if not _is_photographer(request.user):
        return redirect("home")

    event = get_object_or_404(Event, pk=event_id)

    # All customers with their quotation and order status
    customer_rows = []
    for customer in event.customers.all():
        quotation = Quotation.objects.filter(event=event, customer=customer).first()
        order = Order.objects.filter(event=event, customer=customer).first()
        selections = Selection.objects.filter(
            customer=customer, photo__event=event
        ).exclude(choice="reject")

        # Auto-create order if selections exist but no order yet
        if selections.exists() and not order:
            order, _ = Order.objects.get_or_create(event=event, customer=customer)

        customer_rows.append(
            {
                "customer": customer,
                "quotation": quotation,
                "order": order,
                "digital_count": selections.filter(choice="digital").count()
                if selections.exists()
                else 0,
                "both_count": selections.filter(choice="both").count()
                if selections.exists()
                else 0,
                "selection_total": selections.count() if selections.exists() else 0,
            }
        )

    return render(
        request,
        "gallery/event_orders.html",
        {"event": event, "customer_rows": customer_rows},
    )


@login_required
def customer_order_detail(
    request: HttpRequest, event_id: str, customer_id: str
) -> HttpResponse:
    if not _is_photographer(request.user):
        return redirect("home")

    event = get_object_or_404(Event, pk=event_id)
    from jasonstudio.accounts.models import Customer

    customer = get_object_or_404(Customer, pk=customer_id)
    order = get_object_or_404(Order, event=event, customer=customer)

    selections = (
        Selection.objects.filter(customer=customer, photo__event=event)
        .select_related("photo")
        .order_by("choice", "photo__sort_order")
    )

    digital_photos = [s.photo for s in selections if s.choice == "digital"]
    print_selections = [s for s in selections if s.choice == "both"]
    print_photos = [s.photo for s in print_selections]
    print_sizes_by_photo = {
        str(s.photo_id): s.get_print_size_display() for s in print_selections
    }
    rejected = Selection.objects.filter(
        customer=customer, photo__event=event, choice="reject"
    ).count()

    download_tokens = DownloadToken.objects.filter(
        order=order, customer=customer
    ).order_by("-created")

    return render(
        request,
        "gallery/customer_order_detail.html",
        {
            "event": event,
            "customer": customer,
            "order": order,
            "digital_photos": digital_photos,
            "print_photos": print_photos,
            "print_sizes_by_photo": print_sizes_by_photo,
            "digital_delivery_count": len(digital_photos) + len(print_photos),
            "rejected_count": rejected,
            "download_tokens": download_tokens,
        },
    )


@login_required
@require_POST
def update_order_status(
    request: HttpRequest, event_id: str, customer_id: str
) -> HttpResponse:
    if not _is_photographer(request.user):
        return redirect("home")

    event = get_object_or_404(Event, pk=event_id)
    from jasonstudio.accounts.models import Customer

    customer = get_object_or_404(Customer, pk=customer_id)
    order = get_object_or_404(Order, event=event, customer=customer)

    from django.utils import timezone as tz

    new_status = request.POST.get("status", "")
    update_fields = ["modified"]

    if new_status in {c.value for c in Order.Status}:
        order.status = new_status
        update_fields.append("status")
        # Record paid_at timestamp when marking as paid
        if new_status == Order.Status.PAID and not order.paid_at:
            order.paid_at = tz.now()
            update_fields.append("paid_at")

    if request.POST.get("update_fee"):
        from decimal import Decimal, InvalidOperation

        try:
            order.photographer_hours = Decimal(
                request.POST.get("photographer_hours", "0")
            )
        except InvalidOperation, ValueError:
            pass
        else:
            update_fields.append("photographer_hours")

        try:
            order.photographer_rate = Decimal(
                request.POST.get("photographer_rate", "0")
            )
        except InvalidOperation, ValueError:
            pass
        else:
            update_fields.append("photographer_rate")

        try:
            order.deposit_amount = Decimal(request.POST.get("deposit_amount", "0"))
        except InvalidOperation, ValueError:
            pass
        else:
            update_fields.append("deposit_amount")

    order.save(update_fields=update_fields)

    return redirect("customer_order_detail", event_id=event.pk, customer_id=customer.pk)


@login_required
def download_zip(
    request: HttpRequest, event_id: str, customer_id: str, zip_type: str
) -> HttpResponse:
    import zipfile

    if not _is_photographer(request.user):
        return redirect("home")

    event = get_object_or_404(Event, pk=event_id)
    from jasonstudio.accounts.models import Customer

    customer = get_object_or_404(Customer, pk=customer_id)
    order = get_object_or_404(Order, event=event, customer=customer)

    if not order.is_paid:
        return HttpResponse("Payment required before download.", status=403)

    selections = Selection.objects.filter(
        customer=customer, photo__event=event
    ).select_related("photo")

    if zip_type == "print":
        photos = [s.photo for s in selections if s.choice == "both"]
        filename = f"{event.name}_{customer}_print.zip"
    elif zip_type == "digital":
        photos = [s.photo for s in selections if s.choice in ("digital", "both")]
        filename = f"{event.name}_{customer}_digital.zip"
    else:
        return HttpResponse("Invalid zip type.", status=400)

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for photo in photos:
            if photo.original:
                zf.write(photo.original.path, photo.filename or photo.original.name)

    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def customer_download(request: HttpRequest, event_id: str) -> HttpResponse:
    """Customer downloads their digital photos (valid 30 days from payment)."""
    import zipfile

    customer = _get_customer(request.user)
    if not customer:
        return redirect("home")

    event = get_object_or_404(Event, pk=event_id, customers=customer)
    order = get_object_or_404(Order, event=event, customer=customer)

    if not order.download_available:
        if order.is_paid and not order.download_available:
            return HttpResponse(
                "Download link has expired (30 days from payment).", status=403
            )
        return HttpResponse("Payment required before download.", status=403)

    selections = (
        Selection.objects.filter(customer=customer, photo__event=event)
        .exclude(choice="reject")
        .select_related("photo")
    )

    photos = [s.photo for s in selections if s.choice in ("digital", "both")]

    # Increment download count
    from django.db.models import F

    Order.objects.filter(pk=order.pk).update(download_count=F("download_count") + 1)

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for photo in photos:
            if photo.original:
                zf.write(photo.original.path, photo.filename or photo.original.name)

    buffer.seek(0)
    filename = f"{event.name}_digital.zip"
    response = HttpResponse(buffer.read(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# ---------------------------------------------------------------------------
# Service catalog views
# ---------------------------------------------------------------------------


@login_required
def service_list(request: HttpRequest) -> HttpResponse:
    if not _is_photographer(request.user):
        return redirect("home")
    services = Service.objects.all()
    return render(request, "gallery/service_list.html", {"services": services})


@login_required
def service_edit(request: HttpRequest, service_id: str | None = None) -> HttpResponse:
    if not _is_photographer(request.user):
        return redirect("home")

    from decimal import Decimal, InvalidOperation

    service = get_object_or_404(Service, pk=service_id) if service_id else None

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        unit_type = request.POST.get("unit_type", Service.UnitType.PER_HOUR)
        try:
            default_rate = Decimal(request.POST.get("default_rate", "0"))
        except InvalidOperation, ValueError:
            default_rate = Decimal("0")
        sort_order = int(request.POST.get("sort_order", "0") or "0")
        is_active = request.POST.get("is_active") == "on"

        if not name:
            return render(
                request,
                "gallery/service_form.html",
                {
                    "service": service,
                    "error": "Name is required.",
                    "action": "Edit" if service else "Add",
                },
            )

        if service:
            service.name = name
            service.description = description
            service.unit_type = unit_type
            service.default_rate = default_rate
            service.sort_order = sort_order
            service.is_active = is_active
            service.save()
        else:
            Service.objects.create(
                name=name,
                description=description,
                unit_type=unit_type,
                default_rate=default_rate,
                sort_order=sort_order,
                is_active=is_active,
            )
        return redirect("service_list")

    return render(
        request,
        "gallery/service_form.html",
        {
            "service": service,
            "action": "Edit" if service else "Add",
            "unit_types": Service.UnitType.choices,
        },
    )


# ---------------------------------------------------------------------------
# Quotation views
# ---------------------------------------------------------------------------


def _build_quotation_totals(quotation: Quotation) -> None:
    """Recalculate quotation subtotal, tax, and total from its line items."""
    from decimal import Decimal

    from jasonstudio.accounts.models import PhotographerProfile

    subtotal = sum((item.price for item in quotation.line_items.all()), Decimal("0"))
    photographer_profile = PhotographerProfile.objects.first()
    tax_rate = (
        Decimal(str(photographer_profile.tax_rate))
        if photographer_profile
        else Decimal("0")
    )
    tax_amount = subtotal * tax_rate / Decimal("100")
    total = subtotal - quotation.deposit_amount + tax_amount

    quotation.subtotal = subtotal
    quotation.tax_rate = tax_rate
    quotation.tax_amount = tax_amount
    quotation.total = total
    quotation.save(
        update_fields=["subtotal", "tax_rate", "tax_amount", "total", "modified"]
    )


@login_required
def quotation_edit(
    request: HttpRequest, event_id: str, customer_id: str
) -> HttpResponse:
    """Photographer creates/edits a quotation for a customer on an event."""
    if not _is_photographer(request.user):
        return redirect("home")

    from decimal import Decimal, InvalidOperation

    from jasonstudio.accounts.models import Customer as CustomerModel

    event = get_object_or_404(Event, pk=event_id)
    customer = get_object_or_404(CustomerModel, pk=customer_id)

    quotation, _created = Quotation.objects.get_or_create(
        event=event,
        customer=customer,
    )

    if request.method == "POST":
        # Save deposit and validity
        try:
            quotation.deposit_amount = Decimal(request.POST.get("deposit_amount", "0"))
        except InvalidOperation, ValueError:
            pass
        valid_until = request.POST.get("valid_until", "").strip()
        if valid_until:
            import datetime

            try:
                quotation.valid_until = datetime.date.fromisoformat(valid_until)
            except ValueError:
                pass
        else:
            quotation.valid_until = None
        quotation.notes = request.POST.get("notes", "").strip()
        quotation.save(
            update_fields=["deposit_amount", "valid_until", "notes", "modified"]
        )

        # Replace line items from form
        quotation.line_items.all().delete()
        idx = 0
        while True:
            desc = request.POST.get(f"item_{idx}_description", "").strip()
            if not desc and idx > 0:
                break
            if desc:
                try:
                    qty = Decimal(request.POST.get(f"item_{idx}_qty", "1"))
                except InvalidOperation, ValueError:
                    qty = Decimal("1")
                try:
                    unit_cost = Decimal(request.POST.get(f"item_{idx}_unit_cost", "0"))
                except InvalidOperation, ValueError:
                    unit_cost = Decimal("0")
                price = qty * unit_cost
                service_id = request.POST.get(f"item_{idx}_service", "")
                service = None
                if service_id:
                    service = Service.objects.filter(pk=service_id).first()
                QuotationLineItem.objects.create(
                    quotation=quotation,
                    service=service,
                    sort_order=idx,
                    description=desc,
                    qty=qty,
                    unit_cost=unit_cost,
                    price=price,
                )
            idx += 1
            if idx > 50:  # safety limit
                break

        _build_quotation_totals(quotation)
        return redirect("quotation_view", event_id=event.pk, customer_id=customer.pk)

    services = Service.objects.filter(is_active=True)
    return render(
        request,
        "gallery/quotation_form.html",
        {
            "event": event,
            "customer": customer,
            "quotation": quotation,
            "line_items": quotation.line_items.all(),
            "services": services,
        },
    )


@login_required
def quotation_view(
    request: HttpRequest, event_id: str, customer_id: str
) -> HttpResponse:
    """View a quotation (photographer side)."""
    if not _is_photographer(request.user):
        return redirect("home")

    from jasonstudio.accounts.models import Customer as CustomerModel
    from jasonstudio.accounts.models import PhotographerProfile

    event = get_object_or_404(Event, pk=event_id)
    customer = get_object_or_404(CustomerModel, pk=customer_id)
    quotation = get_object_or_404(Quotation, event=event, customer=customer)
    photographer = PhotographerProfile.objects.first()

    return render(
        request,
        "gallery/quotation_detail.html",
        {
            "event": event,
            "customer": customer,
            "quotation": quotation,
            "line_items": quotation.line_items.all(),
            "photographer": photographer,
            "is_photographer_view": True,
        },
    )


@login_required
@require_POST
def quotation_accept(
    request: HttpRequest, event_id: str, customer_id: str
) -> HttpResponse:
    """Photographer accepts a quotation on behalf of the customer."""
    if not _is_photographer(request.user):
        return redirect("home")

    from jasonstudio.accounts.models import Customer as CustomerModel

    event = get_object_or_404(Event, pk=event_id)
    customer = get_object_or_404(CustomerModel, pk=customer_id)
    quotation = get_object_or_404(Quotation, event=event, customer=customer)

    if quotation.status not in (Quotation.Status.DRAFT, Quotation.Status.SENT):
        return redirect("quotation_view", event_id=event.pk, customer_id=customer.pk)

    quotation.accept(by="photographer")
    return redirect("customer_order_detail", event_id=event.pk, customer_id=customer.pk)


@login_required
def customer_quotation_view(request: HttpRequest, event_id: str) -> HttpResponse:
    """Customer views their quotation."""
    customer = _get_customer(request.user)
    if not customer:
        return redirect("home")

    from jasonstudio.accounts.models import PhotographerProfile

    event = get_object_or_404(Event, pk=event_id, customers=customer)
    quotation = get_object_or_404(Quotation, event=event, customer=customer)
    photographer = PhotographerProfile.objects.first()

    return render(
        request,
        "gallery/quotation_detail.html",
        {
            "event": event,
            "customer": customer,
            "quotation": quotation,
            "line_items": quotation.line_items.all(),
            "photographer": photographer,
            "is_photographer_view": False,
        },
    )


@login_required
@require_POST
def customer_quotation_accept(request: HttpRequest, event_id: str) -> HttpResponse:
    """Customer accepts a quotation."""
    customer = _get_customer(request.user)
    if not customer:
        return redirect("home")

    event = get_object_or_404(Event, pk=event_id, customers=customer)
    quotation = get_object_or_404(Quotation, event=event, customer=customer)

    if quotation.status not in (Quotation.Status.SENT, Quotation.Status.DRAFT):
        return redirect("customer_quotation_view", event_id=event.pk)
    if quotation.is_expired:
        return redirect("customer_quotation_view", event_id=event.pk)

    quotation.accept(by="customer")
    return redirect("my_selections")


@login_required
@require_POST
def customer_quotation_decline(request: HttpRequest, event_id: str) -> HttpResponse:
    """Customer declines a quotation."""
    customer = _get_customer(request.user)
    if not customer:
        return redirect("home")

    event = get_object_or_404(Event, pk=event_id, customers=customer)
    quotation = get_object_or_404(Quotation, event=event, customer=customer)

    if quotation.status in (Quotation.Status.SENT, Quotation.Status.DRAFT):
        quotation.status = Quotation.Status.DECLINED
        quotation.save(update_fields=["status", "modified"])

    return redirect("customer_quotation_view", event_id=event.pk)


# --- Share Link ---


@login_required
@require_POST
def create_share_link(request: HttpRequest, event_id: str) -> HttpResponse:
    """Customer generates a share code for their paid order."""
    customer = _get_customer(request.user)
    if not customer:
        return redirect("home")

    event = get_object_or_404(Event, pk=event_id, customers=customer)
    order = get_object_or_404(Order, event=event, customer=customer)

    if not order.download_available:
        return HttpResponse("Download not available.", status=403)

    # Delete any existing share link and create a fresh one with a new code
    ShareLink.objects.filter(order=order).delete()
    ShareLink.objects.create(order=order, code=ShareLink.generate_code())

    return redirect("my_selections")


@login_required
@require_POST
def deactivate_share_link(request: HttpRequest, event_id: str) -> HttpResponse:
    """Customer or photographer deactivates a share code."""
    customer = _get_customer(request.user)
    is_photographer = _is_photographer(request.user)

    if customer:
        event = get_object_or_404(Event, pk=event_id, customers=customer)
        order = get_object_or_404(Order, event=event, customer=customer)
    elif is_photographer:
        event = get_object_or_404(Event, pk=event_id)
        from jasonstudio.accounts.models import Customer as CustomerModel

        customer_id = request.POST.get("customer_id")
        cust = get_object_or_404(CustomerModel, pk=customer_id)
        order = get_object_or_404(Order, event=event, customer=cust)
    else:
        return redirect("home")

    share_link = getattr(order, "share_link", None)
    if share_link:
        share_link.is_active = False
        share_link.save(update_fields=["is_active"])

    if is_photographer:
        return redirect("customer_order_detail", event_id=event.pk, customer_id=cust.pk)
    return redirect("my_selections")


def shared_download_page(request: HttpRequest, code: str) -> HttpResponse:
    """Public page where friends can download via share code."""
    try:
        share_link = ShareLink.objects.get(code=code.upper())
    except ShareLink.DoesNotExist:
        return render(request, "gallery/shared_expired.html", {"code": code})

    if not share_link.is_valid:
        return render(request, "gallery/shared_expired.html", {"code": code})

    order = share_link.order
    event = order.event

    return render(
        request,
        "gallery/shared_download.html",
        {"share_link": share_link, "event": event, "order": order},
    )


def shared_download_file(request: HttpRequest, code: str) -> HttpResponse:
    """Public download endpoint via share code."""
    import zipfile

    from django.db.models import F

    try:
        share_link = ShareLink.objects.get(code=code.upper())
    except ShareLink.DoesNotExist:
        return HttpResponse("Invalid share code.", status=404)

    if not share_link.is_valid:
        return HttpResponse("This share link is no longer valid.", status=403)

    order = share_link.order
    event = order.event
    customer = order.customer

    selections = (
        Selection.objects.filter(customer=customer, photo__event=event)
        .exclude(choice="reject")
        .select_related("photo")
    )

    photos = [s.photo for s in selections if s.choice in ("digital", "both")]

    # Increment counts
    ShareLink.objects.filter(pk=share_link.pk).update(
        download_count=F("download_count") + 1
    )
    Order.objects.filter(pk=order.pk).update(download_count=F("download_count") + 1)

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for photo in photos:
            if photo.original:
                zf.write(photo.original.path, photo.filename or photo.original.name)

    buffer.seek(0)
    filename = f"{event.name}_digital.zip"
    response = HttpResponse(buffer.read(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# --- Download Token (email-based download) ---


@login_required
@require_POST
def send_download_email(
    request: HttpRequest, event_id: str, customer_id: str
) -> HttpResponse:
    """Photographer sends a download link to the customer's email."""
    from django.contrib import messages
    from django.core.mail import send_mail
    from django.template.loader import render_to_string

    if not _is_photographer(request.user):
        return redirect("home")

    from jasonstudio.accounts.models import Customer as CustomerModel

    event = get_object_or_404(Event, pk=event_id)
    customer = get_object_or_404(CustomerModel, pk=customer_id)
    order = get_object_or_404(Order, event=event, customer=customer)

    if not order.is_paid:
        messages.error(request, "Order must be paid before sending a download link.")
        return redirect(
            "customer_order_detail", event_id=event.pk, customer_id=customer.pk
        )

    # Resolve the customer's email
    email = customer.user.email
    if not email:
        messages.error(
            request,
            "This customer has no email address. "
            "Add one before sending a download link.",
        )
        return redirect(
            "customer_order_detail", event_id=event.pk, customer_id=customer.pk
        )

    # Create the token
    token = DownloadToken.objects.create(
        order=order,
        customer=customer,
        sent_to_email=email,
    )

    photographer = PhotographerProfile.objects.first()
    download_url = request.build_absolute_uri(f"/download/{token.token}/")

    subject = render_to_string(
        "accounts/download_email_subject.txt",
        {"event_name": event.name},
    ).strip()

    body = render_to_string(
        "accounts/download_email.txt",
        {
            "customer_name": customer.user.get_full_name() or customer.user.username,
            "event_name": event.name,
            "download_url": download_url,
            "expires_at": token.expires_at,
            "photographer_name": (photographer.business_name if photographer else "us"),
        },
    )

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
    if photographer and photographer.email:
        from_email = photographer.email

    send_mail(subject, body, from_email, [email])

    token.sent_at = timezone.now()
    token.save(update_fields=["sent_at"])

    messages.success(request, f"Download link sent to {email}.")
    return redirect("customer_order_detail", event_id=event.pk, customer_id=customer.pk)


def token_download_page(request: HttpRequest, token: str) -> HttpResponse:
    """Public page where customer downloads their photos via a token link."""
    dl_token = get_object_or_404(DownloadToken, token=token)

    if dl_token.is_expired:
        return render(request, "gallery/token_expired.html", {"token": dl_token})

    order = dl_token.order
    event = order.event

    selections = (
        Selection.objects.filter(customer=dl_token.customer, photo__event=event)
        .exclude(choice="reject")
        .select_related("photo")
    )

    return render(
        request,
        "gallery/token_download.html",
        {
            "token": dl_token,
            "order": order,
            "event": event,
            "photo_count": selections.count(),
        },
    )


def token_download_file(request: HttpRequest, token: str) -> HttpResponse:
    """Serve the zip file for a valid download token."""
    import zipfile

    dl_token = get_object_or_404(DownloadToken, token=token)

    if dl_token.is_expired:
        return render(request, "gallery/token_expired.html", {"token": dl_token})

    order = dl_token.order
    event = order.event

    photos = [
        s.photo
        for s in Selection.objects.filter(
            customer=dl_token.customer, photo__event=event
        )
        .exclude(choice="reject")
        .select_related("photo")
    ]

    # Increment counts
    dl_token.download_count += 1
    dl_token.save(update_fields=["download_count"])
    Order.objects.filter(pk=order.pk).update(download_count=F("download_count") + 1)

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for photo in photos:
            if photo.original:
                zf.write(photo.original.path, photo.filename or photo.original.name)

    buffer.seek(0)
    filename = f"{event.name}_photos.zip"
    response = HttpResponse(buffer.read(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
