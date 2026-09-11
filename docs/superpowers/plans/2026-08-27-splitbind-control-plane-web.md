# SplitBind Control Plane and Web Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build authenticated, authorization-safe issuance and verification workflows whose Django state, RabbitMQ messages, Rust results, OpenAPI contract, and React evidence presentation remain consistent and auditable.

**Architecture:** Django is the sole browser-facing control plane and owns accounts, permissions, metadata, job state, outbox, result ingestion, audit, retention, and OpenAPI. Direct uploads use short-lived, object-scoped S3-compatible URLs; RabbitMQ carries only schema-validated identifiers and checksums. React uses Django sessions and a generated client, while the Rust worker alone receives private signing and watermark keys.

**Tech Stack:** Python 3.11+, Django 5.2 LTS, Django REST Framework, drf-spectacular, PostgreSQL, boto3, pika, pytest, React 19, TypeScript, Vite, React Router, TanStack Query, openapi-typescript, Vitest, Testing Library, Playwright

**Spec:** `docs/superpowers/specs/2026-08-13-splitbind-production-design.md`

## Global Constraints

- Every business endpoint requires authentication unless explicitly named as login, CSRF bootstrap, liveness, or readiness.
- Roles are `administrator`, `issuer`, `verifier`, and `auditor`; data-query scoping is mandatory in addition to endpoint permissions.
- Browser authentication uses Django sessions. Cookies are `HttpOnly`, `Secure`, and `SameSite=Lax`; mutation requests require CSRF. No JWT is stored in `localStorage`.
- CORS remains same-origin.
- Upload URLs expire after 15 minutes, are scoped to one generated object key, and never grant bucket listing.
- Client-provided extension and MIME are hints only. The worker performs content-based validation after upload finalization.
- Job and outbox creation occur in one PostgreSQL transaction.
- The outbox publisher is at-least-once; worker and result consumer are idempotent by `(job_id, attempt, message_id)`.
- Queue bodies validate against `contracts/jsonschema/job-request-v1.schema.json` or `job-result-v1.schema.json` and never contain PDF bytes, private keys, recipient data, or full presigned URLs.
- Queue `schema_version` is the JSON integer `1`; `v1` is only a filename/exchange suffix.
- Audit events are append-only in application paths and contain actor, action, target, UTC time, correlation ID, and outcome with sensitive fields redacted.
- Django stores public signing-key metadata and signatures. It never reads the private Ed25519, fingerprint, or integrity keys from Azure Key Vault.
- Verification copy uses stable limitation identifiers and never equates an issuance match with proof of who leaked or modified a document.

---

## File Structure Lock-In

```text
services/api/
  pyproject.toml
  manage.py
  config/
  splitbind/
    access/
    audit/
    documents/
    health/
    integrations/
    jobs/
    outbox/
    retention/
    uploads/
  tests/
apps/web/
  package.json
  src/
    api/generated/
    app/
    features/
    pages/
    test/
contracts/
  jsonschema/job-request-v1.schema.json
  jsonschema/job-result-v1.schema.json
  openapi/schema.json
tests/
  integration/
  e2e/
```

## Stable Domain Types

```python
class Role(models.TextChoices):
    ADMINISTRATOR = "administrator"
    ISSUER = "issuer"
    VERIFIER = "verifier"
    AUDITOR = "auditor"

class JobStatus(models.TextChoices):
    CREATED = "created"
    QUEUED = "queued"
    PROCESSING = "processing"
    RETRYABLE_FAILED = "retryable_failed"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"
    CANCELLED = "cancelled"

class VerificationStatus(models.TextChoices):
    VERIFIED_INTACT = "VERIFIED_INTACT"
    SOURCE_IDENTIFIED_MODIFIED = "SOURCE_IDENTIFIED_MODIFIED"
    PARTIAL_EVIDENCE = "PARTIAL_EVIDENCE"
    NO_WATERMARK = "NO_WATERMARK"
    INVALID_MANIFEST = "INVALID_MANIFEST"
    PROCESSING_FAILED = "PROCESSING_FAILED"
```

### Task B1: Scaffold Django, PostgreSQL models, migrations, and health smoke

**Owner:** Leader.

**Files:**

- Create: `services/api/pyproject.toml`
- Create: `services/api/manage.py`
- Create: `services/api/config/{settings,urls,asgi,wsgi}.py`
- Create: `services/api/splitbind/access/models.py`
- Create: `services/api/splitbind/documents/models.py`
- Create: `services/api/splitbind/uploads/models.py`
- Create: `services/api/splitbind/jobs/models.py`
- Create: `services/api/splitbind/outbox/models.py`
- Create: `services/api/splitbind/audit/models.py`
- Create: `services/api/splitbind/health/views.py`
- Generate: `services/api/splitbind/*/migrations/0001_initial.py`
- Test: `services/api/tests/test_models.py`
- Test: `services/api/tests/test_health.py`

**Interfaces:**

- Produces `Organization`, custom `User`, `Recipient`, `UploadRequest`, `Document`, `Issuance`, `Manifest`, `Verification`, `Job`, `JobResultReceipt`, `OutboxEvent`, `AuditEvent`, and `SigningKey` models. API-addressable resources use UUID identifiers; `Manifest` remains an authorization-protected internal record and is exposed only through `public_manifest(internal) -> PublicManifestV1` in Task A6 of `2026-08-27-splitbind-algorithm-worker.md`. `JobResultReceipt` is internal idempotency state and is never API-addressable.
- Stores the internal and public canonical manifest payloads with their separate Ed25519 signature envelopes; only the public pair can be returned outside protected record views.
- Produces `GET /health/live` with process-local semantics.

- [ ] **Step 1: Write failing health and invariant tests**

```python
def test_live_does_not_query_database(client, django_assert_num_queries):
    with django_assert_num_queries(0):
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_issuance_id_is_random_uuid_and_recipient_is_internal(issuance):
    assert issuance.id.version == 4
    assert issuance.recipient_id is not None
    assert "recipient" not in issuance.public_payload()
```

