import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from splitbind.access.models import Organization, Recipient, Role, User

DEMO_ORGANIZATION_NAME = "SplitBind Synthetic Demo"
DEMO_ORGANIZATION_SLUG = "splitbind-demo"
DEMO_USERNAME = "demo-admin"
DEMO_RECIPIENT_REFERENCE = "synthetic-recipient-001"
DEMO_RECIPIENT_NAME = "Người nhận tổng hợp 001"


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
                slug=DEMO_ORGANIZATION_SLUG,
                defaults={"name": DEMO_ORGANIZATION_NAME},
            )
            if organization.name != DEMO_ORGANIZATION_NAME:
                raise CommandError("DEMO_SEED_CONFLICT")
            user, created = User.objects.get_or_create(
                username=DEMO_USERNAME,
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
            user.is_active = True
            user.set_password(password)
            user.save(update_fields=["is_staff", "is_active", "password"])

            recipient, _ = Recipient.objects.get_or_create(
                organization=organization,
                external_reference=DEMO_RECIPIENT_REFERENCE,
                defaults={"display_name": DEMO_RECIPIENT_NAME},
            )
            if recipient.display_name != DEMO_RECIPIENT_NAME:
                raise CommandError("DEMO_SEED_CONFLICT")

        self.stdout.write(
            f"username={DEMO_USERNAME} recipient_id={recipient.id} status=ready"
        )
