from io import BytesIO
from pathlib import Path

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
    Delivery,
    DeliveryItem,
    DownloadToken,
    Invoice,
    InvoiceLineItem,
    Order,
    Payment,
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
    from jasonstudio.accounts.models import Customer as CustomerModel

    own_customer = _get_customer(request.user)
    is_photographer = _is_photographer(request.user)

    if is_photographer:
        event = get_object_or_404(Event, pk=event_id)
    elif own_customer:
        event = get_object_or_404(
            Event, pk=event_id, customers=own_customer, status="published"
        )
    else:
        return redirect("home")

    # Perspective switcher: photographer can view as a specific customer
    view_as_customer = None
    event_customers: list[CustomerModel] = []
    if is_photographer:
        event_customers = list(event.customers.all())
        view_as_id = request.GET.get("view_as", "")
        if view_as_id:
            view_as_customer = CustomerModel.objects.filter(
                pk=view_as_id, events=event
            ).first()

    # The "active customer" for loading selections
    active_customer = view_as_customer if is_photographer else own_customer

    all_photos = event.photos.all()
    selections = {}
    print_sizes_map = {}
    if active_customer:
        for sel in Selection.objects.filter(
            customer=active_customer, photo__event=event
        ):
            selections[str(sel.photo_id)] = sel.choice
            print_sizes_map[str(sel.photo_id)] = sel.print_size

    # Filter by selection choice
    filter_by = request.GET.get("filter", "")
    valid_filters = {"digital", "both", "reject", "undecided"}
    if filter_by not in valid_filters:
        filter_by = ""

    if filter_by and active_customer:
        if filter_by == "undecided":
            decided_ids = set(selections.keys())
            photos = [p for p in all_photos if str(p.pk) not in decided_ids]
        else:
            photos = [p for p in all_photos if selections.get(str(p.pk)) == filter_by]
    else:
        photos = all_photos

    # Counts for filter tabs
    filter_counts = {"digital": 0, "both": 0, "reject": 0, "undecided": 0}
    if active_customer:
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
            "is_customer": own_customer is not None,
            "active_customer": active_customer,
            "view_as_customer": view_as_customer,
            "event_customers": event_customers,
            "current_filter": filter_by,
            "filter_counts": filter_counts,
            "total_count": len(all_photos)
            if isinstance(all_photos, list)
            else all_photos.count(),
        },
    )


