import datetime
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from jasonstudio.accounts.models import Customer, Order, PhotographerProfile
from jasonstudio.gallery.models import Event, Photo


@pytest.fixture
def photographer_user(db) -> User:
    user = User.objects.create_user(
        username="photographer", password="testpass123", email="photo@example.com",
        first_name="Jason", last_name="Photographer",
    )
    PhotographerProfile.objects.create(
        user=user,
        business_name="Jason Studio",
        phone="555-0100",
        email="studio@example.com",
        tax_rate=Decimal("13.00"),
        payment_terms="Due upon receipt",
        payment_instructions="E-transfer to studio@example.com",
    )
    return user


@pytest.fixture
def customer_user(db) -> User:
    user = User.objects.create_user(
        username="customer1", password="testpass123", email="customer@example.com",
        first_name="Jane", last_name="Doe",
    )
    Customer.objects.create(user=user, phone="555-0200", company_name="Doe Inc")
    return user


@pytest.fixture
def customer(customer_user) -> Customer:
    return customer_user.customer_profile


@pytest.fixture
def event(db) -> Event:
    return Event.objects.create(
        name="Wedding 2025",
        date=datetime.date(2025, 6, 15),
        location="Central Park",
        status=Event.Status.PUBLISHED,
    )


@pytest.fixture
def event_with_customer(event, customer) -> Event:
    event.customers.add(customer)
    return event


@pytest.fixture
def photo(event) -> Photo:
    return Photo.objects.create(
        event=event,
        original="photos/test/photo1.jpg",
        filename="photo1.jpg",
        sort_order=1,
    )


@pytest.fixture
def photos(event) -> list[Photo]:
    return [
        Photo.objects.create(
            event=event,
            original=f"photos/test/photo{i}.jpg",
            filename=f"photo{i}.jpg",
            sort_order=i,
        )
        for i in range(1, 6)
    ]


@pytest.fixture
def order(event_with_customer, customer) -> Order:
    return Order.objects.create(
        event=event_with_customer,
        customer=customer,
        photographer_hours=Decimal("2.00"),
        photographer_rate=Decimal("150.00"),
    )


@pytest.fixture
def paid_order(order) -> Order:
    order.status = Order.Status.PAID
    order.save()
    return order
