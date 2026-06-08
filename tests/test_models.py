import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from jasonstudio.accounts.models import Invoice, InvoiceLineItem, Order, Payment
from jasonstudio.gallery.models import (
    Event,
    Selection,
    ShareLink,
)


class TestOrderModel:
    def test_ref_auto_generated(self, order):
        assert order.ref.startswith("ORD-")
        assert len(order.ref) == 9  # ORD-00001

    def test_ref_sequential(self, event_with_customer, customer, db):
        o1 = Order.objects.create(event=event_with_customer, customer=customer)
        # Create another event/customer for a second order
        from django.contrib.auth.models import User

        from jasonstudio.accounts.models import Customer as CustomerModel

        user2 = User.objects.create_user(username="cust2", password="pass")
        c2 = CustomerModel.objects.create(user=user2)
        event2 = Event.objects.create(name="Event 2", date=datetime.date(2025, 7, 1))
        event2.customers.add(c2)
        o2 = Order.objects.create(event=event2, customer=c2)
        num1 = int(o1.ref.replace("ORD-", ""))
        num2 = int(o2.ref.replace("ORD-", ""))
        assert num2 == num1 + 1

    def test_paid_at_auto_set_on_paid(self, order):
        assert order.paid_at is None
        order.status = Order.Status.PAID
        order.save()
        assert order.paid_at is not None

    def test_paid_at_not_overwritten(self, order):
        order.status = Order.Status.PAID
        order.save()
        original_paid_at = order.paid_at
        order.notes = "updated"
        order.save()
        assert order.paid_at == original_paid_at

    def test_is_paid(self, order):
        assert order.is_paid is False
        order.status = Order.Status.PAID
        order.save()
        assert order.is_paid is True

    def test_is_paid_includes_later_statuses(self, order):
        for status in [Order.Status.IN_PROGRESS, Order.Status.DELIVERED]:
            order.status = status
            assert order.is_paid is True

    def test_download_available_when_paid(self, paid_order):
        assert paid_order.download_available is True

    def test_download_not_available_when_unpaid(self, order):
        assert order.download_available is False

    def test_download_expires_after_30_days(self, paid_order):
        paid_order.paid_at = timezone.now() - datetime.timedelta(days=31)
        paid_order.save()
        assert paid_order.download_available is False

    def test_download_available_within_30_days(self, paid_order):
        paid_order.paid_at = timezone.now() - datetime.timedelta(days=29)
        paid_order.save()
        assert paid_order.download_available is True

    def test_download_available_legacy_no_paid_at(self, order):
        """Orders marked paid before paid_at field existed should allow download."""
        order.status = Order.Status.PAID
        order.save()
        # Simulate legacy by clearing paid_at
        Order.objects.filter(pk=order.pk).update(paid_at=None)
        order.refresh_from_db()
        assert order.paid_at is None
        assert order.download_available is True


class TestInvoiceModel:
    def test_invoice_number_auto_generated(self, order):
        invoice = Invoice.objects.create(order=order)
        assert invoice.invoice_number.startswith("INV-")
        assert len(invoice.invoice_number) == 9

    def test_invoice_number_sequential(self, order):
        inv1 = Invoice.objects.create(order=order)
        inv2 = Invoice.objects.create(order=order)
        num1 = int(inv1.invoice_number.replace("INV-", ""))
        num2 = int(inv2.invoice_number.replace("INV-", ""))
        assert num2 == num1 + 1

    def test_issued_at_set_on_issued_status(self, order):
        invoice = Invoice.objects.create(order=order, status=Invoice.Status.ISSUED)
        assert invoice.issued_at is not None

    def test_issued_at_not_set_on_draft(self, order):
        invoice = Invoice.objects.create(order=order, status=Invoice.Status.DRAFT)
        assert invoice.issued_at is None

    def test_str(self, order):
        invoice = Invoice.objects.create(order=order)
        assert order.ref in str(invoice)
        assert invoice.invoice_number in str(invoice)


class TestInvoiceLineItemModel:
    def test_ordering(self, order):
        invoice = Invoice.objects.create(order=order)
        item2 = InvoiceLineItem.objects.create(
            invoice=invoice, sort_order=2, description="Second"
        )
        item1 = InvoiceLineItem.objects.create(
            invoice=invoice, sort_order=1, description="First"
        )
        items = list(invoice.line_items.all())
        assert items[0] == item1
        assert items[1] == item2


class TestSelectionModel:
    def test_unique_per_photo_customer(self, photo, customer):
        Selection.objects.create(photo=photo, customer=customer, choice="digital")
        with pytest.raises(Exception):
            Selection.objects.create(photo=photo, customer=customer, choice="both")

    def test_print_size_choices(self):
        assert Selection.PrintSize.SIZE_4X5_3 == "4x5.3"
        assert Selection.PrintSize.SIZE_8X10 == "8x10"


class TestShareLinkModel:
    def test_code_generation_length(self, db):
        code = ShareLink.generate_code()
        assert len(code) == 6
        assert code.isalnum()

    def test_code_unique(self, paid_order):
        link = ShareLink.objects.create(
            order=paid_order, code=ShareLink.generate_code()
        )
        assert link.code

    def test_is_valid_when_active_and_download_available(self, paid_order):
        link = ShareLink.objects.create(
            order=paid_order, code=ShareLink.generate_code()
        )
        assert link.is_valid is True

    def test_is_invalid_when_deactivated(self, paid_order):
        link = ShareLink.objects.create(
            order=paid_order, code=ShareLink.generate_code(), is_active=False
        )
        assert link.is_valid is False

    def test_is_invalid_when_download_expired(self, paid_order):
        paid_order.paid_at = timezone.now() - datetime.timedelta(days=31)
        paid_order.save()
        link = ShareLink.objects.create(
            order=paid_order, code=ShareLink.generate_code()
        )
        assert link.is_valid is False

    def test_is_invalid_when_event_archived(self, paid_order):
        paid_order.event.status = Event.Status.ARCHIVED
        paid_order.event.save()
        link = ShareLink.objects.create(
            order=paid_order, code=ShareLink.generate_code()
        )
        assert link.is_valid is False


class TestPaymentModel:
    def test_payment_linked_to_invoice(self, order):
        invoice = Invoice.objects.create(order=order)
        payment = Payment.objects.create(
            invoice=invoice, amount=Decimal("100.00"), method=Payment.Method.ETRANSFER,
        )
        assert payment.invoice == invoice
        assert invoice.payments.count() == 1

    def test_str_with_invoice(self, order):
        invoice = Invoice.objects.create(order=order)
        payment = Payment.objects.create(
            invoice=invoice, amount=Decimal("50.00"),
        )
        assert "$50.00" in str(payment)
        assert invoice.invoice_number in str(payment)

    def test_str_without_invoice(self, order):
        payment = Payment.objects.create(amount=Decimal("25.00"))
        assert "$25.00" in str(payment)
