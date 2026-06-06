from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from .models import Customer


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
