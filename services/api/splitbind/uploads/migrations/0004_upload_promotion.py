from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("uploads", "0003_harden_upload_expectations")]

    operations = [
        migrations.AddField(
            model_name="uploadrequest",
            name="promotion_target_key",
            field=models.CharField(blank=True, max_length=1024, null=True),
        ),
        migrations.AddField(
            model_name="uploadrequest",
            name="promotion_status",
            field=models.CharField(
                choices=[
                    ("none", "None"),
                    ("copying", "Copying"),
                    ("attached", "Attached"),
                    ("failed", "Failed"),
                ],
                default="none",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="uploadrequest",
            name="safe_error_code",
            field=models.CharField(blank=True, max_length=80, null=True),
        ),
        migrations.AddConstraint(
            model_name="uploadrequest",
            constraint=models.CheckConstraint(
                condition=models.Q(promotion_status__in=["none", "copying", "attached", "failed"]),
                name="upload_promotion_status_stable",
            ),
        ),
        migrations.AddConstraint(
            model_name="uploadrequest",
            constraint=models.CheckConstraint(
                condition=models.Q(promotion_status="none", promotion_target_key__isnull=True)
                | models.Q(
                    promotion_status__in=["copying", "attached", "failed"],
                    promotion_target_key__isnull=False,
                ),
                name="upload_promotion_target_state",
            ),
        ),
        migrations.AddConstraint(
            model_name="uploadrequest",
            constraint=models.CheckConstraint(
                condition=~models.Q(promotion_status="failed")
                | models.Q(safe_error_code__isnull=False),
                name="upload_failed_has_safe_code",
            ),
        ),
    ]
