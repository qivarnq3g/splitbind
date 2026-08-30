from django.db import migrations, models


def create_schedule(apps, schema_editor):
    Schedule = apps.get_model("uploads", "CleanupScheduleState")
    Schedule.objects.using(schema_editor.connection.alias).create(
        id=1, next_lane="ordinary", reconciliation_cursor_at=None,
        reconciliation_cursor_id=None, has_run=False,
    )


def refuse_used_schedule_rollback(apps, schema_editor):
    Schedule = apps.get_model("uploads", "CleanupScheduleState")
    if Schedule.objects.using(schema_editor.connection.alias).filter(has_run=True).exists():
        raise RuntimeError(
            "Cannot reverse uploads.0009 after the durable cleanup scheduler has run; "
            "preserve its fairness position before retrying rollback."
        )


class Migration(migrations.Migration):
    dependencies = [("uploads", "0008_uploadrequest_promotion_target_reconciled_at")]

    operations = [
        migrations.CreateModel(
            name="CleanupScheduleState",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1, editable=False, primary_key=True, serialize=False,
                    ),
                ),
                (
                    "next_lane",
                    models.CharField(
                        choices=[
                            ("ordinary", "Ordinary"),
                            ("reconciliation", "Reconciliation"),
                        ],
                        default="ordinary",
                        max_length=16,
                    ),
                ),
                ("reconciliation_cursor_at", models.DateTimeField(blank=True, null=True)),
                ("reconciliation_cursor_id", models.UUIDField(blank=True, null=True)),
                ("has_run", models.BooleanField(default=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "base_manager_name": "objects",
                "default_manager_name": "objects",
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("id", 1)),
                        name="cleanup_schedule_singleton",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("next_lane__in", ["ordinary", "reconciliation"])),
                        name="cleanup_schedule_lane_stable",
                    ),
                    models.CheckConstraint(
                        condition=(
                            models.Q(
                                ("reconciliation_cursor_at__isnull", True),
                                ("reconciliation_cursor_id__isnull", True),
                            )
                            | models.Q(
                                ("reconciliation_cursor_at__isnull", False),
                                ("reconciliation_cursor_id__isnull", False),
                            )
                        ),
                        name="cleanup_schedule_cursor_complete",
                    ),
                ],
            },
        ),
        migrations.AddIndex(
            model_name="uploadrequest",
            index=models.Index(
                fields=[
                    "promotion_status", "promotion_target_deleted_at",
                    "promotion_status_changed_at", "id",
                ],
                name="upload_stale_scan_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="uploadrequest",
            index=models.Index(
                fields=[
                    "promotion_target_deleted_at", "id",
                ],
                name="upload_reconcile_cursor_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="uploadrequest",
            index=models.Index(
                fields=["orphan_deleted_at", "created_at", "id"],
                name="upload_orphan_scan_idx",
            ),
        ),
        migrations.RunPython(create_schedule, reverse_code=migrations.RunPython.noop),
        migrations.RunPython(
            migrations.RunPython.noop,
            reverse_code=refuse_used_schedule_rollback,
        ),
    ]
