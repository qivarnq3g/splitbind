from django.db import migrations, models
from django.db.models import F, Q
from django.utils import timezone


def backfill_promotion_status_changed_at(apps, schema_editor):
    UploadRequest = apps.get_model("uploads", "UploadRequest")
    uploads = UploadRequest.objects.using(schema_editor.connection.alias)
    # A legacy COPYING/FAILED row may represent work that became active just
    # before this migration. Its true transition time is unknowable, so an old
    # creation time would fabricate staleness and permit immediate deletion.
    # Give active, cleanup-eligible states a migration-time safety baseline.
    uploads.filter(
        promotion_status_changed_at__isnull=True,
        promotion_status__in=["copying", "failed"],
    ).update(promotion_status_changed_at=timezone.now())
    # NONE has existed since creation. ATTACHED does not use this clock for
    # retention eligibility, so preserve its legacy historical lower bound.
    uploads.filter(
        promotion_status_changed_at__isnull=True,
    ).update(promotion_status_changed_at=F("created_at"))


def refuse_promotion_clock_rollback(apps, schema_editor):
    UploadRequest = apps.get_model("uploads", "UploadRequest")
    if UploadRequest.objects.using(schema_editor.connection.alias).filter(
        Q(promotion_status__in=["copying", "attached", "failed"])
        | Q(promotion_target_key__isnull=False)
    ).exists():
        raise RuntimeError(
            "Cannot reverse uploads.0007 while promotion lifecycle evidence exists; "
            "resolve promotion cleanup ownership and preserve the durable promotion "
            "transition clock before retrying rollback."
        )


class Migration(migrations.Migration):
    dependencies = [("uploads", "0006_alter_uploadrequest_options")]

    operations = [
        migrations.AddField(
            model_name="uploadrequest",
            name="promotion_status_changed_at",
            field=models.DateTimeField(null=True),
        ),
        migrations.RunPython(
            backfill_promotion_status_changed_at,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="uploadrequest",
            name="promotion_status_changed_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.RunPython(
            migrations.RunPython.noop,
            reverse_code=refuse_promotion_clock_rollback,
        ),
    ]
