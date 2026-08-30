import json
import threading
import uuid
from datetime import timedelta

import pytest
from django.db import close_old_connections, connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.test import override_settings
from django.utils import timezone

from splitbind.access.models import Organization, Recipient, Role, User
from splitbind.audit.models import AuditEvent
from splitbind.documents.models import Document, Issuance, Verification
from splitbind.integrations.storage.base import UploadRejected
from splitbind.integrations.storage.fake import FakeObjectStorage
from splitbind.jobs.models import Job, JobKind, JobStatus
from splitbind.jobs.services import (
    JobConflict,
    WorkflowNotFound,
    create_issuance,
    create_verification,
)
from splitbind.outbox.models import OutboxEvent
from splitbind.uploads.models import PromotionStatus, UploadPurpose, UploadRequest


SHA256 = "a" * 64


def make_user(org, role, name):
    return User.objects.create_user(username=name, password="correct horse battery staple", organization=org, role=role)


@pytest.fixture
def workflow_context(db):
    org = Organization.objects.create(name="Workflow", slug=f"workflow-{uuid.uuid4().hex[:8]}")
    actor = make_user(org, Role.ISSUER, f"issuer-{uuid.uuid4().hex[:8]}")
    verifier = make_user(org, Role.VERIFIER, f"verifier-{uuid.uuid4().hex[:8]}")
    recipient = Recipient.objects.create(organization=org, external_reference="R-1", display_name="Private Recipient")
    storage = FakeObjectStorage()
    return org, actor, verifier, recipient, storage


def completed_upload(org, actor, storage, purpose):
    kind = f"{purpose}_input"
    record = UploadRequest.objects.create(
        organization=org,
        requested_by=actor,
        purpose=purpose,
        object_key=f"uploads/orphan/{kind}/{org.id}/{uuid.uuid4().hex}.bin",
        expected_sha256=SHA256,
        size_bytes=100,
        expires_at=timezone.now() + timedelta(minutes=10),
        finalized_at=timezone.now(),
    )
    storage.inject_object(key=record.object_key, content_type="application/pdf", size_bytes=100, sha256=SHA256)
    return record


@pytest.mark.django_db
def test_issuance_saga_atomically_attaches_domain_job_outbox_and_audit(workflow_context):
    org, issuer, _, recipient, storage = workflow_context
    upload = completed_upload(org, issuer, storage, UploadPurpose.ISSUANCE)
    correlation = uuid.uuid4()
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        issuance, job = create_issuance(issuer, recipient.id, upload.id, correlation)

    upload.refresh_from_db()
    event = OutboxEvent.objects.get(job=job)
    assert upload.promotion_status == PromotionStatus.ATTACHED
    assert upload.promotion_target_key in storage.objects
    assert upload.object_key not in storage.objects
    assert issuance.document.page_count is None
    assert issuance.document.expected_source_sha256 == SHA256
    assert job.status == JobStatus.CREATED and job.issuance_id == issuance.id
    assert event.message_id == uuid.UUID(event.payload["message_id"])
    assert event.attempt == job.attempt == 0
    assert event.topic == event.payload["message_type"] == "issuance.requested"
    assert set(event.payload) == {
        "schema_version", "message_type", "message_id", "job_id", "attempt",
        "issuance_id", "verification_id", "input_object_key", "input_sha256",
        "deadline_at", "correlation_id",
    }
    serialized = json.dumps(event.payload).lower()
    for forbidden in ("recipient", "display_name", "filename", "pdf_bytes", "presigned", "email"):
        assert forbidden not in serialized
    assert AuditEvent.objects.filter(action="issuance.created", target_id=str(issuance.id)).count() == 1


@pytest.mark.django_db
def test_verification_saga_populates_only_verification_target(workflow_context):
    org, _, verifier, _, storage = workflow_context
    upload = completed_upload(org, verifier, storage, UploadPurpose.VERIFICATION)
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        verification, job = create_verification(verifier, upload.id, uuid.uuid4())
    payload = OutboxEvent.objects.get(job=job).payload
    assert job.kind == JobKind.VERIFICATION
    assert payload["issuance_id"] is None
    assert payload["verification_id"] == str(verification.id)


