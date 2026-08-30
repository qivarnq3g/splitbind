from django.db import migrations, models


def refuse_output_evidence_rollback(apps, schema_editor):
    Issuance = apps.get_model("documents", "Issuance")
    if Issuance.objects.using(schema_editor.connection.alias).filter(output_deleted_at__isnull=False).exists():
        raise RuntimeError(
            "Cannot reverse documents.0004 while output deletion evidence exists; preserve or export cleanup evidence before retrying rollback."
        )


class Migration(migrations.Migration):
    dependencies = [("documents", "0003_pending_document_metadata")]

    operations = [
        migrations.AddField(
            model_name="issuance",
            name="output_deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(migrations.RunPython.noop, reverse_code=refuse_output_evidence_rollback),
    ]
