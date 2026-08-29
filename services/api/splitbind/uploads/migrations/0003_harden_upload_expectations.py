import django.core.validators
from django.db import migrations, models


MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class Migration(migrations.Migration):
    dependencies = [
        ("uploads", "0002_alter_uploadrequest_size_bytes"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="uploadrequest",
            name="upload_sha256_canonical",
        ),
        migrations.RenameField(
            model_name="uploadrequest",
            old_name="sha256",
            new_name="expected_sha256",
        ),
        migrations.AlterField(
            model_name="uploadrequest",
            name="size_bytes",
            field=models.PositiveBigIntegerField(
                blank=True,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(MAX_UPLOAD_BYTES),
                ],
            ),
        ),
        migrations.AddConstraint(
            model_name="uploadrequest",
            constraint=models.CheckConstraint(
                condition=models.Q(expected_sha256__isnull=True)
                | models.Q(expected_sha256__regex="^[0-9a-f]{64}$"),
                name="upload_expected_sha256_canonical",
            ),
        ),
        migrations.AddConstraint(
            model_name="uploadrequest",
            constraint=models.CheckConstraint(
                condition=models.Q(size_bytes__isnull=True)
                | models.Q(size_bytes__gte=1, size_bytes__lte=MAX_UPLOAD_BYTES),
                name="upload_size_legacy_null_or_bounded",
            ),
        ),
    ]