- [ ] **Step 2: Run tests and observe project import failure**

Run: `python -m pytest services/api/tests/test_models.py services/api/tests/test_health.py -v`

Expected: FAIL because the Django project and models do not exist.

- [ ] **Step 3: Add focused models and database constraints**

Use UUID primary keys for public resources; scope users and records to an `Organization`; keep object keys, hashes, signatures, metrics, and evidence as metadata only. Add unique constraints for `(job_id, attempt)`, result-receipt `message_id`, outbox `message_id`, and signing `key_id`. Store SHA-256 as exactly 64 lowercase hex characters and reject invalid values at model/service boundaries.

```python
class Job(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=24, choices=JobKind.choices)
    status = models.CharField(max_length=32, choices=JobStatus.choices, default=JobStatus.CREATED)
    attempt = models.PositiveSmallIntegerField(default=0)
    deadline_at = models.DateTimeField()
    correlation_id = models.UUIDField()
    cancel_requested_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(attempt__lte=2), name="job_attempt_lte_2")]


class JobResultReceipt(models.Model):
    message_id = models.UUIDField(primary_key=True, editable=False)
    job = models.ForeignKey(Job, on_delete=models.PROTECT, related_name="result_receipts")
    received_at = models.DateTimeField(auto_now_add=True)
```

- [ ] **Step 4: Generate and test migrations against PostgreSQL**

Run: `python services/api/manage.py makemigrations --check --dry-run`

Run: `python services/api/manage.py migrate`

Run: `python -m pytest services/api/tests/test_models.py services/api/tests/test_health.py -v`

Expected: no pending migrations and all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api
git commit -m "feat(api): scaffold control-plane domain model"
```

### Task B2: Implement sessions, CSRF, role permissions, query scoping, and audit

**Owner:** Leader; member writes permission-matrix cases.

**Files:**

- Create: `services/api/splitbind/access/{permissions,selectors,views,serializers}.py`
- Create: `services/api/splitbind/audit/{services,redaction}.py`
- Create: `services/api/tests/access/test_sessions.py`
- Create: `services/api/tests/access/test_permissions.py`
- Create: `services/api/tests/audit/test_audit.py`

**Interfaces:**

- `scope_issuances(actor, queryset) -> QuerySet[Issuance]`
- `scope_verifications(actor, queryset) -> QuerySet[Verification]`
- `record_event(actor, action, target, outcome, correlation_id, metadata) -> AuditEvent`
- `GET /api/v1/auth/session`, `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`

- [ ] **Step 1: Write the failing permission matrix**

```python
@pytest.mark.parametrize(
    ("role", "method", "path", "expected"),
    [
        ("issuer", "post", "/api/v1/issuances", 400),
        ("verifier", "post", "/api/v1/issuances", 403),
        ("auditor", "post", "/api/v1/issuances", 403),
        ("auditor", "get", "/api/v1/audit-events", 200),
    ],
)
def test_role_matrix(auth_client, role, method, path, expected):
    response = getattr(auth_client(role), method)(path, {}, format="json")
    assert response.status_code == expected

def test_issuer_gets_404_for_other_organization_record(api_client, issuer, foreign_issuance):
    api_client.force_authenticate(issuer)
    assert api_client.get(f"/api/v1/issuances/{foreign_issuance.id}").status_code == 404
```

- [ ] **Step 2: Run tests and observe missing endpoints/permissions**

Run: `python -m pytest services/api/tests/access services/api/tests/audit -v`

Expected: FAIL with missing routes and selectors.

- [ ] **Step 3: Implement session and data-layer enforcement**

Authenticate through Django `login()`/`logout()`, rotate the session on login, return a CSRF token through the session bootstrap, and require `IsAuthenticated` globally. Every detail view fetches from a role-scoped queryset and therefore returns 404 for foreign objects. Administrator manages accounts through protected Django admin; issuer/verifier/auditor receive only their documented capabilities.

Audit metadata passes an allow-list; reject or replace keys matching password, cookie, session, authorization, private key, PDF content, or full URL.

```python
def scope_issuances(actor: User, queryset: QuerySet[Issuance]) -> QuerySet[Issuance]:
    scoped = queryset.filter(organization_id=actor.organization_id)
    if actor.role in {Role.ADMINISTRATOR, Role.AUDITOR}:
        return scoped
    if actor.role == Role.ISSUER:
        return scoped.filter(created_by_id=actor.id)
    return scoped.none()


SAFE_AUDIT_KEYS = {"kind", "role", "status", "safe_error_code", "object_size", "attempt"}


def record_event(actor, action, target, outcome, correlation_id, metadata) -> AuditEvent:
    safe_metadata = {key: str(value)[:256] for key, value in metadata.items() if key in SAFE_AUDIT_KEYS}
    return AuditEvent.objects.create(
        organization_id=actor.organization_id,
        actor_id=actor.id,
        action=action,
        target_type=target._meta.label_lower,
        target_id=target.pk,
        outcome=outcome,
        correlation_id=correlation_id,
        metadata=safe_metadata,
    )
