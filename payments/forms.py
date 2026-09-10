from decimal import Decimal

from django import forms

from students.models import Student

from .models import FeePayment


class FeePaymentForm(forms.ModelForm):
    class Meta:
        model = FeePayment
        fields = (
            "student",
            "amount_paid",
            "month",
            "payment_method",
            "transaction_id",
            "remarks",
        )
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "amount_paid": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "month": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "September 2026"}
            ),
            "payment_method": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "UPI / Cash / Bank Transfer"}
            ),
            "transaction_id": forms.TextInput(attrs={"class": "form-control", "placeholder": "TXN123456"}),
            "remarks": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = Student.objects.order_by("name")

    def clean_amount_paid(self):
        amount_paid = self.cleaned_data["amount_paid"]
        if amount_paid <= Decimal("0.00"):
            raise forms.ValidationError("Payment amount must be greater than zero.")
        return amount_paid

    def clean_transaction_id(self):
        transaction_id = self.cleaned_data["transaction_id"].strip()
        if transaction_id and FeePayment.objects.filter(transaction_id=transaction_id).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This transaction ID has already been recorded.")
        return transaction_id
