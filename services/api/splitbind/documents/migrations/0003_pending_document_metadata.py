import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("documents", "0002_verification_verification_status_stable")]

    operations = [
        migrations.RemoveConstraint(
            model_name="document", name="document_sha256_canonical",
        ),
        migrations.RenameField(
            model_name="document",
            old_name="source_sha256",
            new_name="expected_source_sha256",
        ),
        migrations.AlterField(
            model_name="document",
            name="page_count",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                validators=[django.core.validators.MinValueValidator(1)],
            ),
        ),
        migrations.AddConstraint(
            model_name="document",
            constraint=models.CheckConstraint(
                condition=models.Q(expected_source_sha256__regex="^[0-9a-f]{64}$"),
                name="document_sha256_canonical",
            ),
        ),
        migrations.AddConstraint(
            model_name="document",
            constraint=models.CheckConstraint(
                condition=models.Q(page_count__isnull=True)
                | models.Q(page_count__gte=1, page_count__lte=50),
                name="document_page_count_pending_or_1_50",
            ),
        ),
    ]
