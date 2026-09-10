from django import forms

from .models import Student


class AddStudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ("name", "email", "phone", "course", "total_fee", "admission_date", "status")
        labels = {
            "name": "Full Name",
            "email": "Email",
            "phone": "Phone",
            "course": "Course",
            "total_fee": "Total Fee",
            "admission_date": "Admission Date",
            "status": "Status",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter full name"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "student@example.com"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional phone number"}),
            "course": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. B.Sc Computer Science"}),
            "total_fee": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}),
            "admission_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name == "status":
                field.widget.attrs["class"] = "form-select"
            else:
                field.widget.attrs.setdefault("class", "form-control")
            if field.required:
                field.widget.attrs["required"] = "required"
            if field_name == "name":
                field.widget.attrs.setdefault("placeholder", "Enter student full name")
            elif field_name == "email":
                field.widget.attrs.setdefault("placeholder", "student@example.com")

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Full name is required.")
        return name

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        if not email:
            raise forms.ValidationError("Email is required.")
        if Student.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A student with this email already exists.")
        return email.lower()

class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ("name", "email", "phone", "course", "total_fee", "admission_date", "status")
        labels = {
            "name": "Full Name",
            "email": "Email",
            "phone": "Phone",
            "course": "Course",
            "total_fee": "Total Fee",
            "admission_date": "Admission Date",
            "status": "Status",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "course": forms.TextInput(attrs={"class": "form-control"}),
            "total_fee": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "admission_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }
