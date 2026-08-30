import importlib
import uuid
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.db import connection
from django.utils import timezone

from splitbind.access.models import Organization, Recipient, Role, User
from splitbind.documents.models import Document, Issuance
from splitbind.uploads.models import UploadPurpose, UploadRequest


@pytest.mark.django_db
def test_cleanup_timestamp_reverse_guards_fail_closed_before_evidence_loss():
    org = Organization.objects.create(name="Migration Guard", slug=f"guard-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(username="guard-user", password="test", organization=org, role=Role.ISSUER)
    upload = UploadRequest.objects.create(
        organization=org,
        requested_by=actor,
        purpose=UploadPurpose.ISSUANCE,
        object_key=f"uploads/orphan/issuance_input/{org.id}/{uuid.uuid4().hex}.bin",
        expected_sha256="a" * 64,
        size_bytes=1,
        expires_at=timezone.now(),
        orphan_deleted_at=timezone.now(),
    )
    document = Document.objects.create(
        organization=org,
        created_by=actor,
        upload_request=upload,
        source_object_key=f"inputs/issuance/{org.id}/{upload.id}.bin",
        expected_source_sha256="a" * 64,
        page_count=1,
    )
    recipient = Recipient.objects.create(
        organization=org, external_reference="R", display_name="Synthetic",
    )
    issuance = Issuance.objects.create(
        organization=org,
        created_by=actor,
        document=document,
        recipient=recipient,
        output_object_key=f"outputs/issuance/{org.id}/{uuid.uuid4()}.pdf",
        output_sha256="b" * 64,
        output_deleted_at=timezone.now(),
    )
    editor = SimpleNamespace(connection=connection)
    upload_migration = importlib.import_module(
        "splitbind.uploads.migrations.0005_cleanup_timestamps"
    )
    document_migration = importlib.import_module(
        "splitbind.documents.migrations.0004_issuance_output_deletion"
    )

    with pytest.raises(RuntimeError, match="cleanup evidence"):
        upload_migration.refuse_cleanup_evidence_rollback(apps, editor)
    with pytest.raises(RuntimeError, match="output deletion evidence"):
        document_migration.refuse_output_evidence_rollback(apps, editor)

    upload.refresh_from_db()
    issuance.refresh_from_db()
    assert upload.orphan_deleted_at is not None
    assert issuance.output_deleted_at is not None
