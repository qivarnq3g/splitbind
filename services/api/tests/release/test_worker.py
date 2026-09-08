import io
import uuid
from datetime import timedelta

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from splitbind.access.models import Organization, Role, User
from splitbind.demo.models import DemoVerificationResult, _allow_demo_result_write
from splitbind.documents.models import Verification
from splitbind.integrations.storage.fake import FakeObjectStorage
from splitbind.jobs.models import Job, JobKind, JobStatus
from splitbind.release.mode import ReleaseMode
from splitbind.uploads.models import UploadPurpose, UploadRequest


def _write_signing_secret(tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    passphrase = b"test-only-integrity-worker-passphrase"
    key_path = tmp_path / "worker.pem"
    passphrase_path = tmp_path / "worker.passphrase"
    key_path.write_bytes(
        Ed25519PrivateKey.generate().private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(passphrase),
        )
    )
    passphrase_path.write_bytes(passphrase)
    return key_path, passphrase_path


@pytest.fixture
def queued_verification(db):
    organization = Organization.objects.create(
        name="Integrity worker",
        slug=f"integrity-worker-{uuid.uuid4().hex[:8]}",
    )
    actor = User.objects.create_user(
        username=f"verifier-{uuid.uuid4().hex[:8]}",
        password="correct horse battery staple",
        organization=organization,
        role=Role.VERIFIER,
    )
    upload = UploadRequest.objects.create(
        organization=organization,
        requested_by=actor,
        purpose=UploadPurpose.VERIFICATION,
        object_key=f"uploads/orphan/verification_input/{organization.id}/{uuid.uuid4().hex}.bin",
        expected_sha256="a" * 64,
        size_bytes=1,
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    verification = Verification.objects.create(
        organization=organization,
        upload_request=upload,
        requested_by=actor,
    )

    def make_job(**values):
        defaults = {
            "organization": organization,
            "kind": JobKind.VERIFICATION,
            "status": JobStatus.QUEUED,
            "attempt": 0,
            "verification": verification,
            "deadline_at": timezone.now() + timedelta(minutes=10),
            "correlation_id": uuid.uuid4(),
        }
        defaults.update(values)
        return Job.objects.create(**defaults)

    return make_job


@pytest.mark.parametrize(
    ("supports_skip_locked", "expected"),
    [(True, {"skip_locked": True}), (False, {})],
)
def test_integrity_lock_uses_skip_locked_when_supported(
    monkeypatch, supports_skip_locked, expected
):
    from splitbind.release import worker

    calls = []

    class Query:
        def select_for_update(self, **kwargs):
            calls.append(kwargs)
            return self

    monkeypatch.setattr(
        worker.connection.features,
        "has_select_for_update_skip_locked",
        supports_skip_locked,
    )
    query = Query()

    assert worker._lock_jobs(query) is query
    assert calls == [expected]


@pytest.mark.django_db
@override_settings(
    SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1,
    SPLITBIND_DEMO_MODE=False,
)
def test_claim_binds_exact_owner_and_processes_only_one_job(queued_verification):
    from splitbind.release.worker import claim_next_integrity_job

    first = queued_verification()
    second = queued_verification()
    Job.objects.filter(pk=first.pk).update(
        created_at=timezone.now() - timedelta(minutes=1)
    )
    owner = uuid.uuid4()

    claimed = claim_next_integrity_job(owner, timezone.now())

    first.refresh_from_db()
    second.refresh_from_db()
    evidence = DemoVerificationResult.objects.get(job=first)
    assert claimed is not None and claimed.id == first.id
    assert first.status == JobStatus.PROCESSING
    assert second.status == JobStatus.QUEUED
    assert evidence.owner_token == owner
    assert evidence.attempt == first.attempt == 0


@pytest.mark.django_db
@override_settings(SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1)
def test_claim_cancels_requested_job_before_creating_owner(queued_verification):
    from splitbind.release.worker import claim_next_integrity_job

    now = timezone.now()
    cancelled = queued_verification(cancel_requested_at=now - timedelta(seconds=1))

    assert claim_next_integrity_job(uuid.uuid4(), now) is None

    cancelled.refresh_from_db()
    assert cancelled.status == JobStatus.CANCELLED
    assert not DemoVerificationResult.objects.filter(job=cancelled).exists()


@pytest.mark.django_db
@override_settings(SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1)
def test_claim_fails_expired_job_before_creating_owner(queued_verification):
    from splitbind.release.worker import claim_next_integrity_job

    now = timezone.now()
    expired = queued_verification(deadline_at=now)

    assert claim_next_integrity_job(uuid.uuid4(), now) is None

    expired.refresh_from_db()
    assert expired.status == JobStatus.FAILED
    assert expired.safe_error_code == "INTEGRITY_JOB_DEADLINE_EXCEEDED"
    assert not DemoVerificationResult.objects.filter(job=expired).exists()


@pytest.mark.django_db
@override_settings(SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1)
def test_retry_never_increments_attempt_above_two(queued_verification):
    from splitbind.release.worker import claim_next_integrity_job

    exhausted = queued_verification(
        status=JobStatus.RETRYABLE_FAILED,
        attempt=2,
    )

    assert claim_next_integrity_job(uuid.uuid4(), timezone.now()) is None

    exhausted.refresh_from_db()
    assert exhausted.status == JobStatus.DEAD_LETTERED
    assert exhausted.attempt == 2
    assert exhausted.safe_error_code == "INTEGRITY_JOB_ATTEMPTS_EXHAUSTED"
    assert not DemoVerificationResult.objects.filter(job=exhausted).exists()


@pytest.mark.django_db
@override_settings(SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1)
def test_retry_increments_once_then_claims_with_new_exact_attempt(queued_verification):
    from splitbind.release.worker import claim_next_integrity_job

    retryable = queued_verification(
        status=JobStatus.RETRYABLE_FAILED,
        attempt=1,
        safe_error_code="STORAGE_TEMPORARY",
    )
    owner = uuid.uuid4()

    claimed = claim_next_integrity_job(owner, timezone.now())

    retryable.refresh_from_db()
    evidence = DemoVerificationResult.objects.get(job=retryable)
    assert claimed is not None and claimed.id == retryable.id
    assert retryable.status == JobStatus.PROCESSING
    assert retryable.attempt == 2
    assert retryable.safe_error_code is None
    assert evidence.owner_token == owner
    assert evidence.attempt == 2


@pytest.mark.django_db
@override_settings(SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1)
def test_retry_refuses_to_replace_prior_owner_evidence(queued_verification):
    from splitbind.release.worker import claim_next_integrity_job

    retryable = queued_verification(
        status=JobStatus.RETRYABLE_FAILED,
        attempt=1,
        safe_error_code="STORAGE_TEMPORARY",
    )
    prior_owner = uuid.uuid4()
    with _allow_demo_result_write():
        DemoVerificationResult.objects.create(
            organization_id=retryable.organization_id,
            job=retryable,
            verification_id=retryable.verification_id,
            attempt=retryable.attempt,
            owner_token=prior_owner,
        )

    assert claim_next_integrity_job(uuid.uuid4(), timezone.now()) is None

    retryable.refresh_from_db()
    evidence = DemoVerificationResult.objects.get(job=retryable)
    assert retryable.status == JobStatus.DEAD_LETTERED
    assert retryable.attempt == 1
    assert retryable.safe_error_code == "INTEGRITY_JOB_RESULT_ALREADY_OWNED"
    assert evidence.owner_token == prior_owner
    assert evidence.attempt == 1


@pytest.mark.django_db
@override_settings(
    SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1,
    JOB_TIMEOUT_SECONDS=600,
)
def test_claim_refuses_job_older_than_coded_timeout(queued_verification):
    from splitbind.release.worker import claim_next_integrity_job

    now = timezone.now()
    job = queued_verification(deadline_at=now + timedelta(hours=1))
    Job.objects.filter(pk=job.pk).update(created_at=now - timedelta(seconds=601))

    assert claim_next_integrity_job(uuid.uuid4(), now) is None

    job.refresh_from_db()
    assert job.status == JobStatus.FAILED
    assert job.safe_error_code == "INTEGRITY_JOB_TIMEOUT_EXCEEDED"
    assert not DemoVerificationResult.objects.filter(job=job).exists()


@pytest.mark.django_db
@override_settings(SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1)
def test_cycle_passes_claim_owner_to_existing_processor(
    queued_verification, monkeypatch
):
    from splitbind.release.worker import process_integrity_cycle

    job = queued_verification()
    observed = []

    monkeypatch.setattr(
        "splitbind.release.worker.stage_next_created_job", lambda **kwargs: None
    )

    def process(*, job_id, storage, owner_token):
        evidence = DemoVerificationResult.objects.get(job_id=job_id)
        observed.append((job_id, storage, owner_token, evidence.owner_token))
        Job.objects.filter(pk=job_id).update(status=JobStatus.SUCCEEDED)

    monkeypatch.setattr(
        "splitbind.demo.verification.process_verification_job", process
    )
    storage = FakeObjectStorage()

    outcome = process_integrity_cycle(storage, timezone.now())

    assert outcome is not None and outcome.safe_code == "OK"
    assert observed == [(job.id, storage, observed[0][2], observed[0][2])]


@override_settings(
    SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1,
    JOB_TIMEOUT_SECONDS=600,
)
def test_stale_recovery_uses_the_coded_worker_timeout(monkeypatch):
    from splitbind.release.worker import recover_stale_integrity_jobs

    observed = []
    now = timezone.now()
    storage = FakeObjectStorage()

    monkeypatch.setattr(
        "splitbind.release.worker.reconcile_stale_jobs",
        lambda **kwargs: observed.append(kwargs) or (),
    )

    assert recover_stale_integrity_jobs(storage=storage, now=now) == ()
    assert observed == [
        {
            "storage": storage,
            "now": now,
            "enabled": True,
            "stale_age": timedelta(seconds=600),
        }
    ]


@pytest.mark.django_db
@override_settings(SPLITBIND_RELEASE_MODE=None)
def test_claim_fails_closed_outside_integrity_mode(queued_verification):
    from splitbind.release.worker import claim_next_integrity_job

    job = queued_verification()
    with pytest.raises(ImproperlyConfigured, match="INTEGRITY_RELEASE_MODE_REQUIRED"):
        claim_next_integrity_job(uuid.uuid4(), timezone.now())
    job.refresh_from_db()
    assert job.status == JobStatus.QUEUED


@override_settings(SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1)
def test_command_rejects_non_postgresql_before_storage_access(monkeypatch):
    monkeypatch.setattr("splitbind.release.worker.connection.vendor", "sqlite")
    monkeypatch.setattr(
        "splitbind.uploads.services.get_storage",
        lambda: pytest.fail("storage must not be accessed"),
    )

    with pytest.raises(CommandError, match="^INTEGRITY_DATABASE_INVALID$"):
        call_command("run_integrity_worker", "--once", stdout=io.StringIO())


@override_settings(SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1)
def test_command_rejects_invalid_safety_ceilings_before_database(monkeypatch):
    monkeypatch.setattr("splitbind.release.worker.connection.vendor", "postgresql")

    with override_settings(WORKER_CONCURRENCY=2):
        with pytest.raises(CommandError, match="^INTEGRITY_LIMITS_INVALID$"):
            call_command("run_integrity_worker", "--once", stdout=io.StringIO())


@override_settings(
    SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1,
    SPLITBIND_MANIFEST_SIGNING_KEY_FILE=None,
)
def test_command_rejects_missing_signing_key(monkeypatch):
    monkeypatch.setattr("splitbind.release.worker.connection.vendor", "postgresql")
    monkeypatch.setattr(
        "splitbind.release.worker.connection.ensure_connection", lambda: None
    )

    with pytest.raises(CommandError, match="^INTEGRITY_SIGNING_KEY_INVALID$"):
        call_command("run_integrity_worker", "--once", stdout=io.StringIO())


@override_settings(SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1)
def test_command_rejects_database_connection_failure(monkeypatch, tmp_path):
    key_path, passphrase_path = _write_signing_secret(tmp_path)
    monkeypatch.setattr("splitbind.release.worker.connection.vendor", "postgresql")

    def fail_connection():
        raise RuntimeError("private database endpoint")

    monkeypatch.setattr(
        "splitbind.release.worker.connection.ensure_connection", fail_connection
    )

    with override_settings(
        SPLITBIND_MANIFEST_SIGNING_KEY_FILE=str(key_path),
        SPLITBIND_MANIFEST_SIGNING_KEY_PASSPHRASE_FILE=str(passphrase_path),
    ):
        with pytest.raises(CommandError, match="^INTEGRITY_DATABASE_UNAVAILABLE$"):
            call_command("run_integrity_worker", "--once", stdout=io.StringIO())


@override_settings(SPLITBIND_RELEASE_MODE=None)
def test_command_rejects_non_integrity_mode_before_database(monkeypatch):
    monkeypatch.setattr(
        "splitbind.release.worker.connection.ensure_connection",
        lambda: pytest.fail("database must not be accessed"),
    )

    with pytest.raises(CommandError, match="^INTEGRITY_RELEASE_MODE_REQUIRED$"):
        call_command("run_integrity_worker", "--once", stdout=io.StringIO())


@override_settings(SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1)
def test_command_rejects_storage_initialization_failure(monkeypatch, tmp_path):
    key_path, passphrase_path = _write_signing_secret(tmp_path)
    monkeypatch.setattr("splitbind.release.worker.connection.vendor", "postgresql")
    monkeypatch.setattr(
        "splitbind.release.worker.connection.ensure_connection", lambda: None
    )

    def fail_storage():
        raise RuntimeError("private storage credential")

    monkeypatch.setattr("splitbind.uploads.services.get_storage", fail_storage)

    with override_settings(
        SPLITBIND_MANIFEST_SIGNING_KEY_FILE=str(key_path),
        SPLITBIND_MANIFEST_SIGNING_KEY_PASSPHRASE_FILE=str(passphrase_path),
    ):
        with pytest.raises(CommandError, match="^INTEGRITY_STORAGE_UNAVAILABLE$"):
            call_command("run_integrity_worker", "--once", stdout=io.StringIO())


@override_settings(SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1)
def test_command_rejects_missing_signing_key_passphrase(monkeypatch, tmp_path):
    key_path, _passphrase_path = _write_signing_secret(tmp_path)
    monkeypatch.setattr("splitbind.release.worker.connection.vendor", "postgresql")
    monkeypatch.setattr(
        "splitbind.release.worker.connection.ensure_connection", lambda: None
    )

    with override_settings(
        SPLITBIND_MANIFEST_SIGNING_KEY_FILE=str(key_path),
        SPLITBIND_MANIFEST_SIGNING_KEY_PASSPHRASE_FILE=None,
    ):
        with pytest.raises(CommandError, match="^INTEGRITY_SIGNING_KEY_INVALID$"):
            call_command("run_integrity_worker", "--once", stdout=io.StringIO())


@override_settings(SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1)
def test_once_hides_unexpected_cycle_failure(monkeypatch):
    monkeypatch.setattr(
        "splitbind.release.management.commands.run_integrity_worker.validate_integrity_worker_startup",
        lambda: None,
    )
    monkeypatch.setattr(
        "splitbind.uploads.services.get_storage", lambda: FakeObjectStorage()
    )
    monkeypatch.setattr(
        "splitbind.release.management.commands.run_integrity_worker.recover_stale_integrity_jobs",
        lambda **kwargs: (),
    )

    def fail_cycle(storage, now):
        raise RuntimeError("private provider credential")

    monkeypatch.setattr(
        "splitbind.release.management.commands.run_integrity_worker.process_integrity_cycle",
        fail_cycle,
    )
    stdout = io.StringIO()

    call_command("run_integrity_worker", "--once", stdout=stdout)

    assert stdout.getvalue().strip() == "action=cycle code=INTEGRITY_WORKER_CYCLE_FAILED"
    assert "private" not in stdout.getvalue()


@pytest.mark.parametrize("poll_interval", [0.09, 5.01, float("nan")])
@override_settings(SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1)
def test_command_rejects_invalid_poll_interval_without_startup_access(poll_interval):
    with pytest.raises(CommandError, match="^INTEGRITY_POLL_INTERVAL_INVALID$"):
        call_command(
            "run_integrity_worker",
            "--once",
            "--poll-interval",
            str(poll_interval),
            stdout=io.StringIO(),
        )
