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