@pytest.mark.django_db
def test_administrator_may_create_both_workflow_kinds(workflow_context):
    org, _, _, recipient, storage = workflow_context
    administrator = make_user(
        org, Role.ADMINISTRATOR, f"administrator-{uuid.uuid4().hex[:8]}",
    )
    issuance_upload = completed_upload(
        org, administrator, storage, UploadPurpose.ISSUANCE,
    )
    verification_upload = completed_upload(
        org, administrator, storage, UploadPurpose.VERIFICATION,
    )

    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        issuance, issuance_job = create_issuance(
            administrator, recipient.id, issuance_upload.id, uuid.uuid4(),
        )
        verification, verification_job = create_verification(
            administrator, verification_upload.id, uuid.uuid4(),
        )

    assert issuance_job.issuance_id == issuance.id
    assert verification_job.verification_id == verification.id


@pytest.mark.django_db
def test_same_organization_other_requester_upload_is_not_discoverable(workflow_context):
    org, issuer, _, recipient, storage = workflow_context
    other_issuer = make_user(org, Role.ISSUER, f"other-{uuid.uuid4().hex[:8]}")
    upload = completed_upload(org, other_issuer, storage, UploadPurpose.ISSUANCE)

    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        with pytest.raises(WorkflowNotFound, match="WORKFLOW_NOT_FOUND"):
            create_issuance(issuer, recipient.id, upload.id, uuid.uuid4())

    upload.refresh_from_db()
    assert upload.promotion_status == PromotionStatus.NONE
    assert upload.promotion_target_key is None


@pytest.mark.django_db
def test_stage_three_failure_rolls_back_records_and_leaves_durable_failed_owner(workflow_context, monkeypatch):
    org, issuer, _, recipient, storage = workflow_context
    upload = completed_upload(org, issuer, storage, UploadPurpose.ISSUANCE)
    original = OutboxEvent.objects.create

    def fail_create(**kwargs):
        raise RuntimeError("private database text")

    monkeypatch.setattr(OutboxEvent.objects, "create", fail_create)
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        with pytest.raises(RuntimeError, match="private database text"):
            create_issuance(issuer, recipient.id, upload.id, uuid.uuid4())
    monkeypatch.setattr(OutboxEvent.objects, "create", original)

    upload.refresh_from_db()
    assert upload.promotion_status == PromotionStatus.FAILED
    assert upload.safe_error_code == "PROMOTION_FINALIZE_FAILED"
    assert upload.promotion_target_key in storage.objects
    assert not Document.objects.filter(upload_request=upload).exists()
    assert not Issuance.objects.exists() and not Job.objects.exists() and not OutboxEvent.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("failure_point", ["document", "job", "outbox_service", "audit"])
def test_every_stage_three_write_failure_rolls_back_the_entire_finalize_transaction(
    workflow_context, monkeypatch, failure_point
):
    org, issuer, _, recipient, storage = workflow_context
    upload = completed_upload(org, issuer, storage, UploadPurpose.ISSUANCE)

    def fail(*args, **kwargs):
        raise RuntimeError(f"injected-{failure_point}")

    if failure_point == "document":
        monkeypatch.setattr(Document.objects, "create", fail)
    elif failure_point == "job":
        monkeypatch.setattr(Job.objects, "create", fail)
    elif failure_point == "outbox_service":
        monkeypatch.setattr("splitbind.jobs.services.create_job_event", fail)
    else:
        monkeypatch.setattr("splitbind.jobs.services.record_event", fail)
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        with pytest.raises(RuntimeError, match=f"injected-{failure_point}"):
            create_issuance(issuer, recipient.id, upload.id, uuid.uuid4())
    upload.refresh_from_db()
    assert upload.promotion_status == PromotionStatus.FAILED
    assert upload.promotion_target_key in storage.objects
    assert not Document.objects.filter(upload_request=upload).exists()
    assert not Issuance.objects.exists() and not Job.objects.exists() and not OutboxEvent.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("problem", ["unfinalized", "expired", "wrong_purpose", "reused"])
def test_reservation_rejects_invalid_own_upload_state(workflow_context, problem):
    org, issuer, _, recipient, storage = workflow_context
    purpose = UploadPurpose.VERIFICATION if problem == "wrong_purpose" else UploadPurpose.ISSUANCE
    upload = completed_upload(org, issuer, storage, purpose)
    if problem == "unfinalized":
        upload.finalized_at = None
        upload.save(update_fields=["finalized_at"])
    elif problem == "expired":
        upload.expires_at = timezone.now() - timedelta(seconds=1)
        UploadRequest._base_manager.filter(pk=upload.pk).update(expires_at=upload.expires_at)
    elif problem == "reused":
        UploadRequest._base_manager.filter(pk=upload.pk).update(
            promotion_status=PromotionStatus.ATTACHED,
            promotion_target_key=f"inputs/issuance/{org.id}/{upload.id}.bin",
        )
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        with pytest.raises((UploadRejected, JobConflict)):
            create_issuance(issuer, recipient.id, upload.id, uuid.uuid4())


