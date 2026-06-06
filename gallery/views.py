from io import BytesIO

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Event, Photo, Selection
from .watermark import apply_watermark


def home(request: HttpRequest) -> HttpResponse:
    return render(request, "gallery/home.html")


@login_required
def event_gallery(request: HttpRequest, event_id: str) -> HttpResponse:
    customer = getattr(request.user, "customer_profile", None)
    is_photographer = hasattr(request.user, "photographer_profile")

    if is_photographer:
        event = get_object_or_404(Event, pk=event_id)
    elif customer:
        event = get_object_or_404(Event, pk=event_id, customer=customer, status="published")
    else:
        return redirect("home")

    photos = event.photos.all()
    selections = {}
    if customer:
        for sel in Selection.objects.filter(customer=customer, photo__event=event):
            selections.setdefault(str(sel.photo_id), []).append(sel.selection_type)

    return render(
        request,
        "gallery/event_gallery.html",
        {
            "event": event,
            "photos": photos,
            "selections": selections,
            "is_photographer": is_photographer,
        },
    )


@login_required
def upload_photos(request: HttpRequest, event_id: str) -> HttpResponse:
    if not hasattr(request.user, "photographer_profile"):
        return redirect("home")

    event = get_object_or_404(Event, pk=event_id)

    if request.method == "POST":
        files = request.FILES.getlist("photos")
        for f in files:
            photo = Photo(event=event, original=f)
            photo.save()

            watermark_text = getattr(settings, "WATERMARK_TEXT", "PROOF")
            wm_buffer = apply_watermark(BytesIO(f.read()), text=watermark_text)
            f.seek(0)
            photo.watermarked.save(
                f"wm_{f.name}", ContentFile(wm_buffer.read()), save=True
            )

        if request.htmx:
            photos = event.photos.all()
            return render(
                request,
                "gallery/partials/photo_grid.html",
                {"photos": photos, "event": event, "is_photographer": True},
            )
        return redirect("event_gallery", event_id=event.pk)

    return render(request, "gallery/upload.html", {"event": event})


@login_required
@require_POST
def toggle_selection(request: HttpRequest, photo_id: str) -> HttpResponse:
    customer = getattr(request.user, "customer_profile", None)
    if not customer:
        return JsonResponse({"error": "Not a customer"}, status=403)

    photo = get_object_or_404(Photo, pk=photo_id)
    selection_type = request.POST.get("selection_type", "")
    if selection_type not in ("print", "digital"):
        return JsonResponse({"error": "Invalid selection type"}, status=400)

    selection, created = Selection.objects.get_or_create(
        photo=photo,
        customer=customer,
        selection_type=selection_type,
    )
    if not created:
        selection.delete()
        selected = False
    else:
        selected = True

    if request.htmx:
        return render(
            request,
            "gallery/partials/selection_buttons.html",
            {"photo": photo, "selected": selected, "selection_type": selection_type},
        )
    return JsonResponse({"selected": selected})


@login_required
def photographer_dashboard(request: HttpRequest) -> HttpResponse:
    if not hasattr(request.user, "photographer_profile"):
        return redirect("home")
    events = Event.objects.select_related("customer__user").all()
    return render(request, "gallery/photographer_dashboard.html", {"events": events})


@login_required
def manage_event(request: HttpRequest, event_id: str | None = None) -> HttpResponse:
    if not hasattr(request.user, "photographer_profile"):
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
    customer = getattr(request.user, "customer_profile", None)
    if not customer:
        return redirect("home")

    selections = (
        Selection.objects.filter(customer=customer)
        .select_related("photo__event")
        .order_by("selection_type", "photo__event__name")
    )
    print_selections = [s for s in selections if s.selection_type == "print"]
    digital_selections = [s for s in selections if s.selection_type == "digital"]

    return render(
        request,
        "gallery/my_selections.html",
        {
            "print_selections": print_selections,
            "digital_selections": digital_selections,
        },
    )
