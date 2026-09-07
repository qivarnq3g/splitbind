import os

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from splitbind.access.models import Organization, Role, User
from splitbind.release.mode import integrity_release_enabled


class Command(BaseCommand):
    help = "Create the initial production organization and administrator once."

    def add_arguments(self, parser):
        parser.add_argument("--organization-name", required=True)
        parser.add_argument("--organization-slug", required=True)
        parser.add_argument("--username", required=True)

    def handle(self, *args, **options):
        if settings.ENVIRONMENT != "production" or not integrity_release_enabled(
            settings.SPLITBIND_RELEASE_MODE
        ):
            raise CommandError("INTEGRITY_RELEASE_REQUIRED")

        password = os.environ.get("SPLITBIND_BOOTSTRAP_PASSWORD", "")
        if not password:
            raise CommandError("SPLITBIND_BOOTSTRAP_PASSWORD_REQUIRED")

        organization_name = options["organization_name"].strip()
        organization_slug = options["organization_slug"].strip()
        username = options["username"].strip()
        if not organization_name or not organization_slug or not username:
            raise CommandError("BOOTSTRAP_IDENTITY_REQUIRED")

        with transaction.atomic():
            organization = Organization.objects.filter(slug=organization_slug).first()
            user = User.objects.filter(username=username).first()
            if organization is not None and organization.name != organization_name:
                raise CommandError("BOOTSTRAP_IDENTITY_CONFLICT")
            if user is not None:
                if (
                    organization is None
                    or user.organization_id != organization.id
                    or user.role != Role.ADMINISTRATOR
                    or not user.is_staff
                    or not user.is_superuser
                ):
                    raise CommandError("BOOTSTRAP_IDENTITY_CONFLICT")
                self.stdout.write("Bootstrap identity already exists; no changes made.")
                return

            try:
                validate_password(password)
            except ValidationError as error:
                raise CommandError("BOOTSTRAP_PASSWORD_REJECTED") from error

            if organization is None:
                organization = Organization(name=organization_name, slug=organization_slug)
                try:
                    organization.full_clean()
                except ValidationError as error:
                    raise CommandError("BOOTSTRAP_IDENTITY_INVALID") from error
                organization.save()

            User.objects.create_superuser(
                username=username,
                password=password,
                organization=organization,
                role=Role.ADMINISTRATOR,
            )

        self.stdout.write(self.style.SUCCESS("Production administrator created."))
