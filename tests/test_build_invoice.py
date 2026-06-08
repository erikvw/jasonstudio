"""Tests for the _build_invoice helper function."""
from decimal import Decimal

from jasonstudio.accounts.models import Invoice
from jasonstudio.gallery.models import Selection
from jasonstudio.gallery.views import _build_invoice


class TestBuildInvoice:
    def test_creates_invoice_for_order(self, order):
        invoice = _build_invoice(order)
        assert isinstance(invoice, Invoice)
        assert invoice.pk is not None
        assert invoice.order == order

    def test_always_includes_photography_line(self, order):
        invoice = _build_invoice(order)
        items = list(invoice.line_items.all())
        assert items[0].description == "Photography"
        assert items[0].qty == Decimal("2.00")
        assert items[0].unit_cost == Decimal("150.00")
        assert items[0].price == Decimal("300.00")

    def test_digital_selections_bundled(self, order, photos, customer):
        for p in photos[:3]:
            Selection.objects.create(photo=p, customer=customer, choice="digital")
        invoice = _build_invoice(order)
        digital_item = invoice.line_items.filter(description="Digital images").first()
        assert digital_item is not None
        assert digital_item.qty == Decimal("3")

    def test_print_selections_individual(self, order, photos, customer):
        Selection.objects.create(
            photo=photos[0], customer=customer, choice="both", print_size="5x7"
        )
        Selection.objects.create(
            photo=photos[1], customer=customer, choice="both", print_size="8x10"
        )
        invoice = _build_invoice(order)
        print_items = invoice.line_items.filter(description__startswith="Print & Digital")
        assert print_items.count() == 2
        descs = list(print_items.values_list("description", flat=True))
        assert any("5×7" in d for d in descs)
        assert any("8×10" in d for d in descs)

    def test_calculates_subtotal(self, order, photos, customer):
        Selection.objects.create(photo=photos[0], customer=customer, choice="digital")
        invoice = _build_invoice(order)
        # Only photographer fee contributes: 2h * $150 = $300
        assert invoice.subtotal == Decimal("300.00")

    def test_calculates_tax(self, order, photos, customer, photographer_user):
        Selection.objects.create(photo=photos[0], customer=customer, choice="digital")
        invoice = _build_invoice(order)
        # 13% of $300 = $39
        assert invoice.tax_rate == Decimal("13.00")
        assert invoice.tax_amount == Decimal("39.00")
        assert invoice.amount_due == Decimal("339.00")

    def test_reuses_existing_invoice(self, order, photos, customer):
        Selection.objects.create(photo=photos[0], customer=customer, choice="digital")
        invoice1 = _build_invoice(order)
        invoice2 = _build_invoice(order)
        assert invoice1.pk == invoice2.pk
        assert Invoice.objects.filter(order=order).count() == 1

    def test_updates_line_items_on_rebuild(self, order, photos, customer):
        Selection.objects.create(photo=photos[0], customer=customer, choice="digital")
        # Add another selection and rebuild
        Selection.objects.create(photo=photos[1], customer=customer, choice="both", print_size="4x6")
        invoice = _build_invoice(order)
        # Should have Photography + Print item + Digital bundle = 3
        assert invoice.line_items.count() == 3

    def test_no_selections_only_photography_line(self, order):
        invoice = _build_invoice(order)
        assert invoice.line_items.count() == 1
        assert invoice.line_items.first().description == "Photography"

    def test_zero_hour_photography_still_shown(self, event_with_customer, customer):
        from jasonstudio.accounts.models import Order

        order = Order.objects.create(
            event=event_with_customer,
            customer=customer,
            photographer_hours=Decimal("0"),
            photographer_rate=Decimal("0"),
        )
        invoice = _build_invoice(order)
        assert invoice.line_items.filter(description="Photography").exists()

    def test_deposit_reduces_amount_due(self, order, photos, customer, photographer_user):
        Selection.objects.create(photo=photos[0], customer=customer, choice="digital")
        order.deposit_amount = Decimal("100.00")
        order.save(update_fields=["deposit_amount"])
        invoice = _build_invoice(order)
        # subtotal=300, deposit=100, tax=13% of 300=39 → amount_due=239
        assert invoice.deposit == Decimal("100.00")
        assert invoice.subtotal == Decimal("300.00")
        assert invoice.tax_amount == Decimal("39.00")
        assert invoice.amount_due == Decimal("239.00")

    def test_zero_deposit_amount_due_equals_subtotal_plus_tax(self, order, photos, customer, photographer_user):
        Selection.objects.create(photo=photos[0], customer=customer, choice="digital")
        invoice = _build_invoice(order)
        # subtotal=300, deposit=0, tax=39 → amount_due=339
        assert invoice.deposit == Decimal("0")
        assert invoice.amount_due == Decimal("339.00")
