from django.db import migrations, models


def refuse_cleanup_evidence_rollback(apps, schema_editor):
    UploadRequest = apps.get_model("uploads", "UploadRequest")
    if UploadRequest.objects.using(schema_editor.connection.alias).filter(
        models.Q(orphan_deleted_at__isnull=False)
        | models.Q(promotion_target_deleted_at__isnull=False)
        | models.Q(promotion_target_key__isnull=False)
    ).exists():
        raise RuntimeError(
            "Cannot reverse uploads.0005 while deletion evidence or promotion targets exist; "
            "resolve promotion cleanup ownership and preserve cleanup evidence before retrying rollback."
        )


class Migration(migrations.Migration):
    dependencies = [("uploads", "0004_upload_promotion")]

    operations = [
        migrations.AddField(
            model_name="uploadrequest",
            name="orphan_deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="uploadrequest",
            name="promotion_target_deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(migrations.RunPython.noop, reverse_code=refuse_cleanup_evidence_rollback),
    ]
