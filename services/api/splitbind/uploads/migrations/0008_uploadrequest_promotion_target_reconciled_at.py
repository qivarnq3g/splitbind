from django.db import migrations, models


def refuse_reconciliation_evidence_rollback(apps, schema_editor):
    UploadRequest = apps.get_model("uploads", "UploadRequest")
    if UploadRequest.objects.using(schema_editor.connection.alias).filter(
        promotion_target_reconciled_at__isnull=False,
    ).exists():
        raise RuntimeError(
            "Cannot reverse uploads.0008 while promotion reconciliation evidence exists; "
            "preserve the durable retry observation before retrying rollback."
        )


class Migration(migrations.Migration):
    dependencies = [("uploads", "0007_uploadrequest_promotion_status_changed_at")]

    operations = [
        migrations.AddField(
            model_name="uploadrequest",
            name="promotion_target_reconciled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(
            migrations.RunPython.noop,
            reverse_code=refuse_reconciliation_evidence_rollback,
        ),
    ]
