import re
import secrets
import string

from django.contrib.auth import get_user_model
from django.db import transaction


User = get_user_model()


def normalize_name_for_username(full_name):
    cleaned = re.sub(r"[^a-zA-Z0-9\s.-]", " ", full_name or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return ".".join(part for part in cleaned.split() if part) or "student"


def generate_unique_username(full_name):
    base = normalize_name_for_username(full_name)
    candidate = base
    suffix = 2
    while User.objects.filter(username__iexact=candidate).exists():
        candidate = f"{base}{suffix}"
        suffix += 1
    return candidate


def generate_unique_student_id():
    from .models import Student

    existing_ids = set(Student.objects.values_list("student_id", flat=True))
    highest_number = 99
    for student_id in existing_ids:
        numbers = re.findall(r"\d+", student_id or "")
        if numbers:
            highest_number = max(highest_number, int(numbers[-1]))

    counter = highest_number + 1
    while True:
        candidate = f"STU{counter}"
        if candidate not in existing_ids:
            return candidate
        counter += 1


def generate_temporary_password(student_name, student_id):
    del student_name, student_id
    required = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("@!$%&*"),
    ]
    alphabet = string.ascii_letters + string.digits + "@!$%&*"
    required.extend(secrets.choice(alphabet) for _ in range(8))
    secrets.SystemRandom().shuffle(required)
    return "".join(required)


@transaction.atomic
def create_student_with_account(form_data, *, send_email_callback=None):
    from .models import Student

    name = (form_data.get("name") or "").strip()
    email = (form_data.get("email") or "").strip()
    course = (form_data.get("course") or "").strip()
    total_fee = form_data.get("total_fee")
    phone = (form_data.get("phone") or "").strip()
    admission_date = form_data.get("admission_date")
    status = form_data.get("status") or Student.Status.ACTIVE

    student_id = generate_unique_student_id()
    username = generate_unique_username(name)
    password = generate_temporary_password(name, student_id)
    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        role=User.Role.STUDENT,
        must_change_password=True,
    )
    student = Student.objects.create(
        user=user,
        student_id=student_id,
        name=name,
        email=email,
        phone=phone,
        course=course,
        total_fee=total_fee,
        admission_date=admission_date,
        status=status,
    )

    if send_email_callback:
        send_email_callback(student, username, password)

    return student, username, password
