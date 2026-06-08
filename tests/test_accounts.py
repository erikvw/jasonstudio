import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from jasonstudio.accounts.models import Customer
from jasonstudio.gallery.models import Selection


@pytest.fixture
def photographer_client(photographer_user) -> Client:
    client = Client()
    client.login(username="photographer", password="testpass123")
    return client


class TestCustomerList:
    def test_photographer_can_view(self, photographer_client, customer):
        resp = photographer_client.get(reverse("customer_list"))
        assert resp.status_code == 200
        assert b"Jane" in resp.content

    def test_inactive_hidden_by_default(self, photographer_client, customer):
        customer.is_active = False
        customer.save()
        resp = photographer_client.get(reverse("customer_list"))
        assert b"Jane" not in resp.content

    def test_inactive_shown_with_param(self, photographer_client, customer):
        customer.is_active = False
        customer.save()
        resp = photographer_client.get(reverse("customer_list") + "?show_inactive=1")
        assert b"Jane" in resp.content

    def test_customer_cannot_view(self, customer_user):
        client = Client()
        client.login(username="customer1", password="testpass123")
        resp = client.get(reverse("customer_list"))
        assert resp.status_code == 302


class TestCustomerAdd:
    def test_add_customer(self, photographer_client):
        resp = photographer_client.post(
            reverse("customer_add"),
            {
                "first_name": "Bob",
                "last_name": "Smith",
                "company_name": "Smith Co",
                "email": "bob@example.com",
                "phone": "555-9999",
            },
        )
        assert resp.status_code == 302
        assert Customer.objects.filter(user__first_name="Bob").exists()
        cust = Customer.objects.get(user__first_name="Bob")
        assert cust.company_name == "Smith Co"

    def test_add_creates_user(self, photographer_client):
        photographer_client.post(
            reverse("customer_add"),
            {
                "first_name": "Alice",
                "last_name": "Wonder",
                "company_name": "",
                "email": "alice@example.com",
                "phone": "",
            },
        )
        assert User.objects.filter(username="alice@example.com").exists()


class TestCustomerEdit:
    def test_edit_customer(self, photographer_client, customer):
        resp = photographer_client.post(
            reverse("customer_edit", args=[customer.pk]),
            {
                "first_name": "Janet",
                "last_name": "Doe",
                "company_name": "New Co",
                "email": "janet@example.com",
                "phone": "555-1234",
            },
        )
        assert resp.status_code == 302
        customer.refresh_from_db()
        customer.user.refresh_from_db()
        assert customer.user.first_name == "Janet"
        assert customer.company_name == "New Co"


class TestCustomerToggleActive:
    def test_deactivate(self, photographer_client, customer):
        assert customer.is_active is True
        photographer_client.post(reverse("customer_toggle_active", args=[customer.pk]))
        customer.refresh_from_db()
        assert customer.is_active is False
        customer.user.refresh_from_db()
        assert customer.user.is_active is False

    def test_reactivate(self, photographer_client, customer):
        customer.is_active = False
        customer.user.is_active = False
        customer.save()
        customer.user.save()
        photographer_client.post(reverse("customer_toggle_active", args=[customer.pk]))
        customer.refresh_from_db()
        assert customer.is_active is True


class TestCustomerDelete:
    def test_delete_with_no_data(self, photographer_client, db):
        user = User.objects.create_user(username="empty_cust", password="pass")
        cust = Customer.objects.create(user=user)
        resp = photographer_client.post(reverse("customer_delete", args=[cust.pk]))
        assert resp.status_code == 302
        assert not Customer.objects.filter(pk=cust.pk).exists()
        assert not User.objects.filter(pk=user.pk).exists()

    def test_delete_blocked_with_orders(
        self, photographer_client, customer, event_with_customer, order
    ):
        resp = photographer_client.post(reverse("customer_delete", args=[customer.pk]))
        assert resp.status_code == 302
        # Customer still exists
        assert Customer.objects.filter(pk=customer.pk).exists()

    def test_delete_blocked_with_events(
        self, photographer_client, customer, event_with_customer
    ):
        resp = photographer_client.post(reverse("customer_delete", args=[customer.pk]))
        assert resp.status_code == 302
        assert Customer.objects.filter(pk=customer.pk).exists()

    def test_delete_blocked_with_selections(
        self, photographer_client, customer, event_with_customer, photo
    ):
        Selection.objects.create(photo=photo, customer=customer, choice="digital")
        resp = photographer_client.post(reverse("customer_delete", args=[customer.pk]))
        assert resp.status_code == 302
        assert Customer.objects.filter(pk=customer.pk).exists()
