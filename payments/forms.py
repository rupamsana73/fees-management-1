from django import forms

from students.models import Student

from .models import FeePayment


class FeePaymentForm(forms.ModelForm):
    class Meta:
        model = FeePayment
        fields = ("student", "amount_paid", "month", "remarks")
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "amount_paid": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "month": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "September 2026"}
            ),
            "remarks": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = Student.objects.order_by("name")
