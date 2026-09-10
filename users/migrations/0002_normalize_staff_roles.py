from django.db import migrations


def promote_staff_users(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.objects.filter(is_staff=True).update(role="admin")


class Migration(migrations.Migration):
    dependencies = [("users", "0001_initial")]

    operations = [migrations.RunPython(promote_staff_users, migrations.RunPython.noop)]