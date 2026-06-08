from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import CustomerForm
from .models import Customer


def _is_photographer(user) -> bool:
    try:
        return bool(user.photographer_profile)
    except Exception:
        return False


def signup(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            Customer.objects.create(user=user)
            login(request, user)
            return redirect("customer_dashboard")
    else:
        form = UserCreationForm()
    return render(request, "accounts/signup.html", {"form": form})


@login_required
def customer_dashboard(request: HttpRequest) -> HttpResponse:
    customer = getattr(request.user, "customer_profile", None)
    if not customer:
        return redirect("home")
    events = customer.events.filter(status="published")
    return render(
        request, "accounts/dashboard.html", {"customer": customer, "events": events}
    )


@login_required
def customer_list(request: HttpRequest) -> HttpResponse:
    if not _is_photographer(request.user):
        return redirect("home")
    show_inactive = request.GET.get("show_inactive", "") == "1"
    if show_inactive:
        customers = Customer.objects.select_related("user").all()
    else:
        customers = Customer.objects.select_related("user").filter(is_active=True)
    return render(
        request,
        "accounts/customer_list.html",
        {"customers": customers, "show_inactive": show_inactive},
    )


@login_required
def customer_add(request: HttpRequest) -> HttpResponse:
    if not _is_photographer(request.user):
        return redirect("home")

    if request.method == "POST":
        form = CustomerForm(request.POST)
        if form.is_valid():
            first_name = form.cleaned_data["first_name"]
            last_name = form.cleaned_data["last_name"]
            email = form.cleaned_data["email"]
            phone = form.cleaned_data["phone"]

            company_name = form.cleaned_data["company_name"]

            # Create user with email as username
            username = email or f"{first_name.lower()}.{last_name.lower()}"
            user = User.objects.create_user(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
            )
            Customer.objects.create(user=user, phone=phone, company_name=company_name)
            return redirect("customer_list")
    else:
        form = CustomerForm()

    return render(
        request, "accounts/customer_form.html", {"form": form, "action": "Add"}
    )


@login_required
def customer_edit(request: HttpRequest, customer_id: str) -> HttpResponse:
    if not _is_photographer(request.user):
        return redirect("home")

    customer = get_object_or_404(Customer, pk=customer_id)

    if request.method == "POST":
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer.user.first_name = form.cleaned_data["first_name"]
            customer.user.last_name = form.cleaned_data["last_name"]
            customer.user.email = form.cleaned_data["email"]
            customer.user.save(update_fields=["first_name", "last_name", "email"])
            customer.company_name = form.cleaned_data["company_name"]
            customer.phone = form.cleaned_data["phone"]
            customer.save(update_fields=["company_name", "phone", "modified"])
            return redirect("customer_list")
    else:
        form = CustomerForm(
            initial={
                "first_name": customer.user.first_name,
                "last_name": customer.user.last_name,
                "company_name": customer.company_name,
                "email": customer.user.email,
                "phone": customer.phone,
            }
        )

    return render(
        request,
        "accounts/customer_form.html",
        {"form": form, "action": "Edit", "customer": customer},
    )


@login_required
@require_POST
def customer_toggle_active(request: HttpRequest, customer_id: str) -> HttpResponse:
    if not _is_photographer(request.user):
        return redirect("home")

    customer = get_object_or_404(Customer, pk=customer_id)
    customer.is_active = not customer.is_active
    customer.user.is_active = customer.is_active
    customer.user.save(update_fields=["is_active"])
    customer.save(update_fields=["is_active", "modified"])
    return redirect("customer_list")


@login_required
@require_POST
def customer_delete(request: HttpRequest, customer_id: str) -> HttpResponse:
    from django.contrib import messages

    if not _is_photographer(request.user):
        return redirect("home")

    customer = get_object_or_404(Customer, pk=customer_id)

    # Check for linked data
    has_selections = customer.selections.exists()
    has_orders = customer.orders.exists()
    has_events = customer.events.exists()

    if has_selections or has_orders or has_events:
        reasons = []
        if has_events:
            reasons.append(f"{customer.events.count()} event(s)")
        if has_selections:
            reasons.append(f"{customer.selections.count()} selection(s)")
        if has_orders:
            reasons.append(f"{customer.orders.count()} order(s)")
        messages.error(
            request,
            f"Cannot delete {customer}. They have linked data: {', '.join(reasons)}. "
            f"Remove them from events and delete their orders first.",
        )
        return redirect("customer_list")

    user = customer.user
    customer.delete()
    user.delete()
    messages.success(request, "Customer deleted.")
    return redirect("customer_list")
