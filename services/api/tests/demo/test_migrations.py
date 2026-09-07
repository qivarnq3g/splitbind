import hashlib
import uuid
from datetime import timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from splitbind.access.models import Organization, Recipient, Role, User
from splitbind.demo.models import (
    DemoIssuanceResult,
    DemoOutputState,
    _allow_demo_result_write,
)
from splitbind.documents.models import Document, Issuance
from splitbind.jobs.models import Job, JobKind, JobStatus
from splitbind.uploads.models import PromotionStatus, UploadPurpose, UploadRequest

from .fixtures import synthetic_pdf_bytes


def _create_issuance_evidence():
    source = synthetic_pdf_bytes(width=144, height=192)
    source_sha256 = hashlib.sha256(source).hexdigest()
    organization = Organization.objects.create(
        name="Demo migration",
        slug=f"demo-migration-{uuid.uuid4().hex[:8]}",
    )
    actor = User.objects.create_user(
        username=f"migration-{uuid.uuid4().hex[:8]}",
        password="correct horse battery staple",
        organization=organization,
        role=Role.ISSUER,
    )
    recipient = Recipient.objects.create(
        organization=organization,
        external_reference=f"synthetic-{uuid.uuid4().hex[:8]}",
        display_name="Synthetic recipient",
    )
    upload_id = uuid.uuid4()
    input_key = f"inputs/issuance/{organization.id}/{upload_id}.bin"
    upload = UploadRequest.objects.create(
        id=upload_id,
        organization=organization,
        requested_by=actor,
        purpose=UploadPurpose.ISSUANCE,
        object_key=(
            f"uploads/orphan/issuance_input/{organization.id}/{uuid.uuid4().hex}.bin"
        ),
        expected_sha256=source_sha256,
        size_bytes=len(source),
        expires_at=timezone.now() + timedelta(minutes=15),
        finalized_at=timezone.now(),
        promotion_target_key=input_key,
        promotion_status=PromotionStatus.ATTACHED,
    )
    document = Document.objects.create(
        organization=organization,
        created_by=actor,
        upload_request=upload,
        source_object_key=input_key,
        expected_source_sha256=source_sha256,
    )
    issuance = Issuance.objects.create(
        organization=organization,
        document=document,
        recipient=recipient,
        created_by=actor,
    )
    job = Job.objects.create(
        organization=organization,
        kind=JobKind.ISSUANCE,
        status=JobStatus.PROCESSING,
        attempt=0,
        issuance=issuance,
        deadline_at=timezone.now() + timedelta(minutes=10),
        correlation_id=uuid.uuid4(),
    )
    evidence = DemoIssuanceResult(
        organization=organization,
        job=job,
        issuance=issuance,
        attempt=job.attempt,
        owner_token=uuid.uuid4(),
        output_object_key=f"outputs/issuance/{organization.id}/{issuance.id}.pdf",
        output_state=DemoOutputState.RESERVED,
    )
    with _allow_demo_result_write():
        evidence.save()
    return evidence


@pytest.mark.django_db(transaction=True)
def test_initial_demo_migration_reverses_when_issuance_evidence_is_empty():
    latest_targets = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        MigrationExecutor(connection).migrate([("demo", "0001_initial")])
        MigrationExecutor(connection).migrate([("demo", None)])

        assert "demo_demoissuanceresult" not in connection.introspection.table_names()
    finally:
        MigrationExecutor(connection).migrate(latest_targets)


@pytest.mark.django_db(transaction=True)
def test_initial_demo_migration_refuses_evidence_bearing_reverse_before_drop():
    evidence = _create_issuance_evidence()
    latest_targets = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        MigrationExecutor(connection).migrate([("demo", "0001_initial")])

        with pytest.raises(
            RuntimeError,
            match="preserve or export issuance result evidence",
        ):
            MigrationExecutor(connection).migrate([("demo", None)])

        assert DemoIssuanceResult.objects.filter(pk=evidence.pk).exists()
    finally:
        MigrationExecutor(connection).migrate(latest_targets)
