from django.db import migrations, models


def validate_legacy_signing_keys(apps, schema_editor):
    SigningKey = apps.get_model("access", "SigningKey")
    keys = SigningKey.objects.using(schema_editor.connection.alias)
    invalid = keys.exclude(status__in=["active", "verify_only", "revoked"]).filter()
    invalid = invalid | keys.filter(valid_until__isnull=False, valid_until__lte=models.F("valid_from"))
    invalid = invalid | keys.filter(status="revoked", revoked_at__isnull=True)
    invalid = invalid | keys.filter(status__in=["active", "verify_only"], revoked_at__isnull=False)
    if invalid.exists():
        raise RuntimeError(
            "Cannot apply access.0004: invalid legacy signing-key lifecycle rows exist; "
            "repair or export the registry evidence before retrying migration."
        )


def refuse_lifecycle_guard_rollback(apps, schema_editor):
    SigningKey = apps.get_model("access", "SigningKey")
    if SigningKey.objects.using(schema_editor.connection.alias).exists():
        raise RuntimeError(
            "Cannot reverse access.0004 while signing-key registry evidence exists; "
            "preserve or export the registry and maintain lifecycle guards before retrying rollback."
        )


class Migration(migrations.Migration):
    dependencies = [("access", "0003_alter_user_managers")]

    operations = [
        migrations.RunPython(validate_legacy_signing_keys, reverse_code=migrations.RunPython.noop),
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
        migrations.RunPython(
            migrations.RunPython.noop,
            reverse_code=refuse_lifecycle_guard_rollback,
        ),
    ]
