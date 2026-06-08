"""Tests for Service, Quotation, and QuotationLineItem models and views."""
import datetime
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from jasonstudio.accounts.models import Order, Quotation, QuotationLineItem
from jasonstudio.gallery.models import Service


@pytest.fixture
def photographer_client(photographer_user) -> Client:
    client = Client()
    client.login(username="photographer", password="testpass123")
    return client


@pytest.fixture
def customer_client(customer_user) -> Client:
    client = Client()
    client.login(username="customer1", password="testpass123")
    return client


@pytest.fixture
def photography_service(db) -> Service:
    return Service.objects.create(
        name="Photography",
        unit_type=Service.UnitType.PER_HOUR,
        default_rate=Decimal("150.00"),
        sort_order=0,
    )


@pytest.fixture
def travel_service(db) -> Service:
    return Service.objects.create(
        name="Travel",
        unit_type=Service.UnitType.PER_KM,
        default_rate=Decimal("0.55"),
        sort_order=1,
    )


@pytest.fixture
def quotation(event_with_customer, customer) -> Quotation:
    return Quotation.objects.create(
        event=event_with_customer,
        customer=customer,
        deposit_amount=Decimal("100.00"),
        valid_until=datetime.date(2026, 12, 31),
    )


@pytest.fixture
def quotation_with_items(quotation, photography_service, travel_service) -> Quotation:
    QuotationLineItem.objects.create(
        quotation=quotation,
        service=photography_service,
        sort_order=0,
        description="Photography",
        qty=Decimal("3"),
        unit_cost=Decimal("150.00"),
        price=Decimal("450.00"),
    )
    QuotationLineItem.objects.create(
        quotation=quotation,
        service=travel_service,
        sort_order=1,
        description="Travel",
        qty=Decimal("50"),
        unit_cost=Decimal("0.55"),
        price=Decimal("27.50"),
    )
    return quotation


class TestServiceModel:
    def test_create_service(self, db):
        svc = Service.objects.create(
            name="Photography",
            unit_type=Service.UnitType.PER_HOUR,
            default_rate=Decimal("150.00"),
        )
        assert str(svc) == "Photography (Per Hour)"

    def test_unit_type_choices(self):
        values = [c[0] for c in Service.UnitType.choices]
        assert "per_hour" in values
        assert "per_image" in values
        assert "per_km" in values
        assert "flat" in values
        assert "each" in values

    def test_ordering(self, photography_service, travel_service):
        services = list(Service.objects.all())
        assert services[0] == photography_service
        assert services[1] == travel_service


class TestQuotationModel:
    def test_quote_number_auto_generated(self, quotation):
        assert quotation.quote_number.startswith("QUO-")
        assert len(quotation.quote_number) == 9

    def test_quote_number_sequential(self, event_with_customer, customer, db):
        from django.contrib.auth.models import User

        from jasonstudio.accounts.models import Customer as CustomerModel
        from jasonstudio.gallery.models import Event

        q1 = Quotation.objects.create(event=event_with_customer, customer=customer)
        user2 = User.objects.create_user(username="cust2q", password="pass")
        c2 = CustomerModel.objects.create(user=user2)
        event2 = Event.objects.create(name="Event 2", date=datetime.date(2025, 7, 1))
        event2.customers.add(c2)
        q2 = Quotation.objects.create(event=event2, customer=c2)
        num1 = int(q1.quote_number.replace("QUO-", ""))
        num2 = int(q2.quote_number.replace("QUO-", ""))
        assert num2 == num1 + 1

    def test_is_expired_false(self, quotation):
        quotation.valid_until = datetime.date(2099, 1, 1)
        assert quotation.is_expired is False

    def test_is_expired_true(self, quotation):
        quotation.valid_until = datetime.date(2020, 1, 1)
        assert quotation.is_expired is True

    def test_is_expired_none_valid_until(self, quotation):
        quotation.valid_until = None
        assert quotation.is_expired is False

    def test_unique_per_event_customer(self, event_with_customer, customer):
        Quotation.objects.create(event=event_with_customer, customer=customer)
        with pytest.raises(Exception):
            Quotation.objects.create(event=event_with_customer, customer=customer)


class TestQuotationAccept:
    def test_accept_creates_order(self, quotation_with_items, photographer_user):
        quotation = quotation_with_items
        order = quotation.accept(by="photographer")
        assert isinstance(order, Order)
        assert order.event == quotation.event
        assert order.customer == quotation.customer
        assert order.quotation == quotation
        assert order.deposit_amount == Decimal("100.00")

    def test_accept_sets_photographer_hours_from_per_hour_item(
        self, quotation_with_items, photographer_user
    ):
        order = quotation_with_items.accept(by="photographer")
        # Photography item: qty=3 hours, unit_cost=150
        assert order.photographer_hours == Decimal("3")
        assert order.photographer_rate == Decimal("150.00")

    def test_accept_sets_status_and_timestamp(self, quotation_with_items, photographer_user):
        quotation = quotation_with_items
        quotation.accept(by="customer")
        quotation.refresh_from_db()
        assert quotation.status == Quotation.Status.ACCEPTED
        assert quotation.accepted_at is not None
        assert quotation.accepted_by == "customer"

    def test_accept_updates_existing_order(self, quotation_with_items, customer, event_with_customer):
        # Pre-create order
        existing_order = Order.objects.create(
            event=event_with_customer, customer=customer,
        )
        order = quotation_with_items.accept(by="photographer")
        assert order.pk == existing_order.pk
        assert order.deposit_amount == Decimal("100.00")