```

- [ ] **Step 4: Verify cookies, CSRF, RBAC, and immutable audit paths**

Run: `python -m pytest services/api/tests/access services/api/tests/audit -v`

Expected: PASS; browser POST without CSRF is 403; cookies have secure attributes in production settings; no model service exposes an audit update/delete path.

- [ ] **Step 5: Commit**

```bash
git add services/api/splitbind/access services/api/splitbind/audit services/api/tests/access services/api/tests/audit
git commit -m "feat(api): enforce sessions rbac and append-only audit"
```

### Task B3: Implement scoped uploads and the R2-compatible storage provider

**Owner:** Leader; member tests browser validation and expiry display.

**Files:**

- Create: `services/api/splitbind/integrations/storage/{base,fake,s3}.py`
- Create: `services/api/splitbind/uploads/{services,serializers,views}.py`
- Create: `services/api/tests/uploads/test_uploads.py`
- Test: `tests/integration/test_s3_storage.py`

**Interfaces:**

```python
class ObjectStorage(Protocol):
    def presign_put(self, *, key: str, content_type: str, size_bytes: int, expires: timedelta) -> PresignedPut: ...
    def head(self, *, key: str) -> ObjectMetadata | None: ...
    def presign_get(self, *, key: str, expires: timedelta) -> str: ...
    def copy_verified(self, *, source: str, destination: str, sha256: str) -> ObjectMetadata: ...
    def delete(self, *, key: str) -> None: ...
```

- `POST /api/v1/uploads` creates one 15-minute upload intent.
- `POST /api/v1/uploads/{id}/complete` checks the object size/checksum and marks it ready for a job. This is the explicit completion endpoint needed by the presigned-upload workflow in the specification and is included in OpenAPI by B7.

- [ ] **Step 1: Write failing scope, TTL, size, and completion tests**

```python
def test_upload_uses_server_generated_key_and_short_ttl(issuer_client):
    response = issuer_client.post("/api/v1/uploads", {
        "kind": "issuance_input", "filename": "../../report.pdf",
        "content_type": "application/pdf", "size_bytes": 1024,
    }, format="json")
    assert response.status_code == 201
    assert response.json()["object_key"].startswith("uploads/orphan/issuance_input/")
    assert "report.pdf" not in response.json()["object_key"]
    assert parse(response.json()["expires_at"]) <= timezone.now() + timedelta(minutes=15)

def test_upload_above_ten_mib_is_rejected(issuer_client):
    response = issuer_client.post("/api/v1/uploads", {
        "kind": "issuance_input", "filename": "x.pdf",
        "content_type": "application/pdf", "size_bytes": 10 * 1024 * 1024 + 1,
    }, format="json")
    assert response.status_code == 400
```

- [ ] **Step 2: Run tests and observe missing provider/routes**

Run: `python -m pytest services/api/tests/uploads tests/integration/test_s3_storage.py -v`

Expected: FAIL because upload services and provider do not exist.

- [ ] **Step 3: Implement the S3-compatible adapter without trusting MIME**

Generate the object key from organization ID, upload kind, UUID, and a fixed internal suffix. Apply a content-length policy where supported, short TTL, server-side encryption, and no list permission. On completion, compare observed size and client-provided SHA-256 metadata; mark the record ready but leave content/MIME/encryption/page validation to the worker.

```python
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def create_upload(actor: User, *, kind: str, content_type: str, size_bytes: int) -> UploadIntent:
    if size_bytes < 1 or size_bytes > MAX_UPLOAD_BYTES:
        raise UploadRejected("UPLOAD_SIZE")
    object_key = f"uploads/orphan/{kind}/{actor.organization_id}/{uuid.uuid4().hex}.bin"
    expires = timedelta(minutes=15)
    signed = storage.presign_put(key=object_key, content_type=content_type, size_bytes=size_bytes, expires=expires)
    record = UploadRequest.objects.create(
        organization_id=actor.organization_id,
        created_by=actor,
        kind=kind,
        object_key=object_key,
        expected_size=size_bytes,
        expires_at=timezone.now() + expires,
    )
    return UploadIntent(record=record, url=signed.url, required_headers=signed.headers)


def complete_upload(actor: User, upload: UploadRequest, expected_sha256: str) -> UploadRequest:
    metadata = storage.head(key=upload.object_key)
    if metadata is None or metadata.size_bytes != upload.expected_size or metadata.sha256 != expected_sha256:
        raise UploadRejected("UPLOAD_METADATA_MISMATCH")
    upload.mark_ready(expected_sha256)
    upload.save(update_fields=["status", "sha256", "completed_at"])
    return upload
```

- [ ] **Step 4: Run fake-provider and MinIO integration tests**

Run: `python -m pytest services/api/tests/uploads -v`

Run: `python -m pytest tests/integration/test_s3_storage.py -v --storage-endpoint http://localhost:9000`

Expected: PASS; presigned URLs redact in logs and cannot address another object key.

- [ ] **Step 5: Commit**

```bash
git add services/api/splitbind/uploads services/api/splitbind/integrations/storage services/api/tests/uploads tests/integration/test_s3_storage.py
git commit -m "feat(api): add scoped direct-upload workflow"
```

### Task B4: Implement issuance/verification APIs, job cancellation, and transactional outbox

**Owner:** Leader; member reviews API examples.

**Files:**

- Create: `services/api/splitbind/documents/{services,serializers,views}.py`
- Create: `services/api/splitbind/jobs/{services,serializers,views,state.py}`
- Create: `services/api/splitbind/outbox/{messages,services}.py`
- Modify: `services/api/splitbind/uploads/models.py`
- Generate: `services/api/splitbind/uploads/migrations/0002_upload_promotion.py`
- Create: `services/api/tests/jobs/test_creation.py`
- Create: `services/api/tests/jobs/test_state.py`
- Create: `services/api/tests/jobs/test_cancel.py`

**Interfaces:**

- Implements all minimum `/api/v1/uploads`, `/issuances`, `/verifications`, and `/jobs` endpoints from the specification.
- `create_issuance(actor, recipient_id, upload_id, correlation_id) -> (Issuance, Job)`
- `create_verification(actor, upload_id, correlation_id) -> (Verification, Job)`
- `request_cancel(actor, job_id, correlation_id) -> Job`

- [ ] **Step 1: Write failing PostgreSQL-atomicity, compensation, and message-privacy tests**

