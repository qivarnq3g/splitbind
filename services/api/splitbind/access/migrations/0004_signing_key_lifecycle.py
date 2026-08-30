from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("access", "0003_alter_user_managers")]

    operations = [
        migrations.AddConstraint(
            model_name="signingkey",
            constraint=models.CheckConstraint(
                condition=models.Q(status__in=["active", "verify_only", "revoked"]),
                name="signkey_status_stable",
            ),
        ),
        migrations.AddConstraint(
            model_name="signingkey",
            constraint=models.CheckConstraint(
                condition=models.Q(valid_until__isnull=True) | models.Q(valid_until__gt=models.F("valid_from")),
                name="signkey_valid_window_ordered",
            ),
        ),
        migrations.AddConstraint(
            model_name="signingkey",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(status="revoked", revoked_at__isnull=False)
                    | models.Q(status__in=["active", "verify_only"], revoked_at__isnull=True)
                ),
                name="signkey_revocation_state",
            ),
        ),
    ]
