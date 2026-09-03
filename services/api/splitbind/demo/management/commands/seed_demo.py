import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from splitbind.access.models import Organization, Recipient, Role, User


class Command(BaseCommand):
    help = "Seed the local presentation database with synthetic identities."

    def handle(self, *args, **options):
        if (
            getattr(settings, "ENVIRONMENT", "") != "local"
            or not getattr(settings, "SPLITBIND_DEMO_MODE", False)
        ):
            raise CommandError("DEMO_MODE_DISABLED")
        password = os.environ.get("SPLITBIND_DEMO_LOGIN_PASSWORD", "")
        if not password:
            raise CommandError("SPLITBIND_DEMO_LOGIN_PASSWORD_REQUIRED")

        with transaction.atomic():
            organization, _ = Organization.objects.get_or_create(
                slug="splitbind-demo",
                defaults={"name": "SplitBind Synthetic Demo"},
            )
            user, created = User.objects.get_or_create(
                username="demo-admin",
                defaults={
                    "organization": organization,
                    "role": Role.ADMINISTRATOR,
                    "is_staff": True,
                    "is_superuser": False,
                },
            )
            if not created and (
                user.organization_id != organization.id
                or user.role != Role.ADMINISTRATOR
                or user.is_superuser
            ):
                raise CommandError("DEMO_SEED_CONFLICT")
            user.is_staff = True
            user.set_password(password)
            user.save(update_fields=["is_staff", "password"])

            recipient, _ = Recipient.objects.get_or_create(
                organization=organization,
                external_reference="synthetic-recipient-001",
                defaults={"display_name": "Người nhận tổng hợp 001"},
            )
            if recipient.display_name != "Người nhận tổng hợp 001":
                raise CommandError("DEMO_SEED_CONFLICT")

        self.stdout.write(
            f"username=demo-admin recipient_id={recipient.id} status=ready"
        )