```python
def test_issuance_job_and_outbox_commit_atomically(issuer, recipient, completed_upload):
    issuance, job = create_issuance(issuer, recipient.id, completed_upload.id, uuid4())
    event = OutboxEvent.objects.get(aggregate_id=job.id)
    assert issuance.job_id == job.id
    assert event.payload["schema_version"] == 1

def test_job_request_contains_no_recipient_or_pdf_bytes(outbox_event):
    serialized = json.dumps(outbox_event.payload)
    assert "recipient" not in serialized
    assert "pdf_bytes" not in serialized
    assert set(outbox_event.payload) == {
        "schema_version", "message_type", "message_id", "job_id", "attempt",
        "issuance_id", "verification_id", "input_object_key", "input_sha256",
        "deadline_at", "correlation_id"
    }


def test_failure_after_object_copy_leaves_a_durable_cleanup_owner(
    issuer, recipient, completed_upload, fake_storage, monkeypatch
):
    def fail_outbox_write(**kwargs):
        raise SimulatedDatabaseFailure()

    monkeypatch.setattr(OutboxEvent.objects, "create", fail_outbox_write)
    with pytest.raises(SimulatedDatabaseFailure):
        create_issuance(issuer, recipient.id, completed_upload.id, uuid4())

    completed_upload.refresh_from_db()
    assert completed_upload.promotion_status == PromotionStatus.FAILED
    assert completed_upload.promotion_target_key in fake_storage.objects
    assert not Issuance.objects.exists()
    assert not OutboxEvent.objects.exists()
```

- [ ] **Step 2: Run tests and observe missing services/states**

Run: `python -m pytest services/api/tests/jobs -v`

Expected: FAIL with missing job services and endpoints.

- [ ] **Step 3: Implement a compensated object-promotion saga, atomic PostgreSQL creation, and a checked state machine**

Object storage and PostgreSQL cannot share one atomic transaction. Use a three-stage compensated saga: first commit the exact destination key and `COPYING` state, then perform and checksum-verify the copy without holding a database lock, then create the domain record, job, outbox message, audit event, and `ATTACHED` transition in one `transaction.atomic()` block. Any failure after the first commit marks the same durable reservation `FAILED`; B6 deletes or retries its exact target, including stale `COPYING` rows after a crash. Only allow job transitions defined in the specification. Cancellation sets `cancel_requested_at`; queued jobs may become cancelled immediately, while processing jobs wait for worker acknowledgement. Use RFC 3339 UTC deadlines and schema validation before saving the outbox payload.

```python
def promoted_input_key(kind: JobKind, organization_id: UUID, upload_id: UUID) -> str:
    prefix = "inputs/issuance" if kind == JobKind.ISSUANCE else "inputs/verification"
    return f"{prefix}/{organization_id}/{upload_id}.bin"


@transaction.atomic
def reserve_promotion(actor: User, upload_id: UUID, kind: JobKind) -> UploadRequest:
    upload = completed_uploads(actor).select_for_update().get(id=upload_id)
    if upload.promotion_status not in {PromotionStatus.NONE, PromotionStatus.FAILED}:
        raise UploadRejected("PROMOTION_ALREADY_RESERVED")
    upload.promotion_target_key = promoted_input_key(kind, actor.organization_id, upload.id)
    upload.promotion_status = PromotionStatus.COPYING
    upload.save(update_fields=["promotion_target_key", "promotion_status"])
    return upload


def create_issuance(actor, recipient_id, upload_id, correlation_id):
    upload = reserve_promotion(actor, upload_id, JobKind.ISSUANCE)
    recipient = Recipient.objects.filter(organization_id=actor.organization_id).get(id=recipient_id)
    promoted_key = upload.promotion_target_key
    try:
        storage.copy_verified(source=upload.object_key, destination=promoted_key, sha256=upload.sha256)
        with transaction.atomic():
            locked_upload = UploadRequest.objects.select_for_update().get(id=upload.id)
            if locked_upload.promotion_status != PromotionStatus.COPYING:
                raise UploadRejected("PROMOTION_STATE")
            issuance = Issuance.objects.create(
                organization_id=actor.organization_id, recipient=recipient, created_by=actor,
            )
            job = Job.objects.create(
                organization_id=actor.organization_id,
                kind=JobKind.ISSUANCE,
                status=JobStatus.CREATED,
                attempt=0,
                deadline_at=timezone.now() + timedelta(seconds=600),
                correlation_id=correlation_id,
            )
            issuance.job = job
            issuance.input_object_key = promoted_key
            issuance.save(update_fields=["job", "input_object_key"])
            payload = build_job_request(job=job, issuance=issuance, upload=upload, input_object_key=promoted_key)
            validate_json(payload, "contracts/jsonschema/job-request-v1.schema.json")
            OutboxEvent.objects.create(message_id=payload["message_id"], aggregate_id=job.id, payload=payload)
            record_event(actor, "issuance.created", issuance, "success", correlation_id, {"status": job.status})
            locked_upload.promotion_status = PromotionStatus.ATTACHED
            locked_upload.save(update_fields=["promotion_status"])
    except Exception:
        UploadRequest.objects.filter(id=upload.id).update(
            promotion_status=PromotionStatus.FAILED,
            safe_error_code="PROMOTION_FAILED",
        )
        raise
    try:
        storage.delete(key=upload.object_key)
    except StorageError as cleanup_error:
        record_event(actor, "object.cleanup_deferred_to_lifecycle", upload, "failure", correlation_id,
                     {"safe_error_code": cleanup_error.safe_code})
    return issuance, job
```

`create_verification` uses `promoted_input_key(JobKind.VERIFICATION, ...)`, omits `issuance_id`, creates a `Verification`, and otherwise writes the same schema-validated job/outbox/audit transaction. Both paths copy and checksum-verify before publishing and leave failed orphan-source deletion under the provider's 24-hour `uploads/orphan/` lifecycle.

`UploadRequest.promotion_target_key` is therefore durable cleanup ownership before object-store mutation. This is intentionally a compensated saga, not a claim of distributed atomicity. B6's retention service retries/deletes `FAILED` or stale `COPYING` targets by that exact key; tests inject failures after copy and during database creation and prove no copied object is unowned and no rolled-back outbox message survives.

