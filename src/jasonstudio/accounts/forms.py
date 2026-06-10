from django import forms


class CustomerForm(forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    company_name = forms.CharField(max_length=200, required=False)
    email = forms.EmailField(required=False)
    phone = forms.CharField(max_length=20, required=False)


class PhotographerSetupForm(forms.Form):
    business_name = forms.CharField(max_length=200)
    phone = forms.CharField(max_length=20, required=False)
    email = forms.EmailField(required=False)
    address = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)
    payment_instructions = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text="Payment details shown on invoices (bank, Venmo, etc.).",
    )
    payment_terms = forms.CharField(
        max_length=100,
        initial="Due within 30 days",
        required=False,
        help_text="e.g. 'Due within 30 days', 'Due on receipt'.",
    )
    tax_rate = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        initial=0,
        required=False,
        help_text="Tax percentage (e.g. 13.00 for 13%).",
    )
