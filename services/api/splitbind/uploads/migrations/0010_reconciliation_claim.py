from django.db import migrations, models


def refuse_live_claim_rollback(apps, schema_editor):
    Schedule = apps.get_model("uploads", "CleanupScheduleState")
    live = Schedule.objects.using(schema_editor.connection.alias).filter(
        reconciliation_claim_upload_id__isnull=False,
    ).exists()
    if live:
        raise RuntimeError(
            "Cannot reverse uploads.0010 while a reconciliation claim is live; "
            "complete or safely clear the claim before retrying rollback."
        )


class Migration(migrations.Migration):
    dependencies = [("uploads", "0009_cleanup_schedule_fairness")]

    operations = [
        migrations.AddField(
            model_name="cleanupschedulestate",
            name="reconciliation_claim_upload_id",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="cleanupschedulestate",
            name="reconciliation_claim_token",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="cleanupschedulestate",
            name="reconciliation_claim_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="cleanupschedulestate",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        ("reconciliation_claim_expires_at__isnull", True),
                        ("reconciliation_claim_token__isnull", True),
                        ("reconciliation_claim_upload_id__isnull", True),
                    )
                    | models.Q(
                        ("reconciliation_claim_expires_at__isnull", False),
                        ("reconciliation_claim_token__isnull", False),
                        ("reconciliation_claim_upload_id__isnull", False),
                    )
                ),
                name="cleanup_schedule_claim_complete",
            ),
        ),
        migrations.RunPython(
            migrations.RunPython.noop,
            reverse_code=refuse_live_claim_rollback,
        ),
    ]