- [ ] **Step 4: Run job, transition, rollback, and permission tests**

Run: `python -m pytest services/api/tests/jobs services/api/tests/access -v`

Expected: PASS; injected failure rolls back all four records; invalid transitions raise a stable domain error.

- [ ] **Step 5: Commit**

```bash
git add services/api/splitbind/documents services/api/splitbind/jobs services/api/splitbind/outbox services/api/tests/jobs
git commit -m "feat(api): add workflow jobs and transactional outbox"
```

### Task B5: Connect RabbitMQ publisher, Rust consumer, result events, retries, and dead letters

**Owner:** Leader.

**Files:**

- Create: `services/api/splitbind/integrations/broker/{base,fake,rabbitmq}.py`
- Create: `services/api/splitbind/outbox/publisher.py`
- Create: `services/api/splitbind/jobs/result_consumer.py`
- Create: `services/api/splitbind/management/commands/{publish_outbox,consume_results,run_event_bridge}.py`
- Create: `services/worker/crates/worker/src/{amqp,postgres,s3,file_secret}.rs`
- Test: `services/api/tests/outbox/test_publisher.py`
- Test: `services/api/tests/jobs/test_results.py`
- Test: `tests/integration/test_job_roundtrip.py`

**Interfaces:**

- Publisher uses exchange `splitbind.jobs.v1` and routing keys `issuance.requested` / `verification.requested`.
- Worker publishes to `splitbind.results.v1`; retryable failures use delay/TTL routing; exhausted jobs enter `splitbind.jobs.dead.v1`.
- `consume_result(payload) -> Job` validates schema and applies an idempotent state transition.
- `python manage.py run_event_bridge` is the single production event process: it drains pending outbox rows, consumes one result with a bounded wait, handles it idempotently, and repeats.

- [ ] **Step 1: Write failing at-least-once and idempotency tests**

```python
def test_duplicate_result_event_has_one_effect(job, result_payload):
    consume_result(result_payload)
    consume_result(result_payload)
    job.refresh_from_db()
    assert job.status == JobStatus.SUCCEEDED
    assert JobResultReceipt.objects.filter(message_id=result_payload["message_id"]).count() == 1


def test_message_id_cannot_be_reused_for_another_job(job, other_job, result_payload):
    consume_result(result_payload)
    result_payload["job_id"] = str(other_job.id)
    with pytest.raises(ResultRejected, match="MESSAGE_ID_REUSE"):
        consume_result(result_payload)

def test_retry_exhaustion_dead_letters_without_third_retry(retryable_job):
    retryable_job.attempt = 2
    retryable_job.save(update_fields=["attempt"])
    result = consume_result(retryable_failure(retryable_job))
    assert result.status == JobStatus.DEAD_LETTERED
```

- [ ] **Step 2: Run tests and observe missing publisher/consumer**

Run: `python -m pytest services/api/tests/outbox/test_publisher.py services/api/tests/jobs/test_results.py -v`

Expected: FAIL with missing broker and result consumer.

- [ ] **Step 3: Implement confirms, receipts, and worker adapters**

Publisher selects pending rows with `select_for_update(skip_locked=True)`, sends persistent JSON with publisher confirms, and marks the row published only after confirmation. Result ingestion stores a unique receipt before applying state. Rust validates job schema before downloading input, uses PostgreSQL only for cancellation/manifest lookup, obtains private keys only through its `SecretProvider`, and publishes a schema-valid result for every terminal outcome.

`file_secret.rs` is a worker-only `SecretProvider`. On the host, P10 materializes sources under `/run/splitbind/secrets`; production Compose maps exactly those three sources into the worker container as `/run/secrets/{manifest_signing_key,fingerprint_key,integrity_key}`. `FileSecretProvider` uses `/run/secrets` as its container-local root. Django never imports this provider or mounts those three files. Managed-identity/Key Vault retrieval belongs to P10, outside the API process.

```python
def publish_batch(limit: int = 100) -> int:
    published = 0
    with transaction.atomic():
        events = list(OutboxEvent.objects.select_for_update(skip_locked=True).filter(published_at=None)[:limit])
        for event in events:
            validate_json(event.payload, "contracts/jsonschema/job-request-v1.schema.json")
            broker.publish_persistent(
                exchange="splitbind.jobs.v1",
                routing_key=event.payload["message_type"],
                message_id=str(event.message_id),
                correlation_id=str(event.payload["correlation_id"]),
                body=event.payload,
                confirm=True,
            )
            event.published_at = timezone.now()
            event.save(update_fields=["published_at"])
            published += 1
    return published


@transaction.atomic
def consume_result(payload: dict) -> Job:
    validate_json(payload, "contracts/jsonschema/job-result-v1.schema.json")
    job = Job.objects.select_for_update().get(id=payload["job_id"])
    receipt, created = JobResultReceipt.objects.get_or_create(
        message_id=payload["message_id"], defaults={"job": job}
    )
    if not created:
        if receipt.job_id != job.id:
            raise ResultRejected("MESSAGE_ID_REUSE")
        return job
    apply_result_transition(job, payload)
    job.save()
    return job


def run_event_bridge(stop_requested: Callable[[], bool]) -> None:
    while not stop_requested():
        publish_batch(limit=100)
        broker.consume_one(
            queue="splitbind.results.v1",
            timeout_seconds=1,
            handler=consume_result,
        )
```

```rust
pub struct FileSecretProvider {
    root: PathBuf,
}

impl FileSecretProvider {
    fn read_secret(&self, name: &str) -> Result<Zeroizing<Vec<u8>>, SecretError> {
        let path = self.root.join(name);
        let metadata = std::fs::symlink_metadata(&path)?;
        if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
            return Err(SecretError::UnsafePath);
        }
        Ok(Zeroizing::new(std::fs::read(path)?))
    }
}
```

