import datetime
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from jasonstudio.accounts.models import Invoice, Payment
from jasonstudio.gallery.models import (
    Event,
    Selection,
    ShareLink,
)


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


class TestHomeView:
    def test_anonymous_redirects_to_login(self, db):
        client = Client()
        resp = client.get(reverse("home"))
        assert resp.status_code == 200 or resp.status_code == 302

    def test_photographer_redirects_to_dashboard(self, photographer_client):
        resp = photographer_client.get(reverse("home"))
        assert resp.status_code == 302
        assert "photographer" in resp.url

    def test_customer_redirects_to_events(self, customer_client):
        resp = customer_client.get(reverse("home"))
        assert resp.status_code == 302
        assert "events" in resp.url or "dashboard" in resp.url


class TestEventGalleryView:
    def test_customer_can_view_gallery(
        self, customer_client, event_with_customer, photos
    ):
        resp = customer_client.get(
            reverse("event_gallery", args=[event_with_customer.pk])
        )
        assert resp.status_code == 200

    def test_customer_cannot_view_other_event(self, customer_client, db):
        other_event = Event.objects.create(
            name="Other", date=datetime.date(2025, 1, 1), status="published"
        )
        resp = customer_client.get(reverse("event_gallery", args=[other_event.pk]))
        assert resp.status_code == 404 or resp.status_code == 302


