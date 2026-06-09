import datetime
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from jasonstudio.accounts.models import (
    Customer,
    Invoice,
    Order,
    Payment,
    PhotographerProfile,
    Quotation,
    QuotationLineItem,
)
from jasonstudio.gallery.models import Event, Photo


@pytest.fixture
def photographer_user(db) -> User:
    user = User.objects.create_user(
        username="photographer",
        password="testpass123",
        email="photo@example.com",
        first_name="Jason",
        last_name="Photographer",
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
        username="customer1",
        password="testpass123",
        email="customer@example.com",
        first_name="Jane",
        last_name="Doe",
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
def quotation(event_with_customer, customer) -> Quotation:
    q = Quotation.objects.create(
        event=event_with_customer,
        customer=customer,
        deposit_amount=Decimal("100.00"),
        subtotal=Decimal("300.00"),
        total=Decimal("300.00"),
    )
    QuotationLineItem.objects.create(
        quotation=q,
        description="Photography",
        qty=Decimal("2.00"),
        unit_cost=Decimal("150.00"),
        price=Decimal("300.00"),
        sort_order=0,
    )
    return q


@pytest.fixture
def order(quotation) -> Order:
    return Order.objects.create(
        event=quotation.event,
        customer=quotation.customer,
        quotation=quotation,
    )


@pytest.fixture
def invoice(order) -> Invoice:
    return Invoice.objects.create(
        order=order,
        subtotal=Decimal("300.00"),
        amount_due=Decimal("300.00"),
    )


@pytest.fixture
def paid_order(order, invoice) -> Order:
    """Create a payment against the invoice, which marks the invoice as paid."""
    Payment.objects.create(
        invoice=invoice,
        amount=invoice.amount_due,
        method=Payment.Method.ETRANSFER,
    )
    return order
