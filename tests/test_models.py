import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from jasonstudio.accounts.models import (
    Invoice,
    InvoiceLineItem,
    Order,
    Payment,
    Quotation,
)
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
        q1 = Quotation.objects.create(event=event_with_customer, customer=customer)
        o1 = Order.objects.create(
            event=event_with_customer, customer=customer, quotation=q1
        )
        # Create another event/customer for a second order
        from django.contrib.auth.models import User

        from jasonstudio.accounts.models import Customer as CustomerModel

        user2 = User.objects.create_user(username="cust2", password="pass")
        c2 = CustomerModel.objects.create(user=user2)
        event2 = Event.objects.create(name="Event 2", date=datetime.date(2025, 7, 1))
        event2.customers.add(c2)
        q2 = Quotation.objects.create(event=event2, customer=c2)
        o2 = Order.objects.create(event=event2, customer=c2, quotation=q2)
        num1 = int(o1.ref.replace("ORD-", ""))
        num2 = int(o2.ref.replace("ORD-", ""))
        assert num2 == num1 + 1

    def test_is_paid_false_without_payment(self, order):
        assert order.is_paid is False

    def test_is_paid_true_with_payment(self, paid_order):
        assert paid_order.is_paid is True

    def test_paid_at_returns_payment_date(self, paid_order):
        assert paid_order.paid_at is not None

    def test_paid_at_none_without_payment(self, order):
        assert order.paid_at is None

    def test_download_available_when_paid(self, paid_order):
        assert paid_order.download_available is True

    def test_download_not_available_when_unpaid(self, order):
        assert order.download_available is False

    def test_download_expires_after_30_days(self, paid_order, invoice):
        # Move the payment's date_created back 31 days
        payment = invoice.payments.first()
        Payment.objects.filter(pk=payment.pk).update(
            date_created=timezone.now() - datetime.timedelta(days=31)
        )
        assert paid_order.download_available is False

    def test_download_available_within_30_days(self, paid_order, invoice):
        payment = invoice.payments.first()
        Payment.objects.filter(pk=payment.pk).update(
            date_created=timezone.now() - datetime.timedelta(days=29)
        )
        assert paid_order.download_available is True


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

    def test_is_invalid_when_download_expired(self, paid_order, invoice):
        # Move payment date_created back 31 days to expire downloads
        payment = invoice.payments.first()
        Payment.objects.filter(pk=payment.pk).update(
            date_created=timezone.now() - datetime.timedelta(days=31)
        )
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
            invoice=invoice,
            amount=Decimal("100.00"),
            method=Payment.Method.ETRANSFER,
        )
        assert payment.invoice == invoice
        assert invoice.payments.count() == 1

    def test_receipt_number_auto_generated(self, order):
        invoice = Invoice.objects.create(order=order)
        payment = Payment.objects.create(
            invoice=invoice,
            amount=Decimal("50.00"),
        )
        assert payment.receipt_number.startswith("REC-")
        assert len(payment.receipt_number) == 9

    def test_str_contains_receipt_and_amount(self, order):
        invoice = Invoice.objects.create(order=order)
        payment = Payment.objects.create(
            invoice=invoice,
            amount=Decimal("50.00"),
        )
        assert "$50.00" in str(payment)
        assert payment.receipt_number in str(payment)
        assert invoice.invoice_number in str(payment)

    def test_date_defaults_to_today(self, order):
        invoice = Invoice.objects.create(order=order)
        payment = Payment.objects.create(invoice=invoice, amount=Decimal("10.00"))
        assert payment.date == timezone.now().date()

    def test_payment_marks_invoice_as_paid(self, order):
        invoice = Invoice.objects.create(order=order)
        assert invoice.status == Invoice.Status.DRAFT
        Payment.objects.create(
            invoice=invoice,
            amount=Decimal("100.00"),
        )
        invoice.refresh_from_db()
        assert invoice.status == Invoice.Status.PAID

    def test_payment_makes_order_is_paid_true(self, order):
        invoice = Invoice.objects.create(order=order)
        assert order.is_paid is False
        Payment.objects.create(
            invoice=invoice,
            amount=Decimal("100.00"),
        )
        assert order.is_paid is True


class TestDateChainValidation:
    """Ensure quotation.date ≤ order.date ≤ invoice.date ≤ payment.date."""

    def test_order_date_before_quotation_raises(self, quotation):
        from django.core.exceptions import ValidationError

        quotation.date = datetime.date(2025, 6, 15)
        quotation.save(update_fields=["date"])
        order = Order(
            event=quotation.event,
            customer=quotation.customer,
            quotation=quotation,
            date=datetime.date(2025, 6, 14),
        )
        with pytest.raises(ValidationError) as exc_info:
            order.clean()
        assert "date" in exc_info.value.message_dict

    def test_order_date_equal_to_quotation_ok(self, quotation):
        quotation.date = datetime.date(2025, 6, 15)
        quotation.save(update_fields=["date"])
        order = Order(
            event=quotation.event,
            customer=quotation.customer,
            quotation=quotation,
            date=datetime.date(2025, 6, 15),
        )
        order.clean()  # should not raise

    def test_invoice_date_before_order_raises(self, order):
        from django.core.exceptions import ValidationError

        order.date = datetime.date(2025, 6, 15)
        order.save(update_fields=["date"])
        invoice = Invoice(
            order=order,
            date=datetime.date(2025, 6, 14),
        )
        with pytest.raises(ValidationError) as exc_info:
            invoice.clean()
        assert "date" in exc_info.value.message_dict

    def test_invoice_date_equal_to_order_ok(self, order):
        order.date = datetime.date(2025, 6, 15)
        order.save(update_fields=["date"])
        invoice = Invoice(order=order, date=datetime.date(2025, 6, 15))
        invoice.clean()  # should not raise

    def test_payment_date_before_invoice_raises(self, order):
        from django.core.exceptions import ValidationError

        invoice = Invoice.objects.create(order=order, date=datetime.date(2025, 6, 15))
        payment = Payment(
            invoice=invoice,
            amount=Decimal("10.00"),
            date=datetime.date(2025, 6, 14),
        )
        with pytest.raises(ValidationError) as exc_info:
            payment.clean()
        assert "date" in exc_info.value.message_dict

    def test_payment_date_equal_to_invoice_ok(self, order):
        invoice = Invoice.objects.create(order=order, date=datetime.date(2025, 6, 15))
        payment = Payment(
            invoice=invoice,
            amount=Decimal("10.00"),
            date=datetime.date(2025, 6, 15),
        )
        payment.clean()  # should not raise


class TestAuditFields:
    """Verify audit fields are auto-populated."""

    def test_date_created_auto_set(self, order):
        assert order.date_created is not None

    def test_date_modified_auto_set(self, order):
        assert order.date_modified is not None

    def test_history_recorded(self, quotation):
        assert quotation.history.count() >= 1