@login_required
@require_POST
def select_all_digital(request: HttpRequest, event_id: str) -> HttpResponse:
    """Mark all event photos as 'Digital' for a specific customer or all."""
    from django.contrib import messages

    from jasonstudio.accounts.models import Customer

    if not _is_photographer(request.user):
        return redirect("home")

    event = get_object_or_404(Event, pk=event_id)
    photos = list(event.photos.all())

    if not photos:
        messages.warning(request, "No photos in this event.")
        return redirect("event_gallery", event_id=event.pk)

    # If acting on behalf of a specific customer
    view_as_id = request.POST.get("view_as", "")
    if view_as_id:
        target_customer = Customer.objects.filter(pk=view_as_id, events=event).first()
        if not target_customer:
            messages.error(request, "Customer not found.")
            return redirect("event_gallery", event_id=event.pk)
        target_customers = [target_customer]
    else:
        target_customers = list(Customer.objects.filter(orders__event=event).distinct())

    if not target_customers:
        messages.warning(
            request,
            "No customers with orders for this event. Create an order first.",
        )
        return redirect("event_gallery", event_id=event.pk)

    created_count = 0
    for customer in target_customers:
        selections_to_create = [
            Selection(
                photo=photo,
                customer=customer,
                choice=Selection.Choice.DIGITAL,
            )
            for photo in photos
        ]
        objs = Selection.objects.bulk_create(
            selections_to_create, ignore_conflicts=True
        )
        created_count += len(objs)

    customer_names = ", ".join(
        c.user.get_full_name() or c.user.username for c in target_customers
    )
    messages.success(
        request,
        f"Marked {len(photos)} photos as Digital "
        f"for {customer_names}. "
        f"{created_count} new selection(s) created.",
    )
    from django.urls import reverse

    url = reverse("event_gallery", kwargs={"event_id": event.pk})
    if view_as_id:
        url += f"?view_as={view_as_id}"
    return redirect(url)


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
    from jasonstudio.accounts.models import Customer as CustomerModel

    customer = _get_customer(request.user)

    # Photographer acting on behalf of a customer
    if not customer and _is_photographer(request.user):
        on_behalf_of = request.POST.get("on_behalf_of", "")
        if on_behalf_of:
            customer = CustomerModel.objects.filter(pk=on_behalf_of).first()

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

        # Pass view_as_customer back for photographer acting on behalf
        on_behalf_of = request.POST.get("on_behalf_of", "")
        view_as_customer = None
        if on_behalf_of:
            view_as_customer = CustomerModel.objects.filter(pk=on_behalf_of).first()

        # Render selection buttons
        buttons_html = render_to_string(
            "gallery/partials/selection_buttons.html",
            {
                "photo": photo,
                "current_choice": current_choice,
                "current_print_size": current_print_size,
                "print_sizes": Selection.PrintSize.choices,
                "view_as_customer": view_as_customer,
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
    events = list(Event.objects.prefetch_related("customers__user").all())

    # Annotate each event with order summary for badge display
    for event in events:
        orders = Order.objects.filter(event=event)
        event.all_paid = orders.exists() and all(o.is_paid for o in orders)
        event.all_delivered = orders.exists() and all(
            o.status == Order.Status.DELIVERED for o in orders
        )
        event.has_orders = orders.exists()

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
        # Merge primary_customer + friends into the customers M2M field
        post_data = request.POST.copy()
        customer_ids = list(request.POST.getlist("friends"))
        primary = request.POST.get("primary_customer", "")
        if primary and primary not in customer_ids:
            customer_ids.insert(0, primary)
        post_data.setlist("customers", customer_ids)

        form = EventForm(post_data, instance=event)
        if form.is_valid():
            form.save()
            return redirect("photographer_dashboard")
    else:
        form = EventForm(instance=event)

    # Determine primary customer and friends for the template
    primary_customer_id = ""
    friend_ids = set()
    if event:
        customer_ids = [str(c.pk) for c in event.customers.all()]
        if customer_ids:
            primary_customer_id = customer_ids[0]
            friend_ids = {cid for cid in customer_ids[1:]}

    return render(
        request,
        "gallery/manage_event.html",
        {
            "form": form,
            "event": event,
            "primary_customer_id": primary_customer_id,
            "friend_ids": friend_ids,
        },
    )


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
    invoice = order.invoices.order_by("-date_created").first()
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

    quotation = order.quotation

    # Build line items from the accepted quotation
    items = []
    for qi in quotation.line_items.all():
        items.append(
            {
                "sort_order": qi.sort_order,
                "description": qi.description,
                "filename": "",
                "qty": qi.qty,
                "unit_cost": qi.unit_cost,
                "price": qi.price,
            }
        )

    next_sort = (items[-1]["sort_order"] + 1) if items else 0

    for i, s in enumerate(print_items):
        items.append(
            {
                "sort_order": next_sort + i,
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
                "sort_order": next_sort + len(print_items),
                "description": "Digital images",
                "filename": "",
                "qty": Decimal(digital_count),
                "unit_cost": Decimal("0"),
                "price": Decimal("0"),
            }
        )

    # Compute totals
    subtotal = sum(item["price"] for item in items)
    deposit = quotation.deposit_amount
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
    """Printable order document."""
    if not _is_photographer(request.user):
        return redirect("home")

    event = get_object_or_404(Event, pk=event_id)
    from jasonstudio.accounts.models import Customer

    customer = get_object_or_404(Customer, pk=customer_id)
    order = get_object_or_404(Order, event=event, customer=customer)

    quotation = order.quotation
    quotation_line_items = quotation.line_items.all() if quotation else []
    photographer = PhotographerProfile.objects.first()

    return render(
        request,
        "gallery/customer_order_detail.html",
        {
            "event": event,
            "customer": customer,
            "order": order,
            "quotation": quotation,
            "quotation_line_items": quotation_line_items,
            "photographer": photographer,
        },
    )


def _scaffold_delivery_items(
    delivery: Delivery,
    digital_count: int,
    print_count: int,
) -> None:
    """Create default line items on a delivery from order selection counts."""
    items: list[DeliveryItem] = []
    idx = 0
    if digital_count:
        items.append(
            DeliveryItem(
                delivery=delivery,
                sort_order=idx,
                description=f"Digital images ({digital_count})",
                qty=digital_count,
            )
        )
        idx += 1
    if print_count:
        items.append(
            DeliveryItem(
                delivery=delivery,
                sort_order=idx,
                description=f"Print & Digital images ({print_count})",
                qty=print_count,
            )
        )
    if items:
        DeliveryItem.objects.bulk_create(items)


def _build_mailto_url(
    *,
    email: str,
    download_url: str,
    customer_name: str,
    event_name: str,
    photographer: PhotographerProfile | None,
) -> str:
    """Render the photographer's email template into a mailto: URL."""
    from urllib.parse import quote as urlquote

    photographer_name = photographer.business_name if photographer else "Jason Studio"
    subject_template = (
        photographer.email_subject_template
        if photographer
        else 'Your photos from "{event_name}" are ready'
    )
    body_template = (
        photographer.email_body_template
        if photographer
        else (
            "Hi {customer_name},\n\n"
            'Your photos from "{event_name}" are ready for download.\n\n'
            "{download_url}\n\n"
            "Thank you for choosing {photographer_name}."
        )
    )
    replacements = {
        "customer_name": customer_name,
        "event_name": event_name,
        "photographer_name": photographer_name,
        "download_url": download_url,
    }
    subject = subject_template
    body = body_template
    for key, val in replacements.items():
        subject = subject.replace(f"{{{key}}}", val)
        body = body.replace(f"{{{key}}}", val)
    return f"mailto:{email}?subject={urlquote(subject)}&body={urlquote(body)}"


@login_required
def order_fulfilment(
    request: HttpRequest, event_id: str, customer_id: str
) -> HttpResponse:
    """Fulfilment page: payment, delivery, and downloads."""
    if not _is_photographer(request.user):
        return redirect("home")

    event = get_object_or_404(Event, pk=event_id)
    from jasonstudio.accounts.models import Customer

    customer = get_object_or_404(Customer, pk=customer_id)
    order = get_object_or_404(Order, event=event, customer=customer)

    selections = Selection.objects.filter(
        customer=customer, photo__event=event
    ).exclude(choice="reject")
    print_photos = [
        s.photo for s in selections.filter(choice="both").select_related("photo")
    ]

    download_tokens = DownloadToken.objects.filter(
        order=order, customer=customer
    ).order_by("-date_created")

    photographer = PhotographerProfile.objects.first()
    customer_name = customer.user.get_full_name() or customer.user.username

    # Check if Google Drive is configured
    from .google_drive import is_drive_configured

    drive_configured = is_drive_configured()

    # Delivery history for this order
    deliveries = order.deliveries.prefetch_related("items").all()

    # mailto with token-based download link
    mailto_url = ""
    if customer.user.email and download_tokens:
        latest_token = download_tokens.first()
        if latest_token and latest_token.is_valid:
            token_url = request.build_absolute_uri(f"/download/{latest_token.token}/")
            mailto_url = _build_mailto_url(
                email=customer.user.email,
                download_url=token_url,
                customer_name=customer_name,
                event_name=event.name,
                photographer=photographer,
            )

    # Attach a mailto URL to each delivery that has a URL
    for d in deliveries:
        if d.url and customer.user.email:
            d.mailto_url = _build_mailto_url(
                email=customer.user.email,
                download_url=d.url,
                customer_name=customer_name,
                event_name=event.name,
                photographer=photographer,
            )
        else:
            d.mailto_url = ""

    return render(
        request,
        "gallery/order_fulfilment.html",
        {
            "event": event,
            "customer": customer,
            "order": order,
            "photographer": photographer,
            "print_photos": print_photos,
            "download_tokens": download_tokens,
            "deliveries": deliveries,
            "mailto_url": mailto_url,
            "drive_configured": drive_configured,
        },
    )


@login_required
def delivery_detail(request: HttpRequest, delivery_id: str) -> HttpResponse:
    """View or edit a delivery note."""
    if not _is_photographer(request.user):
        return redirect("home")

    delivery = get_object_or_404(
        Delivery.objects.prefetch_related("items"),
        pk=delivery_id,
    )
    order = delivery.order
    event = order.event
    customer = order.customer

    if request.method == "POST":
        delivery.notes = request.POST.get("notes", "").strip()
        url = request.POST.get("url", "").strip()
        delivery.url = url
        delivery.save(update_fields=["notes", "url", "date_modified"])

        # Replace line items from form
        delivery.items.all().delete()
        idx = 0
        while True:
            desc = request.POST.get(f"item_{idx}_description", "").strip()
            if not desc and idx > 0:
                break
            if desc:
                qty = int(request.POST.get(f"item_{idx}_qty", "1") or "1")
                DeliveryItem.objects.create(
                    delivery=delivery,
                    sort_order=idx,
                    description=desc,
                    qty=max(qty, 1),
                )
            idx += 1
            if idx > 50:
                break

        return redirect(
            "order_fulfilment",
            event_id=event.pk,
            customer_id=customer.pk,
        )

    from .google_drive import is_drive_configured

    return render(
        request,
        "gallery/delivery_detail.html",
        {
            "delivery": delivery,
            "items": delivery.items.all(),
            "order": order,
            "event": event,
            "customer": customer,
            "drive_configured": is_drive_configured(),
        },
    )


@require_POST
@login_required
def delivery_delete(request: HttpRequest, delivery_id: str) -> HttpResponse:
    """Delete a delivery note and update the order status."""
    if not _is_photographer(request.user):
        return redirect("home")

    delivery = get_object_or_404(Delivery, pk=delivery_id)
    order = delivery.order
    event = order.event
    customer = order.customer

    delivery.delete()
    order.update_delivery_status()

    return redirect("order_fulfilment", event_id=event.pk, customer_id=customer.pk)


@login_required
def delivery_create(
    request: HttpRequest, event_id: str, customer_id: str
) -> HttpResponse:
    """Photographer creates a new manual delivery note."""
    if not _is_photographer(request.user):
        return redirect("home")

    from jasonstudio.accounts.models import Customer as CustomerModel

    event = get_object_or_404(Event, pk=event_id)
    customer = get_object_or_404(CustomerModel, pk=customer_id)
    order = get_object_or_404(Order, event=event, customer=customer)

    if request.method == "POST":
        method = request.POST.get("method", Delivery.Method.MANUAL)
        if method not in {c.value for c in Delivery.Method}:
            method = Delivery.Method.MANUAL
        notes = request.POST.get("notes", "").strip()
        url = request.POST.get("url", "").strip()

        delivery = Delivery.objects.create(
            order=order,
            method=method,
            url=url,
            notes=notes,
        )

        # Save line items from form
        idx = 0
        while True:
            desc = request.POST.get(f"item_{idx}_description", "").strip()
            if not desc and idx > 0:
                break
            if desc:
                qty = int(request.POST.get(f"item_{idx}_qty", "1") or "1")
                DeliveryItem.objects.create(
                    delivery=delivery,
                    sort_order=idx,
                    description=desc,
                    qty=max(qty, 1),
                )
            idx += 1
            if idx > 50:
                break

        order.update_delivery_status()
        return redirect(
            "order_fulfilment",
            event_id=event.pk,
            customer_id=customer.pk,
        )

    # Scaffold default items from order selections
    selections = Selection.objects.filter(
        customer=customer, photo__event=event
    ).exclude(choice="reject")
    digital_count = selections.filter(choice__in=["digital", "both"]).count()
    print_count = selections.filter(choice="both").count()

    scaffold_items = []
    idx = 0
    if digital_count:
        scaffold_items.append(
            {
                "sort_order": idx,
                "description": f"Digital images ({digital_count})",
                "qty": digital_count,
            }
        )
        idx += 1
    if print_count:
        scaffold_items.append(
            {
                "sort_order": idx,
                "description": f"Print & Digital images ({print_count})",
                "qty": print_count,
            }
        )

    return render(
        request,
        "gallery/delivery_form.html",
        {
            "event": event,
            "customer": customer,
            "order": order,
            "scaffold_items": scaffold_items,
            "delivery_methods": Delivery.Method.choices,
        },
    )


@login_required
@require_POST
def mark_order_delivered(
    request: HttpRequest, event_id: str, customer_id: str
) -> HttpResponse:
    """Photographer marks order as fully delivered."""
    if not _is_photographer(request.user):
        return redirect("home")

    from jasonstudio.accounts.models import Customer as CustomerModel

    event = get_object_or_404(Event, pk=event_id)
    customer = get_object_or_404(CustomerModel, pk=customer_id)
    order = get_object_or_404(Order, event=event, customer=customer)

    order.status = Order.Status.DELIVERED
    order.save(update_fields=["status", "date_modified"])

    return redirect("order_fulfilment", event_id=event.pk, customer_id=customer.pk)


@login_required
@require_POST
def reopen_order_delivery(
    request: HttpRequest, event_id: str, customer_id: str
) -> HttpResponse:
    """Photographer reopens a delivered order (undo mark as delivered)."""
    if not _is_photographer(request.user):
        return redirect("home")

    from jasonstudio.accounts.models import Customer as CustomerModel

    event = get_object_or_404(Event, pk=event_id)
    customer = get_object_or_404(CustomerModel, pk=customer_id)
    order = get_object_or_404(Order, event=event, customer=customer)

    # Recalculate based on actual deliveries
    if order.deliveries.exists():
        order.status = Order.Status.PARTIALLY_DELIVERED
    else:
        order.status = Order.Status.IN_PROGRESS
    order.save(update_fields=["status", "date_modified"])

    return redirect("order_fulfilment", event_id=event.pk, customer_id=customer.pk)


@login_required
def record_payment(
    request: HttpRequest, event_id: str, customer_id: str
) -> HttpResponse:
    """Photographer records a payment against the customer's invoice."""
    if not _is_photographer(request.user):
        return redirect("home")

    from decimal import Decimal, InvalidOperation

    from jasonstudio.accounts.models import Customer as CustomerModel

    event = get_object_or_404(Event, pk=event_id)
    customer = get_object_or_404(CustomerModel, pk=customer_id)
    order = get_object_or_404(Order, event=event, customer=customer)
    invoice = _build_invoice(order)

    # Don't allow duplicate payment if already paid
    if invoice.status == Invoice.Status.PAID:
        return redirect(
            "payment_receipt",
            event_id=event.pk,
            customer_id=customer.pk,
        )

    error = ""
    if request.method == "POST":
        import datetime

        payment_date = request.POST.get("date", "").strip()
        try:
            amount = Decimal(request.POST.get("amount", "0"))
        except InvalidOperation, ValueError:
            amount = Decimal("0")
        method = request.POST.get("method", Payment.Method.ETRANSFER)
        reference = request.POST.get("reference", "").strip()
        notes = request.POST.get("notes", "").strip()

        if amount <= 0:
            error = "Amount must be greater than zero."
        elif method not in {c.value for c in Payment.Method}:
            error = "Invalid payment method."
        else:
            payment = Payment(
                invoice=invoice,
                amount=amount,
                method=method,
                reference=reference,
                notes=notes,
            )
            if payment_date:
                try:
                    payment.date = datetime.date.fromisoformat(payment_date)
                except ValueError:
                    pass
            payment.full_clean()
            payment.save()
            return redirect(
                "payment_receipt",
                event_id=event.pk,
                customer_id=customer.pk,
            )

    photographer = PhotographerProfile.objects.first()

    return render(
        request,
        "gallery/record_payment.html",
        {
            "event": event,
            "customer": customer,
            "order": order,
            "invoice": invoice,
            "photographer": photographer,
            "payment_methods": Payment.Method.choices,
            "error": error,
        },
    )


@login_required
def payment_receipt(
    request: HttpRequest, event_id: str, customer_id: str
) -> HttpResponse:
    """Display a printable receipt for the customer."""
    if not _is_photographer(request.user):
        return redirect("home")

    from jasonstudio.accounts.models import Customer as CustomerModel

    event = get_object_or_404(Event, pk=event_id)
    customer = get_object_or_404(CustomerModel, pk=customer_id)
    order = get_object_or_404(Order, event=event, customer=customer)
    invoice = order.invoices.order_by("-date_created").first()
    if not invoice:
        return redirect(
            "customer_order_detail", event_id=event.pk, customer_id=customer.pk
        )

    payment = invoice.payments.order_by("date_created").first()
    if not payment:
        return redirect(
            "customer_order_detail", event_id=event.pk, customer_id=customer.pk
        )

    photographer = PhotographerProfile.objects.first()

    return render(
        request,
        "gallery/payment_receipt.html",
        {
            "event": event,
            "customer": customer,
            "order": order,
            "invoice": invoice,
            "payment": payment,
            "photographer": photographer,
        },
    )


@login_required
def event_planning_notes(request: HttpRequest, event_id: str) -> HttpResponse:
    """Photographer views/edits internal planning notes for an event."""
    if not _is_photographer(request.user):
        return redirect("home")

    event = get_object_or_404(Event, pk=event_id)

    if request.method == "POST":
        event.planning_notes = request.POST.get("planning_notes", "")
        event.save(update_fields=["planning_notes", "modified"])
        return redirect("photographer_dashboard")

    return render(
        request,
        "gallery/event_notes.html",
        {"event": event},
    )


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
def download_event_photos(request: HttpRequest, event_id: str) -> HttpResponse:
    """Photographer downloads all original photos for an event as a zip."""
    import zipfile

    if not _is_photographer(request.user):
        return redirect("home")

    event = get_object_or_404(Event, pk=event_id)
    photos = event.photos.all().order_by("sort_order")

    if not photos.exists():
        return HttpResponse("No photos in this event.", status=404)

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for photo in photos:
            if photo.original:
                zf.write(photo.original.path, photo.filename or photo.original.name)

    buffer.seek(0)
    filename = f"{event.name}_all_photos.zip"
    response = HttpResponse(buffer.read(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_POST
def upload_delivery_to_drive(request: HttpRequest, delivery_id: str) -> HttpResponse:
    """Upload a delivery's customer selections to Google Drive.

    Zips the customer's digital/both selections and uploads to Drive,
    then updates the delivery note with the Drive URL.
    """
    import tempfile
    import zipfile

    from django.contrib import messages

    if not _is_photographer(request.user):
        return redirect("home")

    from .google_drive import is_drive_configured, upload_to_drive

    delivery = get_object_or_404(Delivery, pk=delivery_id)
    order = delivery.order
    event = order.event
    customer = order.customer

    if not is_drive_configured():
        messages.error(
            request,
            "Google Drive is not configured. "
            "Set GOOGLE_DRIVE_CREDENTIALS_FILE and GOOGLE_DRIVE_FOLDER_ID.",
        )
        return redirect("order_fulfilment", event_id=event.pk, customer_id=customer.pk)

    # Build the zip of the customer's digital delivery photos
    selections = list(
        Selection.objects.filter(customer=customer, photo__event=event)
        .exclude(choice="reject")
        .select_related("photo")
    )
    digital_photos = [s.photo for s in selections if s.choice in ("digital", "both")]
    digital_count = len(digital_photos)
    print_count = sum(1 for s in selections if s.choice == "both")

    if not digital_photos:
        messages.warning(
            request,
            "No photos to upload. The customer has not selected any photos "
            "as digital or print in the gallery.",
        )
        return redirect("order_fulfilment", event_id=event.pk, customer_id=customer.pk)

    zip_filename = f"{event.name}_{customer}_digital.zip"

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = tmp.name
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for photo in digital_photos:
                if photo.original:
                    zf.write(
                        photo.original.path,
                        photo.filename or photo.original.name,
                    )

    try:
        drive_url = upload_to_drive(tmp_path, zip_filename)
        delivery.method = Delivery.Method.GOOGLE_DRIVE
        delivery.url = drive_url
        delivery.notes = (
            f"{delivery.notes}\nUploaded {zip_filename}".strip()
            if delivery.notes
            else f"Uploaded {zip_filename}"
        )
        delivery.save(update_fields=["method", "url", "notes", "date_modified"])

        # Scaffold items if delivery has none
        if not delivery.items.exists():
            _scaffold_delivery_items(delivery, digital_count, print_count)

        order.update_delivery_status()
        messages.success(
            request,
            f"Uploaded to Google Drive. Link: {drive_url}",
        )
    except Exception as exc:
        messages.error(request, f"Google Drive upload failed: {exc}")
    finally:
        import os

        os.unlink(tmp_path)

    return redirect("order_fulfilment", event_id=event.pk, customer_id=customer.pk)


@login_required
def select_files_for_delivery(request: HttpRequest, delivery_id: str) -> HttpResponse:
    """File browser for selecting files to upload to Drive for a delivery."""
    if not _is_photographer(request.user):
        return redirect("home")

    delivery = get_object_or_404(Delivery, pk=delivery_id)
    order = delivery.order
    event = order.event
    customer = order.customer

    media_root = Path(settings.MEDIA_ROOT)
    event_folder = media_root / "photos" / str(event.pk)
    browse_path_str = request.GET.get("path", "")
    if browse_path_str:
        browse_path = Path(browse_path_str).resolve()
    else:
        browse_path = event_folder.resolve()

    if not browse_path.exists() or not browse_path.is_dir():
        browse_path = event_folder.resolve()

    folders: list[dict[str, str]] = []
    files: list[dict[str, object]] = []
    parent_path = browse_path.parent
    has_parent = browse_path != browse_path.parent

    image_extensions = {
        ".jpg",
        ".jpeg",
        ".png",
        ".tif",
        ".tiff",
        ".raw",
        ".cr2",
        ".nef",
        ".arw",
        ".dng",
        ".psd",
        ".zip",
    }

    try:
        for entry in sorted(
            browse_path.iterdir(), key=lambda e: (not e.is_dir(), e.name)
        ):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                folders.append({"name": entry.name, "path": str(entry)})
            elif entry.is_file():
                suffix = entry.suffix.lower()
                if suffix in image_extensions:
                    size_mb = entry.stat().st_size / (1024 * 1024)
                    files.append(
                        {
                            "name": entry.name,
                            "path": str(entry),
                            "size": f"{size_mb:.1f} MB",
                        }
                    )
    except PermissionError:
        from django.contrib import messages

        messages.error(request, f"Permission denied: {browse_path}")

    return render(
        request,
        "gallery/select_files_for_delivery.html",
        {
            "delivery": delivery,
            "event": event,
            "customer": customer,
            "order": order,
            "browse_path": str(browse_path),
            "browse_path_display": browse_path.name or str(browse_path),
            "parent_path": str(parent_path) if has_parent else "",
            "event_folder": str(event_folder),
            "folders": folders,
            "files": files,
        },
    )


@require_POST
@login_required
def upload_selected_for_delivery(
    request: HttpRequest, delivery_id: str
) -> HttpResponse:
    """Upload photographer-selected files to Google Drive for a delivery."""
    import tempfile
    import zipfile

    from django.contrib import messages

    if not _is_photographer(request.user):
        return redirect("home")

    from .google_drive import is_drive_configured, upload_to_drive

    delivery = get_object_or_404(Delivery, pk=delivery_id)
    order = delivery.order
    event = order.event
    customer = order.customer

    if not is_drive_configured():
        messages.error(
            request,
            "Google Drive is not configured. "
            "Set GOOGLE_DRIVE_CREDENTIALS_FILE and GOOGLE_DRIVE_FOLDER_ID.",
        )
        return redirect("order_fulfilment", event_id=event.pk, customer_id=customer.pk)

    selected_files = request.POST.getlist("selected_files")
    if not selected_files:
        messages.warning(request, "No files selected.")
        return redirect("delivery_detail", delivery_id=delivery.pk)

    valid_paths: list[Path] = []
    for fp in selected_files:
        p = Path(fp).resolve()
        if p.is_file():
            valid_paths.append(p)

    if not valid_paths:
        messages.warning(request, "No valid files found.")
        return redirect("delivery_detail", delivery_id=delivery.pk)

    zip_filename = f"{event.name}_{customer}_selected.zip"

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = tmp.name
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in valid_paths:
                zf.write(p, p.name)

    try:
        drive_url = upload_to_drive(tmp_path, zip_filename)
        delivery.method = Delivery.Method.GOOGLE_DRIVE
        delivery.url = drive_url
        delivery.notes = (
            f"{delivery.notes}\nUploaded {len(valid_paths)} selected file(s)".strip()
            if delivery.notes
            else f"Uploaded {len(valid_paths)} selected file(s)"
        )
        delivery.save(update_fields=["method", "url", "notes", "date_modified"])

        if not delivery.items.exists():
            DeliveryItem.objects.create(
                delivery=delivery,
                sort_order=0,
                description=f"Selected files ({len(valid_paths)})",
                qty=len(valid_paths),
            )

        order.update_delivery_status()
        messages.success(
            request,
            f"Uploaded {len(valid_paths)} file(s) to Google Drive. Link: {drive_url}",
        )
    except Exception as exc:
        messages.error(request, f"Google Drive upload failed: {exc}")
    finally:
        import os

        os.unlink(tmp_path)

    return redirect("order_fulfilment", event_id=event.pk, customer_id=customer.pk)


@login_required
def select_files_for_drive(
    request: HttpRequest, event_id: str, customer_id: str
) -> HttpResponse:
    """File browser for selecting files to upload to Google Drive."""
    if not _is_photographer(request.user):
        return redirect("home")

    from jasonstudio.accounts.models import Customer as CustomerModel

    event = get_object_or_404(Event, pk=event_id)
    customer = get_object_or_404(CustomerModel, pk=customer_id)
    order = get_object_or_404(Order, event=event, customer=customer)

    media_root = Path(settings.MEDIA_ROOT)
    event_folder = media_root / "photos" / str(event.pk)
    # Default to the event folder, allow navigation via ?path=
    browse_path_str = request.GET.get("path", "")
    if browse_path_str:
        browse_path = Path(browse_path_str).resolve()
    else:
        browse_path = event_folder.resolve()

    # Ensure the path exists and is a directory
    if not browse_path.exists() or not browse_path.is_dir():
        browse_path = event_folder.resolve()

    # Build directory listing
    folders: list[dict[str, str]] = []
    files: list[dict[str, object]] = []

    # Parent folder navigation
    parent_path = browse_path.parent
    has_parent = browse_path != browse_path.parent

    image_extensions = {
        ".jpg",
        ".jpeg",
        ".png",
        ".tif",
        ".tiff",
        ".raw",
        ".cr2",
        ".nef",
        ".arw",
        ".dng",
        ".psd",
        ".zip",
    }

    try:
        for entry in sorted(
            browse_path.iterdir(), key=lambda e: (not e.is_dir(), e.name)
        ):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                folders.append({"name": entry.name, "path": str(entry)})
            elif entry.is_file():
                suffix = entry.suffix.lower()
                if suffix in image_extensions:
                    size_mb = entry.stat().st_size / (1024 * 1024)
                    files.append(
                        {
                            "name": entry.name,
                            "path": str(entry),
                            "size": f"{size_mb:.1f} MB",
                        }
                    )
    except PermissionError:
        from django.contrib import messages

        messages.error(request, f"Permission denied: {browse_path}")

    return render(
        request,
        "gallery/select_files_for_drive.html",
        {
            "event": event,
            "customer": customer,
            "order": order,
            "browse_path": str(browse_path),
            "browse_path_display": browse_path.name or str(browse_path),
            "parent_path": str(parent_path) if has_parent else "",
            "event_folder": str(event_folder),
            "folders": folders,
            "files": files,
        },
    )


@require_POST
@login_required
def upload_selected_to_google_drive(
    request: HttpRequest, event_id: str, customer_id: str
) -> HttpResponse:
    """Upload photographer-selected files to Google Drive."""
    import tempfile
    import zipfile

    from django.contrib import messages

    if not _is_photographer(request.user):
        return redirect("home")

    from jasonstudio.accounts.models import Customer as CustomerModel

    from .google_drive import is_drive_configured, upload_to_drive

    event = get_object_or_404(Event, pk=event_id)
    customer = get_object_or_404(CustomerModel, pk=customer_id)
    order = get_object_or_404(Order, event=event, customer=customer)

    if not is_drive_configured():
        messages.error(
            request,
            "Google Drive is not configured. "
            "Set GOOGLE_DRIVE_CREDENTIALS_FILE and GOOGLE_DRIVE_FOLDER_ID.",
        )
        return redirect("order_fulfilment", event_id=event.pk, customer_id=customer.pk)

    selected_files = request.POST.getlist("selected_files")
    if not selected_files:
        messages.warning(request, "No files selected.")
        return redirect("order_fulfilment", event_id=event.pk, customer_id=customer.pk)

    # Validate all paths are real files
    valid_paths: list[Path] = []
    for fp in selected_files:
        p = Path(fp).resolve()
        if p.is_file():
            valid_paths.append(p)

    if not valid_paths:
        messages.warning(request, "No valid files found.")
        return redirect("order_fulfilment", event_id=event.pk, customer_id=customer.pk)

    zip_filename = f"{event.name}_{customer}_selected.zip"

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = tmp.name
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in valid_paths:
                zf.write(p, p.name)

    try:
        drive_url = upload_to_drive(tmp_path, zip_filename)
        delivery = Delivery.objects.create(
            order=order,
            method=Delivery.Method.GOOGLE_DRIVE,
            url=drive_url,
            notes=f"Uploaded {len(valid_paths)} selected file(s)",
        )
        DeliveryItem.objects.create(
            delivery=delivery,
            sort_order=0,
            description=f"Selected files ({len(valid_paths)})",
            qty=len(valid_paths),
        )
        order.update_delivery_status()
        messages.success(
            request,
            f"Uploaded {len(valid_paths)} file(s) to Google Drive. Link: {drive_url}",
        )
    except Exception as exc:
        messages.error(request, f"Google Drive upload failed: {exc}")
    finally:
        import os

        os.unlink(tmp_path)

    return redirect("order_fulfilment", event_id=event.pk, customer_id=customer.pk)


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
        is_default = request.POST.get("is_default") == "on"
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
            service.is_default = is_default
            service.is_active = is_active
            service.save()
        else:
            Service.objects.create(
                name=name,
                description=description,
                unit_type=unit_type,
                default_rate=default_rate,
                sort_order=sort_order,
                is_default=is_default,
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
        update_fields=["subtotal", "tax_rate", "tax_amount", "total", "date_modified"]
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

    # Auto-populate default services on a brand-new quotation
    if _created:
        from decimal import Decimal

        default_services = Service.objects.filter(
            is_active=True, is_default=True
        ).order_by("sort_order")
        for idx, svc in enumerate(default_services):
            QuotationLineItem.objects.create(
                quotation=quotation,
                service=svc,
                sort_order=idx,
                description=svc.name,
                qty=Decimal("1"),
                unit_cost=svc.default_rate,
                price=svc.default_rate,
            )
        if default_services.exists():
            _build_quotation_totals(quotation)

    # Lock editing if invoice is paid
    existing_order = Order.objects.filter(event=event, customer=customer).first()
    if existing_order and existing_order.is_paid:
        return redirect("quotation_view", event_id=event.pk, customer_id=customer.pk)

    if request.method == "POST":
        # Save date, deposit, and validity
        import datetime

        quote_date = request.POST.get("date", "").strip()
        if quote_date:
            try:
                quotation.date = datetime.date.fromisoformat(quote_date)
            except ValueError:
                pass
        try:
            quotation.deposit_amount = Decimal(request.POST.get("deposit_amount", "0"))
        except InvalidOperation, ValueError:
            pass
        valid_until = request.POST.get("valid_until", "").strip()
        if valid_until:
            try:
                quotation.valid_until = datetime.date.fromisoformat(valid_until)
            except ValueError:
                pass
        else:
            quotation.valid_until = None
        quotation.notes = request.POST.get("notes", "").strip()
        # Reset accepted status when quotation is edited
        if quotation.status == Quotation.Status.ACCEPTED:
            quotation.status = Quotation.Status.DRAFT
            quotation.accepted_at = None
            quotation.accepted_by = ""
        quotation.save(
            update_fields=[
                "date",
                "deposit_amount",
                "valid_until",
                "notes",
                "status",
                "accepted_at",
                "accepted_by",
                "date_modified",
            ]
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

    # Check if invoice is paid (locks editing)
    existing_order = Order.objects.filter(event=event, customer=customer).first()
    is_locked = existing_order.is_paid if existing_order else False

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
            "is_locked": is_locked,
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
@require_POST
def quotation_delete(
    request: HttpRequest, event_id: str, customer_id: str
) -> HttpResponse:
    """Photographer deletes a quotation. Blocked if an order references it."""
    if not _is_photographer(request.user):
        return redirect("home")

    from django.contrib import messages
    from django.db.models import ProtectedError

    from jasonstudio.accounts.models import Customer as CustomerModel

    event = get_object_or_404(Event, pk=event_id)
    customer = get_object_or_404(CustomerModel, pk=customer_id)
    quotation = get_object_or_404(Quotation, event=event, customer=customer)

    try:
        quotation.delete()
        messages.success(request, f"Quotation {quotation.quote_number} deleted.")
    except ProtectedError:
        messages.error(
            request,
            f"Cannot delete {quotation.quote_number} — "
            f"an order references this quotation. Delete the order first.",
        )
    return redirect("event_orders", event_id=event.pk)


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
        quotation.save(update_fields=["status", "date_modified"])

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

    # Create a Delivery with scaffolded items
    selections = Selection.objects.filter(
        customer=customer, photo__event=event
    ).exclude(choice="reject")
    digital_count = selections.filter(choice__in=["digital", "both"]).count()
    print_count = selections.filter(choice="both").count()
    if digital_count:
        delivery = Delivery.objects.create(
            order=order,
            method=Delivery.Method.EMAIL,
            url=download_url,
            notes=f"Email sent to {email}",
        )
        _scaffold_delivery_items(delivery, digital_count, print_count)
        order.update_delivery_status()

    messages.success(request, f"Download link sent to {email}.")
    return redirect("order_fulfilment", event_id=event.pk, customer_id=customer.pk)


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


# ── Utilities ──────────────────────────────────────────────────────────


@login_required
def utilities(request: HttpRequest) -> HttpResponse:
    """Photographer utilities page."""
    if not _is_photographer(request.user):
        return redirect("home")

    from .google_drive import is_drive_configured

    photographer = request.user.photographer_profile

    return render(
        request,
        "gallery/utilities.html",
        {
            "drive_configured": is_drive_configured(),
            "photographer": photographer,
        },
    )


@login_required
def email_template_edit(request: HttpRequest) -> HttpResponse:
    """Edit the default email template for customer download emails."""
    from django.contrib import messages

    if not _is_photographer(request.user):
        return redirect("home")

    photographer = request.user.photographer_profile

    if request.method == "POST":
        photographer.email_subject_template = request.POST.get(
            "email_subject_template", ""
        ).strip()
        photographer.email_body_template = request.POST.get(
            "email_body_template", ""
        ).strip()
        photographer.save(
            update_fields=[
                "email_subject_template",
                "email_body_template",
                "date_modified",
            ]
        )
        messages.success(request, "Email template updated.")
        return redirect("utilities")

    return redirect("utilities")


@login_required
@require_POST
def backup_database(request: HttpRequest) -> HttpResponse:
    """Back up the SQLite database.

    If Google Drive is configured, uploads the backup there.
    Otherwise, serves it as a local file download.
    """
    import shutil
    import tempfile

    from django.contrib import messages

    if not _is_photographer(request.user):
        return redirect("home")

    db_path = settings.DATABASES["default"]["NAME"]
    if not db_path or not Path(db_path).exists():
        messages.error(request, "Database file not found.")
        return redirect("utilities")

    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"jasonstudio_backup_{timestamp}.sqlite3"

    # Copy the database safely (SQLite supports this while the DB is open)
    tmp_dir = tempfile.mkdtemp()
    backup_path = Path(tmp_dir) / backup_filename
    shutil.copy2(str(db_path), str(backup_path))

    destination = request.POST.get("destination", "drive")

    if destination == "drive":
        from .google_drive import is_drive_configured, upload_to_drive

        if not is_drive_configured():
            messages.error(request, "Google Drive is not configured.")
            return redirect("utilities")

        try:
            drive_url = upload_to_drive(
                str(backup_path),
                backup_filename,
                mime_type="application/x-sqlite3",
            )
            messages.success(
                request,
                f"Database backed up to Google Drive: {drive_url}",
            )
        except Exception as e:
            messages.error(request, f"Google Drive upload failed: {e}")
        finally:
            backup_path.unlink(missing_ok=True)
            Path(tmp_dir).rmdir()

        return redirect("utilities")

    else:
        # Local download
        response = HttpResponse(
            backup_path.read_bytes(),
            content_type="application/x-sqlite3",
        )
        response["Content-Disposition"] = f'attachment; filename="{backup_filename}"'
        backup_path.unlink(missing_ok=True)
        Path(tmp_dir).rmdir()
        return response


# ── Reports ──────────────────────────────────────────────────────────────


@login_required
def report_payments_received(request: HttpRequest) -> HttpResponse:
    """Payments received in a date range."""
    from decimal import Decimal

    if not _is_photographer(request.user):
        return redirect("home")

    today = timezone.now().date()
    # Default to current month
    date_from_str = request.GET.get("from", "")
    date_to_str = request.GET.get("to", "")

    try:
        date_from = (
            timezone.datetime.strptime(date_from_str, "%Y-%m-%d").date()
            if date_from_str
            else today.replace(day=1)
        )
    except ValueError:
        date_from = today.replace(day=1)

    try:
        date_to = (
            timezone.datetime.strptime(date_to_str, "%Y-%m-%d").date()
            if date_to_str
            else today
        )
    except ValueError:
        date_to = today

    payments = (
        Payment.objects.filter(date__gte=date_from, date__lte=date_to)
        .select_related(
            "invoice__order__customer__user",
            "invoice__order__event",
        )
        .order_by("-date")
    )

    total = sum((p.amount for p in payments), Decimal("0.00"))

    # Group by method
    by_method: dict[str, Decimal] = {}
    for p in payments:
        label = p.get_method_display()
        by_method[label] = by_method.get(label, Decimal("0.00")) + p.amount

    return render(
        request,
        "gallery/reports/payments_received.html",
        {
            "payments": payments,
            "total": total,
            "by_method": by_method,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@login_required
def report_outstanding_invoices(request: HttpRequest) -> HttpResponse:
    """Invoices that are not yet paid or void."""
    from decimal import Decimal

    if not _is_photographer(request.user):
        return redirect("home")

    today = timezone.now().date()

    invoices = (
        Invoice.objects.filter(status__in=[Invoice.Status.DRAFT, Invoice.Status.ISSUED])
        .select_related(
            "order__customer__user",
            "order__event",
        )
        .order_by("date")
    )

    # Annotate with age
    invoice_rows = []
    for inv in invoices:
        age_days = (today - inv.date).days if inv.date else 0
        invoice_rows.append(
            {
                "invoice": inv,
                "customer": inv.order.customer,
                "event": inv.order.event,
                "order": inv.order,
                "age_days": age_days,
            }
        )

    total_outstanding = sum((inv.amount_due for inv in invoices), Decimal("0.00"))

    return render(
        request,
        "gallery/reports/outstanding_invoices.html",
        {
            "invoice_rows": invoice_rows,
            "total_outstanding": total_outstanding,
        },
    )


@login_required
def report_revenue_summary(request: HttpRequest) -> HttpResponse:
    """Revenue summary grouped by month."""
    from collections import OrderedDict
    from decimal import Decimal

    if not _is_photographer(request.user):
        return redirect("home")

    today = timezone.now().date()
    year = request.GET.get("year", "")
    try:
        year = int(year)
    except (ValueError, TypeError):
        year = today.year

    payments = (
        Payment.objects.filter(date__year=year)
        .select_related("invoice__order__event")
        .order_by("date")
    )

    # Group by month
    monthly: OrderedDict[str, dict] = OrderedDict()
    for month_num in range(1, 13):
        month_label = timezone.datetime(year, month_num, 1).strftime("%B")
        monthly[month_label] = {
            "count": 0,
            "total": Decimal("0.00"),
        }

    grand_total = Decimal("0.00")
    total_count = 0
    for p in payments:
        month_label = p.date.strftime("%B")
        monthly[month_label]["count"] += 1
        monthly[month_label]["total"] += p.amount
        grand_total += p.amount
        total_count += 1

    # Available years for the switcher
    all_years = Payment.objects.dates("date", "year", order="DESC")
    available_years = [d.year for d in all_years]
    if year not in available_years:
        available_years.insert(0, year)

    return render(
        request,
        "gallery/reports/revenue_summary.html",
        {
            "monthly": monthly,
            "grand_total": grand_total,
            "total_count": total_count,
            "year": year,
            "available_years": available_years,
        },
    )