- [ ] **Step 4: Run RabbitMQ/PostgreSQL integration round trip**

Run: `python -m pytest tests/integration/test_job_roundtrip.py -v --rabbitmq-url amqp://localhost --database-url postgresql://localhost/splitbind_test`

Expected: PASS for success, duplicate delivery, one retry, exhausted retry, cancellation, and dead-letter inspection; queue bodies contain no PDF or PII.

- [ ] **Step 5: Commit**

```bash
git add services/api/splitbind/integrations/broker services/api/splitbind/outbox services/api/splitbind/jobs services/api/splitbind/management services/worker/crates/worker tests/integration/test_job_roundtrip.py
git commit -m "feat(queue): connect outbox worker and idempotent results"
```

### Task B6: Implement public-key registry, manifests, retention, readiness, throttling, and startup ceilings

**Owner:** Leader; member tests expiration views.

**Files:**

- Create: `services/api/splitbind/documents/manifests.py`
- Create: `services/api/splitbind/retention/{policies,services}.py`
- Create: `services/api/splitbind/health/readiness.py`
- Create: `services/api/splitbind/access/throttles.py`
- Create: `services/api/config/limits.py`
- Test: `services/api/tests/documents/test_manifests.py`
- Test: `services/api/tests/retention/test_policies.py`
- Test: `services/api/tests/retention/test_promotion_cleanup.py`
- Test: `services/api/tests/health/test_readiness.py`
- Test: `services/api/tests/test_limits.py`

**Interfaces:**

- `verify_stored_manifest(manifest, signature, public_key) -> ManifestVerification`
- `retention_deadline(kind, completed_at) -> datetime | None`
- `GET /health/ready` checks PostgreSQL, RabbitMQ, storage config, and active public-key metadata.

- [ ] **Step 1: Write failing privacy, retention, readiness, and ceiling tests**

```python
def test_retention_windows_match_spec(now):
    assert retention_deadline("orphan_upload", now) == now + timedelta(hours=24)
    assert retention_deadline("issuance_input", now) == now + timedelta(days=7)
    assert retention_deadline("issuance_output", now) == now + timedelta(days=30)
    assert retention_deadline("verification_input", now) == now + timedelta(hours=24)

def test_production_rejects_unsafe_limit(settings_factory):
    with pytest.raises(ImproperlyConfigured, match="MAX_PDF_BYTES"):
        settings_factory(environment="production", MAX_PDF_BYTES=10 * 1024 * 1024 + 1)

def test_stale_failed_promotion_deletes_the_recorded_target(stale_failed_promotion, fake_storage):
    cleanup_expired(now=timezone.now())
    assert fake_storage.deleted_keys == [stale_failed_promotion.promotion_target_key]
```

- [ ] **Step 2: Run tests and observe missing modules**

Run: `python -m pytest services/api/tests/documents services/api/tests/retention services/api/tests/health services/api/tests/test_limits.py -v`

Expected: FAIL with missing policies/readiness/limits.

- [ ] **Step 3: Implement exact policies without private-key access**

Django verifies worker signatures from stored public keys, supports active/verify-only/revoked metadata, and preserves historical public keys. Retention deletion records audit outcomes and retries transient object-store failures. Throttles combine account, source IP, and job kind. Production settings refuse limits above the specification; readiness never calls Key Vault for private material.

```python
RETENTION_WINDOWS = {
    "orphan_upload": timedelta(hours=24),
    "issuance_input": timedelta(days=7),
    "issuance_output": timedelta(days=30),
    "verification_input": timedelta(hours=24),
}
SAFETY_CEILINGS = {
    "MAX_PDF_BYTES": 10 * 1024 * 1024,
    "MAX_PDF_PAGES": 50,
    "MAX_IMAGE_PIXELS": 40_000_000,
    "JOB_TIMEOUT_SECONDS": 600,
    "WORKER_CONCURRENCY": 1,
}


def validate_production_limits(config: Mapping[str, int]) -> None:
    for name, ceiling in SAFETY_CEILINGS.items():
        if int(config[name]) > ceiling:
            raise ImproperlyConfigured(f"{name} exceeds safety ceiling {ceiling}")


def readiness() -> tuple[dict[str, str], int]:
    checks = {
        "database": database_ready(),
        "broker": broker_ready(),
        "storage_config": storage_configuration_ready(),
        "public_key_registry": SigningKey.objects.filter(status="active").exists(),
    }
    return ({name: "up" if value else "down" for name, value in checks.items()}, 200 if all(checks.values()) else 503)
```

- [ ] **Step 4: Run all backend security and lifecycle tests**

Run: `python -m pytest services/api/tests -v`

Expected: PASS; liveness remains independent; readiness returns 503 when DB, broker, storage configuration, or public-key registry is unavailable.

- [ ] **Step 5: Commit**

```bash
git add services/api/splitbind/documents services/api/splitbind/retention services/api/splitbind/health services/api/splitbind/access/throttles.py services/api/config/limits.py services/api/tests
git commit -m "feat(api): add manifest lifecycle and readiness gates"
```

### Task B7: Generate OpenAPI and a drift-checked TypeScript client

**Owner:** Leader creates contract; member consumes it.

**Files:**

- Create: `services/api/splitbind/openapi.py`
- Create: `services/api/tests/openapi/test_schema.py`
- Generate: `contracts/openapi/schema.json`
- Create: `apps/web/package.json`
- Create: `apps/web/tsconfig.json`
- Create: `apps/web/vite.config.ts`
- Create: `apps/web/scripts/generate-client.mjs`
- Generate: `apps/web/src/api/generated/schema.d.ts`
- Create: `apps/web/src/api/client.ts`
- Modify: `package-lock.json`
- Test: `apps/web/src/api/client.test.ts`

**Interfaces:**