@pytest.mark.django_db
def test_copy_failure_marks_reservation_failed_without_domain_records(workflow_context):
    org, issuer, _, recipient, storage = workflow_context
    upload = completed_upload(org, issuer, storage, UploadPurpose.ISSUANCE)
    storage.fail_next("copy_verified", "private provider detail")
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        with pytest.raises(Exception):
            create_issuance(issuer, recipient.id, upload.id, uuid.uuid4())
    upload.refresh_from_db()
    assert upload.promotion_status == PromotionStatus.FAILED
    assert upload.safe_error_code == "PROMOTION_COPY_FAILED"
    assert not Job.objects.exists()


@pytest.mark.django_db
def test_copy_observation_size_mismatch_marks_failed_owner(workflow_context, monkeypatch):
    org, issuer, _, recipient, storage = workflow_context
    upload = completed_upload(org, issuer, storage, UploadPurpose.ISSUANCE)
    original = storage.copy_verified

    def mismatched(**kwargs):
        observed = original(**kwargs)
        return type(observed)(observed.key, observed.size_bytes + 1, observed.content_type, observed.client_sha256_metadata)

    monkeypatch.setattr(storage, "copy_verified", mismatched)
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        with pytest.raises(UploadRejected, match="STORAGE_COPY_MISMATCH"):
            create_issuance(issuer, recipient.id, upload.id, uuid.uuid4())
    upload.refresh_from_db()
    assert upload.promotion_status == PromotionStatus.FAILED
    assert upload.promotion_target_key in storage.objects


@pytest.mark.django_db
def test_orphan_delete_failure_keeps_attached_workflow_and_safe_audit(workflow_context):
    org, issuer, _, recipient, storage = workflow_context
    upload = completed_upload(org, issuer, storage, UploadPurpose.ISSUANCE)
    storage.fail_next("delete", "https://provider.invalid/private?secret=yes")
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        issuance, job = create_issuance(issuer, recipient.id, upload.id, uuid.uuid4())
    assert Issuance.objects.filter(pk=issuance.pk).exists() and Job.objects.filter(pk=job.pk).exists()
    event = AuditEvent.objects.get(action="object.cleanup_deferred_to_lifecycle")
    assert "provider" not in json.dumps(event.metadata).lower()


@pytest.mark.django_db
def test_promotion_identity_rejects_normal_instance_and_queryset_mutation(workflow_context):
    org, issuer, _, _, storage = workflow_context
    upload = completed_upload(org, issuer, storage, UploadPurpose.ISSUANCE)
    target = f"inputs/issuance/{org.id}/{upload.id}.bin"
    upload.save_promotion(status=PromotionStatus.COPYING, target_key=target, safe_error_code=None)
    upload.promotion_target_key = f"inputs/issuance/{org.id}/{uuid.uuid4()}.bin"
    with pytest.raises(ValueError, match="immutable"):
        upload.save()
    with pytest.raises(ValueError, match="immutable"):
        UploadRequest.objects.filter(pk=upload.pk).update(promotion_status=PromotionStatus.ATTACHED)


@pytest.mark.django_db
def test_explicit_promotion_transition_rejects_terminal_rewrite(workflow_context):
    org, issuer, _, _, storage = workflow_context
    upload = completed_upload(org, issuer, storage, UploadPurpose.ISSUANCE)
    target = f"inputs/issuance/{org.id}/{upload.id}.bin"
    upload.save_promotion(status=PromotionStatus.COPYING, target_key=target, safe_error_code=None)
    upload.save_promotion(status=PromotionStatus.ATTACHED, target_key=target, safe_error_code=None)

    with pytest.raises(ValueError, match="promotion transition"):
        upload.save_promotion(
            status=PromotionStatus.FAILED,
            target_key=target,
            safe_error_code="PROMOTION_FINALIZE_FAILED",
        )