class TestQuotationTotals:
    def test_build_totals(self, quotation_with_items, photographer_user):
        from jasonstudio.gallery.views import _build_quotation_totals

        _build_quotation_totals(quotation_with_items)
        quotation_with_items.refresh_from_db()
        # 450 + 27.50 = 477.50 subtotal
        assert quotation_with_items.subtotal == Decimal("477.50")
        # tax 13% of 477.50 = 62.075 → stored as Decimal
        assert quotation_with_items.tax_rate == Decimal("13.00")
        # total = subtotal - deposit + tax = 477.50 - 100 + 62.075
        # DB rounds to 2 decimal places
        expected_tax = Decimal("477.50") * Decimal("13") / Decimal("100")
        expected_total = (Decimal("477.50") - Decimal("100") + expected_tax).quantize(Decimal("0.01"))
        assert quotation_with_items.total == expected_total


class TestServiceViews:
    def test_service_list(self, photographer_client, photography_service):
        resp = photographer_client.get(reverse("service_list"))
        assert resp.status_code == 200
        assert b"Photography" in resp.content

    def test_add_service(self, photographer_client):
        resp = photographer_client.post(reverse("service_add"), {
            "name": "Image Processing",
            "description": "Post-processing",
            "unit_type": "per_image",
            "default_rate": "2.50",
            "sort_order": "1",
            "is_active": "on",
        })
        assert resp.status_code == 302
        assert Service.objects.filter(name="Image Processing").exists()

    def test_edit_service(self, photographer_client, photography_service):
        resp = photographer_client.post(
            reverse("service_edit", args=[photography_service.pk]),
            {
                "name": "Photography Updated",
                "description": "",
                "unit_type": "per_hour",
                "default_rate": "175.00",
                "sort_order": "0",
                "is_active": "on",
            },
        )
        assert resp.status_code == 302
        photography_service.refresh_from_db()
        assert photography_service.name == "Photography Updated"
        assert photography_service.default_rate == Decimal("175.00")

    def test_customer_cannot_access(self, customer_client):
        resp = customer_client.get(reverse("service_list"))
        assert resp.status_code == 302


class TestQuotationViews:
    def test_photographer_edit_creates_quotation(
        self, photographer_client, event_with_customer, customer
    ):
        resp = photographer_client.get(
            reverse("quotation_edit", args=[event_with_customer.pk, customer.pk])
        )
        assert resp.status_code == 200
        assert Quotation.objects.filter(
            event=event_with_customer, customer=customer
        ).exists()

    def test_photographer_saves_line_items(
        self, photographer_client, event_with_customer, customer, photography_service
    ):
        resp = photographer_client.post(
            reverse("quotation_edit", args=[event_with_customer.pk, customer.pk]),
            {
                "deposit_amount": "50.00",
                "valid_until": "2026-12-31",
                "notes": "Test quote",
                "item_0_service": str(photography_service.pk),
                "item_0_description": "Photography",
                "item_0_qty": "2",
                "item_0_unit_cost": "150.00",
            },
        )
        assert resp.status_code == 302
        quotation = Quotation.objects.get(
            event=event_with_customer, customer=customer
        )
        assert quotation.deposit_amount == Decimal("50.00")
        assert quotation.line_items.count() == 1
        item = quotation.line_items.first()
        assert item.description == "Photography"
        assert item.price == Decimal("300.00")

    def test_photographer_view_quotation(
        self, photographer_client, quotation_with_items
    ):
        resp = photographer_client.get(
            reverse(
                "quotation_view",
                args=[quotation_with_items.event.pk, quotation_with_items.customer.pk],
            )
        )
        assert resp.status_code == 200
        assert quotation_with_items.quote_number.encode() in resp.content

    def test_photographer_accept(
        self, photographer_client, quotation_with_items
    ):
        resp = photographer_client.post(
            reverse(
                "quotation_accept",
                args=[quotation_with_items.event.pk, quotation_with_items.customer.pk],
            )
        )
        assert resp.status_code == 302
        quotation_with_items.refresh_from_db()
        assert quotation_with_items.status == Quotation.Status.ACCEPTED
        assert Order.objects.filter(
            event=quotation_with_items.event, customer=quotation_with_items.customer
        ).exists()

    def test_customer_view_quotation(
        self, customer_client, quotation_with_items
    ):
        resp = customer_client.get(
            reverse("customer_quotation_view", args=[quotation_with_items.event.pk])
        )
        assert resp.status_code == 200

    def test_customer_accept(self, customer_client, quotation_with_items):
        quotation_with_items.status = Quotation.Status.SENT
        quotation_with_items.save(update_fields=["status"])
        resp = customer_client.post(
            reverse("customer_quotation_accept", args=[quotation_with_items.event.pk])
        )
        assert resp.status_code == 302
        quotation_with_items.refresh_from_db()
        assert quotation_with_items.status == Quotation.Status.ACCEPTED
        assert quotation_with_items.accepted_by == "customer"

    def test_customer_decline(self, customer_client, quotation_with_items):
        quotation_with_items.status = Quotation.Status.SENT
        quotation_with_items.save(update_fields=["status"])
        resp = customer_client.post(
            reverse("customer_quotation_decline", args=[quotation_with_items.event.pk])
        )
        assert resp.status_code == 302
        quotation_with_items.refresh_from_db()
        assert quotation_with_items.status == Quotation.Status.DECLINED

    def test_customer_cannot_accept_expired(self, customer_client, quotation_with_items):
        quotation_with_items.status = Quotation.Status.SENT
        quotation_with_items.valid_until = datetime.date(2020, 1, 1)
        quotation_with_items.save(update_fields=["status", "valid_until"])
        resp = customer_client.post(
            reverse("customer_quotation_accept", args=[quotation_with_items.event.pk])
        )
        assert resp.status_code == 302
        quotation_with_items.refresh_from_db()
        # Should still be sent, not accepted
        assert quotation_with_items.status == Quotation.Status.SENT