- `python services/api/manage.py spectacular --file contracts/openapi/schema.json --validate`
- `npm run generate:api --workspace @splitbind/web`
- Frontend uses a same-origin fetch client with `credentials: "same-origin"` and CSRF headers on mutations.

- [ ] **Step 1: Write failing endpoint/schema and client tests**

```python
def test_minimum_contract_paths(schema):
    assert {
        "/api/v1/uploads", "/api/v1/issuances", "/api/v1/verifications",
        "/api/v1/uploads/{id}/complete",
        "/api/v1/jobs/{id}", "/api/v1/jobs/{id}/cancel",
        "/health/live", "/health/ready",
    } <= set(schema["paths"])
```

```ts
it("sends csrf and same-origin credentials on mutations", async () => {
  await api.POST("/api/v1/jobs/{id}/cancel", { params: { path: { id: JOB_ID } } });
  expect(fetch).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ credentials: "same-origin" }));
});
```

- [ ] **Step 2: Run tests and observe missing schema/client**

Run: `python -m pytest services/api/tests/openapi -v`

Run: `npm test --workspace @splitbind/web -- client.test.ts`

Expected: FAIL with missing schema/client files.

- [ ] **Step 3: Generate schema and typed client**

Annotate every response and error code with drf-spectacular. Generate types with `openapi-typescript`; wrap `openapi-fetch` to attach CSRF only to unsafe methods and never log full presigned URLs.

```ts
// apps/web/src/api/client.ts
import createClient from "openapi-fetch";
import type { paths } from "./generated/schema";

function csrfToken(): string {
  return document.cookie.split("; ").find((part) => part.startsWith("csrftoken="))?.split("=")[1] ?? "";
}

export const api = createClient<paths>({ baseUrl: "", credentials: "same-origin" });
api.use({
  async onRequest({ request }) {
    if (!["GET", "HEAD", "OPTIONS", "TRACE"].includes(request.method.toUpperCase())) {
      request.headers.set("X-CSRFToken", csrfToken());
    }
    return request;
  },
});
```

`apps/web/package.json` names the workspace `@splitbind/web`, declares runtime dependencies `openapi-fetch`, React, React DOM, React Router, and TanStack Query, and declares development dependencies `openapi-typescript`, TypeScript, Vite, Vitest, Testing Library, and Playwright. It defines `generate:api` as `openapi-typescript ../../contracts/openapi/schema.json -o src/api/generated/schema.d.ts`, `test` as `vitest run`, `typecheck` as `tsc --noEmit`, and `e2e` as `playwright test`. Run `npm install --package-lock-only --ignore-scripts` at the repository root after adding dependencies.

- [ ] **Step 4: Prove regeneration has no drift**

Run: `python services/api/manage.py spectacular --file contracts/openapi/schema.json --validate`

Run: `npm run generate:api --workspace @splitbind/web`

Run: `git diff --exit-code contracts/openapi/schema.json apps/web/src/api/generated`

Expected: PASS with no uncommitted generated changes.

- [ ] **Step 5: Commit**

```bash
git add services/api/splitbind/openapi.py services/api/tests/openapi contracts/openapi apps/web/package.json apps/web/tsconfig.json apps/web/vite.config.ts apps/web/scripts apps/web/src/api package-lock.json
git commit -m "feat(contract): publish openapi and typed web client"
```

### Task B8: Build the React session, issuance, upload, and job-progress workflow

**Owner:** Member; leader reviews security and contract usage.

**Files:**

- Create: `apps/web/src/app/{router,queryClient}.tsx`
- Create: `apps/web/src/features/auth/`
- Create: `apps/web/src/features/uploads/`
- Create: `apps/web/src/features/issuances/`
- Create: `apps/web/src/features/jobs/`
- Create: `apps/web/src/pages/{Login,IssueDocument,JobDetail,IssuanceDetail}Page.tsx`
- Test: `apps/web/src/test/issuance-flow.test.tsx`
- Test: `tests/e2e/issuance.spec.ts`

**Interfaces:**

- Browser flow: session bootstrap → upload intent → direct upload → upload completion → issuance creation → job polling → signed result/download.
- Client rejects files above 10 MiB as early feedback but server/worker remains authoritative.

- [ ] **Step 1: Write a failing issuance journey test**

```ts
it("uploads then creates and follows an issuance job", async () => {
  render(<IssueDocumentPage />);
  await user.upload(screen.getByLabelText("Tệp PDF"), pdfFixture);
  await user.selectOptions(screen.getByLabelText("Người nhận"), RECIPIENT_ID);
  await user.click(screen.getByRole("button", { name: "Tạo bản cấp phát" }));
  expect(await screen.findByText("Đang xử lý")).toBeVisible();
  expect(server.requests.map((request) => request.path)).toEqual([
    "/api/v1/uploads", "/direct-upload", "/api/v1/uploads/UPLOAD/complete",
    "/api/v1/issuances", "/api/v1/jobs/JOB"
  ]);
});
```

- [ ] **Step 2: Run test and observe missing pages/features**

Run: `npm test --workspace @splitbind/web -- issuance-flow.test.tsx`

Expected: FAIL because issuance components do not exist.

- [ ] **Step 3: Implement accessible forms and bounded polling**

Use semantic labels, keyboard operation, explicit size/page warnings, upload progress, safe server errors, and polling with exponential backoff capped at five seconds. Stop polling on every terminal state and when the component unmounts. Never place a presigned URL in analytics or console logs.

```tsx
const TERMINAL = new Set(["succeeded", "failed", "dead_lettered", "cancelled"]);

export function useJob(jobId: string | null) {
  return useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.GET("/api/v1/jobs/{id}", { params: { path: { id: jobId! } } }),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.data?.status;
      if (status !== undefined && TERMINAL.has(status)) return false;
      const failures = query.state.fetchFailureCount;
      return Math.min(1000 * 2 ** failures, 5000);
    },
  });
}

async function submitIssuance(file: File, recipientId: string) {
  if (file.size > 10 * 1024 * 1024) throw new Error("FILE_TOO_LARGE");
  const upload = await createUploadIntent(file);
  await putWithoutLoggingUrl(upload.url, file, upload.required_headers);
  await completeUpload(upload.id, await sha256(file));
  return createIssuance({ upload_id: upload.id, recipient_id: recipientId });
}
```