@pytest.mark.django_db
def test_failed_promotion_retry_cannot_change_durable_target(workflow_context):
    org, issuer, _, _, storage = workflow_context
    upload = completed_upload(org, issuer, storage, UploadPurpose.ISSUANCE)
    target = f"inputs/issuance/{org.id}/{upload.id}.bin"
    upload.save_promotion(status=PromotionStatus.COPYING, target_key=target, safe_error_code=None)
    upload.save_promotion(
        status=PromotionStatus.FAILED,
        target_key=target,
        safe_error_code="PROMOTION_COPY_FAILED",
    )

    with pytest.raises(ValueError, match="promotion target is immutable"):
        upload.save_promotion(
            status=PromotionStatus.COPYING,
            target_key=f"inputs/issuance/{org.id}/{uuid.uuid4()}.bin",
            safe_error_code=None,
        )


@pytest.mark.django_db
def test_document_page_count_constraint_allows_pending_and_one_to_fifty(workflow_context):
    org, issuer, _, _, storage = workflow_context
    upload = completed_upload(org, issuer, storage, UploadPurpose.ISSUANCE)
    pending = Document.objects.create(
        organization=org, created_by=issuer, upload_request=upload,
        source_object_key=f"inputs/issuance/{org.id}/{upload.id}.bin",
        expected_source_sha256=SHA256, page_count=None,
    )
    assert pending.page_count is None
    pending.page_count = 50
    pending.save(update_fields=["page_count"])
    pending.page_count = 51
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            pending.save(update_fields=["page_count"])


class PromotionConcurrencyContractTests(TransactionTestCase):
    def test_concurrent_reservation_is_postgresql_gate(self):
        if connection.vendor != "postgresql":
            self.skipTest("SQLite has no row-level SELECT FOR UPDATE; PostgreSQL runtime remains the P3/B4 gate")
        org = Organization.objects.create(name="Concurrent", slug=f"concurrent-{uuid.uuid4().hex[:8]}")
        issuer = make_user(org, Role.ISSUER, f"concurrent-{uuid.uuid4().hex[:8]}")
        recipient = Recipient.objects.create(organization=org, external_reference="R", display_name="Private")
        storage = FakeObjectStorage()
        upload = completed_upload(org, issuer, storage, UploadPurpose.ISSUANCE)
        barrier = threading.Barrier(2)
        outcomes = []

        def submit():
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                create_issuance(issuer, recipient.id, upload.id, uuid.uuid4())
                outcomes.append("created")
            except (JobConflict, UploadRejected):
                outcomes.append("rejected")
            finally:
                close_old_connections()

        with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
            threads = [threading.Thread(target=submit) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
        assert all(not thread.is_alive() for thread in threads)
        assert sorted(outcomes) == ["created", "rejected"]
        assert Issuance.objects.count() == Job.objects.count() == OutboxEvent.objects.count() == 1
        assert AuditEvent.objects.filter(action="issuance.created").count() == 1


class B4MigrationContractTests(TransactionTestCase):
    def test_legacy_rows_and_source_hash_survive_forward_migration(self):
        old_targets = [("documents", "0002_verification_verification_status_stable"), ("uploads", "0003_harden_upload_expectations")]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        try:
            executor.migrate(old_targets)
            old_apps = executor.loader.project_state(old_targets).apps
            Org = old_apps.get_model("access", "Organization")
            Actor = old_apps.get_model("access", "User")
            Upload = old_apps.get_model("uploads", "UploadRequest")
            OldDocument = old_apps.get_model("documents", "Document")
            org = Org.objects.create(name="Migration", slug=f"migration-{uuid.uuid4().hex[:8]}")
            actor = Actor.objects.create(
                username=f"migration-{uuid.uuid4().hex[:8]}", password="unusable",
                organization_id=org.id, role=Role.ISSUER, is_active=True,
                is_staff=False, is_superuser=False, date_joined=timezone.now(),
            )
            upload = Upload.objects.create(
                organization_id=org.id, requested_by_id=actor.id,
                purpose=UploadPurpose.ISSUANCE, object_key=f"legacy/{uuid.uuid4()}.bin",
                expected_sha256=SHA256, size_bytes=1, expires_at=timezone.now(),
            )
            document = OldDocument.objects.create(
                organization_id=org.id, created_by_id=actor.id, upload_request_id=upload.id,
                source_object_key=f"legacy/source/{uuid.uuid4()}.bin", source_sha256=SHA256, page_count=1,
            )
            MigrationExecutor(connection).migrate(latest)
            migrated_upload = UploadRequest._base_manager.get(pk=upload.pk)
            migrated_document = Document._base_manager.get(pk=document.pk)
            assert migrated_upload.promotion_status == PromotionStatus.NONE
            assert migrated_upload.promotion_target_key is None
            assert migrated_document.expected_source_sha256 == SHA256
        finally:
            MigrationExecutor(connection).migrate(latest)