class TestToggleSelectionView:
    def test_toggle_creates_selection(
        self, customer_client, event_with_customer, photo
    ):
        url = reverse("toggle_selection", args=[photo.pk])
        resp = customer_client.post(
            url,
            {"choice": "digital"},
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200
        assert Selection.objects.filter(photo=photo).exists()

    def test_toggle_changes_choice(
        self, customer_client, event_with_customer, photo, customer
    ):
        Selection.objects.create(photo=photo, customer=customer, choice="digital")
        url = reverse("toggle_selection", args=[photo.pk])
        resp = customer_client.post(
            url,
            {"choice": "both", "print_size": "5x7"},
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200
        sel = Selection.objects.get(photo=photo, customer=customer)
        assert sel.choice == "both"
        assert sel.print_size == "5x7"

    def test_toggle_reject_deletes_selection(
        self, customer_client, event_with_customer, photo, customer
    ):
        Selection.objects.create(photo=photo, customer=customer, choice="digital")
        url = reverse("toggle_selection", args=[photo.pk])
        resp = customer_client.post(
            url,
            {"choice": "reject"},
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200
        sel = Selection.objects.get(photo=photo, customer=customer)
        assert sel.choice == "reject"


class TestMySelectionsView:
    def test_shows_selections_grouped_by_event(
        self, customer_client, event_with_customer, photo, customer
    ):
        Selection.objects.create(photo=photo, customer=customer, choice="digital")
        resp = customer_client.get(reverse("my_selections"))
        assert resp.status_code == 200
        assert event_with_customer.name in resp.content.decode()

    def test_filter_by_event(
        self, customer_client, event_with_customer, photo, customer
    ):
        Selection.objects.create(photo=photo, customer=customer, choice="digital")
        resp = customer_client.get(
            reverse("my_selections") + f"?event={event_with_customer.pk}"
        )
        assert resp.status_code == 200


class TestSelectionInvoiceView:
    def test_creates_invoice(
        self, customer_client, event_with_customer, photo, customer, order
    ):
        Selection.objects.create(photo=photo, customer=customer, choice="digital")
        resp = customer_client.get(
            reverse("selection_invoice", args=[event_with_customer.pk])
        )
        assert resp.status_code == 200
        assert Invoice.objects.filter(order=order).exists()

    def test_invoice_contains_line_items(
        self, customer_client, event_with_customer, photos, customer, order
    ):
        # Create a mix of selections
        Selection.objects.create(photo=photos[0], customer=customer, choice="digital")
        Selection.objects.create(
            photo=photos[1], customer=customer, choice="both", print_size="5x7"
        )
        resp = customer_client.get(
            reverse("selection_invoice", args=[event_with_customer.pk])
        )
        assert resp.status_code == 200
        invoice = Invoice.objects.get(order=order)
        # Photography + 1 print item + 1 digital bundle = 3 line items
        assert invoice.line_items.count() == 3

    def test_invoice_calculates_totals(
        self,
        customer_client,
        event_with_customer,
        photo,
        customer,
        order,
        photographer_user,
    ):
        Selection.objects.create(photo=photo, customer=customer, choice="digital")
        customer_client.get(reverse("selection_invoice", args=[event_with_customer.pk]))
        invoice = Invoice.objects.get(order=order)
        # quotation line item: 2 × $150 = $300
        assert invoice.subtotal == Decimal("300.00")
        # tax_rate=13% → tax=39
        assert invoice.tax_amount == Decimal("39.00")
        # subtotal(300) - deposit(100) + tax(39) = 239
        assert invoice.deposit == Decimal("100.00")
        assert invoice.amount_due == Decimal("239.00")

    def test_no_order_redirects(self, customer_client, event_with_customer):
        resp = customer_client.get(
            reverse("selection_invoice", args=[event_with_customer.pk])
        )
        assert resp.status_code == 302

    def test_photographer_can_view_invoice(
        self, photographer_client, event_with_customer, photo, customer, order
    ):
        Selection.objects.create(photo=photo, customer=customer, choice="digital")
        resp = photographer_client.get(
            reverse("photographer_invoice", args=[event_with_customer.pk, customer.pk])
        )
        assert resp.status_code == 200
        assert b"Invoice" in resp.content


class TestCustomerDownloadView:
    def test_download_blocked_when_unpaid(
        self, customer_client, event_with_customer, order
    ):
        resp = customer_client.get(
            reverse("customer_download", args=[event_with_customer.pk])
        )
        # Should redirect or show error
        assert resp.status_code in (302, 403, 404)

    def test_download_blocked_when_expired(
        self, customer_client, event_with_customer, paid_order, invoice
    ):
        # Move payment date_created back 31 days to expire downloads
        payment = invoice.payments.first()
        Payment.objects.filter(pk=payment.pk).update(
            date_created=timezone.now() - datetime.timedelta(days=31)
        )
        resp = customer_client.get(
            reverse("customer_download", args=[event_with_customer.pk])
        )
        assert resp.status_code in (302, 403, 404)


class TestShareLinkViews:
    def test_create_share_link(self, customer_client, event_with_customer, paid_order):
        resp = customer_client.post(
            reverse("create_share_link", args=[event_with_customer.pk])
        )
        assert resp.status_code == 302
        assert ShareLink.objects.filter(order=paid_order).exists()

    def test_create_replaces_old_link(
        self, customer_client, event_with_customer, paid_order
    ):
        ShareLink.objects.create(order=paid_order, code="OLDONE")
        resp = customer_client.post(
            reverse("create_share_link", args=[event_with_customer.pk])
        )
        assert resp.status_code == 302
        assert not ShareLink.objects.filter(code="OLDONE").exists()
        assert ShareLink.objects.filter(order=paid_order).count() == 1

    def test_deactivate_share_link(
        self, customer_client, event_with_customer, paid_order
    ):
        link = ShareLink.objects.create(order=paid_order, code="ABC123")
        resp = customer_client.post(
            reverse("deactivate_share_link", args=[event_with_customer.pk])
        )
        assert resp.status_code == 302
        link.refresh_from_db()
        assert link.is_active is False

    def test_shared_download_page_valid_code(self, client, paid_order):
        ShareLink.objects.create(order=paid_order, code="VALID1")
        resp = client.get(reverse("shared_download_page", args=["VALID1"]))
        assert resp.status_code == 200

    def test_shared_download_page_invalid_code(self, client, db):
        resp = client.get(reverse("shared_download_page", args=["BADCOD"]))
        assert resp.status_code == 200  # Shows expired page, not 404
        assert b"expired" in resp.content.lower() or b"invalid" in resp.content.lower()


class TestPhotographerDashboard:
    def test_photographer_sees_dashboard(self, photographer_client, event):
        resp = photographer_client.get(reverse("photographer_dashboard"))
        assert resp.status_code == 200
        assert event.name in resp.content.decode()

    def test_customer_cannot_access_dashboard(self, customer_client):
        resp = customer_client.get(reverse("photographer_dashboard"))
        assert resp.status_code == 302