- [ ] **Step 4: Run unit and browser journey tests**

Run: `npm test --workspace @splitbind/web -- issuance-flow.test.tsx`

Run: `npm run e2e --workspace @splitbind/web -- --grep "issuance"`

Expected: PASS; download is offered only to an authorized issuer and uses a short-lived URL.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src tests/e2e/issuance.spec.ts
git commit -m "feat(web): add issuance workflow and job progress"
```

### Task B9: Build verification evidence UI and complete end-to-end authorization tests

**Owner:** Member; leader approves all evidence language.

**Files:**

- Create: `apps/web/src/features/verifications/`
- Create: `apps/web/src/features/evidence/{copy,EvidenceSummary,IntegrityMap}.tsx`
- Create: `apps/web/src/pages/{VerifyDocument,VerificationDetail}Page.tsx`
- Test: `apps/web/src/test/verification-flow.test.tsx`
- Test: `apps/web/src/test/evidence-copy.test.tsx`
- Test: `tests/e2e/verification.spec.ts`
- Test: `tests/e2e/authorization.spec.ts`

**Interfaces:**

- Renders all six verification statuses and stable limitation copy.
- Suspicious rectangles use normalized coordinates and are displayed only when evidence supplies sufficient page geometry.

- [ ] **Step 1: Write failing status-language tests**

```ts
it.each([
  ["NO_WATERMARK", "không có nghĩa tài liệu chắc chắn không thuộc hệ thống"],
  ["PARTIAL_EVIDENCE", "chưa đủ ngưỡng để gán nguồn phát hành"],
  ["SOURCE_IDENTIFIED_MODIFIED", "không chứng minh người nhận đã sửa hoặc phát tán"],
])("renders the mandatory limitation for %s", async (status, limitation) => {
  renderVerification(status);
  expect(await screen.findByText(new RegExp(limitation, "i"))).toBeVisible();
});
```

- [ ] **Step 2: Run tests and observe missing evidence components**

Run: `npm test --workspace @splitbind/web -- verification-flow.test.tsx evidence-copy.test.tsx`

Expected: FAIL with missing pages and copy mappings.

- [ ] **Step 3: Implement fact/confidence/limitation/inference separation**

Display four distinct sections. Facts include detected ID, signature/hash states, pages analyzed, and region counts; confidence shows numeric score and threshold; limitations use approved copy IDs; inference uses cautious status wording. Never display `recipient_id` to an unauthorized verifier. Render tamper maps with a legend and a visible “technical signal, not legal conclusion” notice.

```tsx
export const LIMITATION_COPY: Record<string, string> = {
  no_watermark_not_exclusion: "Không phát hiện watermark không có nghĩa tài liệu chắc chắn không thuộc hệ thống.",
  partial_not_attribution: "Bằng chứng hiện có chưa đủ ngưỡng để gán nguồn phát hành.",
  match_not_actor_proof: "Khớp bản cấp phát không chứng minh người nhận đã sửa, làm rò rỉ hoặc phát tán tài liệu.",
  technical_not_legal: "Đây là tín hiệu kỹ thuật, không phải kết luận pháp lý.",
};

export function EvidenceSummary({ evidence, permissions }: Props) {
  return <article>
    <section aria-labelledby="facts"><h2 id="facts">Sự kiện quan sát được</h2><Facts evidence={evidence} showRecipient={permissions.canViewRecipient} /></section>
    <section aria-labelledby="confidence"><h2 id="confidence">Độ tin cậy</h2><Confidence value={evidence.fingerprint_confidence} /></section>
    <section aria-labelledby="limitations"><h2 id="limitations">Giới hạn</h2><LimitationList ids={evidence.limitations} copy={LIMITATION_COPY} /></section>
    <section aria-labelledby="inference"><h2 id="inference">Suy luận thận trọng</h2><Inference status={evidence.status} /></section>
  </article>;
}
```

- [ ] **Step 4: Run UI and E2E authorization suites**

Run: `npm test --workspace @splitbind/web`

Run: `npm run e2e --workspace @splitbind/web -- --grep "verification|authorization"`

Expected: PASS for all statuses, keyboard access, foreign-record denial, cancelled/failed jobs, and evidence copy.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src tests/e2e/verification.spec.ts tests/e2e/authorization.spec.ts
git commit -m "feat(web): add verification evidence workflow"
```

## Track Verification Matrix

- `python services/api/manage.py makemigrations --check --dry-run`
- `python -m pytest services/api/tests -v`
- `python -m pytest tests/integration -v`
- `python services/api/manage.py spectacular --file contracts/openapi/schema.json --validate`
- `npm run generate:api --workspace @splitbind/web`
- `git diff --exit-code contracts/openapi/schema.json apps/web/src/api/generated`
- `npm run lint --workspace @splitbind/web`
- `npm run typecheck --workspace @splitbind/web`
- `npm test --workspace @splitbind/web`
- `npm run e2e --workspace @splitbind/web`
- `git diff --check`

## Track Exit Evidence

- Permission matrix for all four roles at both API and query scope.
- Atomic job/outbox test and duplicate result-delivery test.
- R2-compatible direct upload with TTL/object scope and log redaction.
- RabbitMQ success, retry, dead-letter, cancel, and duplicate-delivery integration evidence.
- Public-key verification and retention-policy tests.
- Generated OpenAPI client with zero drift.
- Issuance and verification browser journeys for every terminal status.
- Mandatory evidentiary limitation text visible and tested.
