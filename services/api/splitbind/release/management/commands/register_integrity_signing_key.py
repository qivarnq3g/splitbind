from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from splitbind.access.models import Organization, SigningKey
from splitbind.release.manifest import load_manifest_signing_key, public_key_pem


class Command(BaseCommand):
    help = "Register the public half of a worker-only integrity signing key."

    def add_arguments(self, parser):
        parser.add_argument("--organization-id", required=True)
        parser.add_argument("--key-id", required=True)
        parser.add_argument("--private-key-file", required=True)
        parser.add_argument("--passphrase-file", required=True)
        parser.add_argument("--valid-from", required=True)

    def handle(self, *args, **options):
        try:
            organization = Organization.objects.get(pk=options["organization_id"])
        except (Organization.DoesNotExist, ValueError) as error:
            raise CommandError("organization does not exist") from error
        valid_from = parse_datetime(options["valid_from"])
        if valid_from is None or valid_from.tzinfo is None:
            raise CommandError("valid-from must be an RFC 3339 timezone-aware timestamp")
        try:
            private_key = load_manifest_signing_key(
                options["private_key_file"],
                options["passphrase_file"],
            )
        except ValueError as error:
            raise CommandError(str(error)) from error
        public_pem = public_key_pem(private_key)

        existing = SigningKey.objects.filter(key_id=options["key_id"]).first()
        if existing is not None:
            if (
                existing.organization_id != organization.id
                or existing.public_key != public_pem
                or existing.algorithm != "Ed25519"
                or existing.valid_from != valid_from
            ):
                raise CommandError(
                    "signing key identifier is already registered with a different public key or policy"
                )
            self.stdout.write("Signing key already registered; no changes made.")
            return

        key = SigningKey(
            organization=organization,
            key_id=options["key_id"],
            algorithm="Ed25519",
            public_key=public_pem,
            valid_from=valid_from,
            metadata={"purpose": "integrity_release_v1"},
        )
        key.full_clean()
        key.save()
        self.stdout.write(self.style.SUCCESS("Integrity signing key registered."))
