# SplitBind MVP Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver and evaluate the complete SplitBind academic-production MVP, publish it at `https://splitbind.qivarn.id.vn`, retain an offline demonstration path, and prepare reproducible evidence for the 17/09/2026 presentation.

**Architecture:** Work contract-first across three coordinated tracks. The algorithm/worker track proves and versions the watermark design before Rust becomes the production data plane; the control-plane/web track implements authenticated issuance and verification around versioned queue contracts; the platform/release track supplies reproducible containers, CI, recovery drills, Azure deployment, and DNS/TLS cutover. Each track has its own detailed plan and may proceed in parallel after the shared contracts land.

**Tech Stack:** npm workspaces, React 19, TypeScript, Vite, Python 3.11+, Django 5.2 LTS, Django REST Framework, PostgreSQL, RabbitMQ, Rust stable, OpenCV, Cloudflare R2, Azure Key Vault, Caddy, Docker Compose, GitHub Actions

**Spec:** `docs/superpowers/specs/2026-08-13-splitbind-production-design.md`

**Detailed Plans:**

- `docs/superpowers/plans/2026-08-27-splitbind-algorithm-worker.md`
- `docs/superpowers/plans/2026-08-27-splitbind-control-plane-web.md`
- `docs/superpowers/plans/2026-08-27-splitbind-platform-release.md`

## Global Constraints

- The public hostname is `splitbind.qivarn.id.vn`; the apex `qivarn.id.vn` remains on its current service.
- The public DNS record is not changed until a release candidate passes local end-to-end, backup, rollback, and Azure preflight gates.
- Never hardcode the current Azure public IP or administrator IPv4 in source, committed configuration, tests, or documentation.
- The existing Azure VM must remain deallocated when a public environment is unnecessary; the static Standard public IPv4 can still consume Azure credit while the VM is deallocated.
- Create and verify the Azure budget guardrail before starting the VM for deployment or changing DNS.
- Keep the Azure for Students spending limit; do not upgrade to Pay-as-you-go.
- Only TCP `80/443` may be public. TCP `22` must be restricted to the administrator's current IPv4 `/32` and use SSH keys. PostgreSQL, RabbitMQ, Docker, and metrics endpoints remain private.
- The production worker is Rust with concurrency `1`; Python is reference, attack simulation, vector generation, and benchmark code only.
- Queue messages contain versioned IDs, object keys, checksums, deadlines, correlation IDs, and minimal metadata; they never contain PDF bytes, private keys, full presigned URLs, or recipient personal data.
- Queue `schema_version` is the JSON integer `1`; the text `v1` appears only in schema filenames, exchange names, and routing infrastructure.
- The only recipient-linked value in a public watermark payload is a pseudonymous 128-bit `issuance_id`; framing may also carry a magic marker, algorithm version, CRC, and error-correction symbols. Recipient mapping remains authorization-protected and audited.
- The signing and watermark key families are separate. Only the Rust worker receives their private production material; Django stores public-key metadata and never reads the private signing or watermark keys.
- Production rejects files or decoded resources above 10 MiB, 50 PDF pages, or 40 megapixels, rejects encrypted or unsafe PDFs, and refuses startup when configured limits exceed coded safety ceilings.
- Worker job timeout is 600 seconds, retry count is at most `2`, temporary storage is at most 2 GiB, and measured peak RSS is at most 1.5 GiB.
- Every success, failure, retry, timeout, cancellation, and orphan-recovery path has an observed cleanup test.
- Verification UI and reports separate facts, confidence, limitations, and inference. A match never proves that the recipient leaked, edited, or distributed a document.
- Do not begin Tardos collusion resistance or advanced localization until both MVP workflows satisfy their release gates.
- Use npm workspaces because npm is installed in the verified Windows toolchain; do not add an undeclared pnpm or uv dependency.
- Use only synthetic, redistributable fixtures without personal data. Real course PDFs and private evidence stay outside Git.

---

## Verified Starting Point

- Repository phase: design specification only; no runnable application or dependency manifests exist.
- Git worktree: contains pre-existing documentation changes and local-only artifacts; implementation must begin in an isolated feature worktree and must not absorb unrelated files.
- Toolchain observed on the primary machine: Node.js, npm, Python 3.11, Rust/Cargo, Docker Compose, Azure CLI, GitHub CLI.
- Production compute: `vm-splitbind-prod` exists in Korea Central as `Standard_B2ls_v2` and was observed deallocated; resource state must be freshly audited before every deployment.
- DNS: `qivarn.id.vn` currently serves another system; `splitbind.qivarn.id.vn` is reserved for SplitBind and has not been cut over.
- Cost gap: the planned Azure budget was not present during the 27/08/2026 read-only audit and is a hard deployment blocker.

## Shared Repository Layout

```text
apps/
  web/                         React/Vite browser application
services/
  api/                         Django control plane and background publishers
  worker/                      Rust workspace: core, worker, and adapters
research/
  python/                      Reference algorithm, simulator, and benchmark
contracts/
  algorithm/                   Candidate and released algorithm profiles
  jsonschema/                  Job, result-event, manifest, and vector schemas
  openapi/                     Generated API schema
fixtures/
  corpus/                      Small synthetic acceptance corpus
  vectors/                     Versioned Python/Rust shared vectors
tests/
  integration/                 PostgreSQL/RabbitMQ/R2-compatible integration tests
  e2e/                         Issuance and verification browser/system tests
  security/                    Authorization, malicious-input, and container tests
infra/
  caddy/                       Same-origin edge configuration
  compose/                     Local, CI, production, and offline profiles
  docker/                      Focused multi-stage images
  scripts/                     PowerShell and POSIX operator scripts
docs/
  decisions/                   Architecture decisions
  evaluation/                  Reproducible result summaries
  runbooks/                    Operations and recovery procedures
  superpowers/plans/           Master and track plans
presentation/                  Slide sources, demo script, and approved figures
```

## Cross-Track Contracts

The first implementation task publishes these interfaces. No downstream track invents alternate field names.

```text
JobRequestV1
  schema_version: 1
  message_type: issuance.requested | verification.requested
  message_id: UUID
  job_id: UUID
  attempt: integer 0..2
  issuance_id: UUID | null
  verification_id: UUID | null
  input_object_key: string
  input_sha256: lowercase hex string
  deadline_at: RFC 3339 UTC timestamp
  correlation_id: UUID

JobResultV1
  schema_version: 1
  message_type: job.succeeded | job.retryable_failed | job.failed | job.cancelled
  message_id: UUID
  job_id: UUID
  attempt: integer 0..2
  output_object_key: string | null
  output_sha256: lowercase hex string | null
  recovered_issuance_id: UUID | null
  verification_status: VERIFIED_INTACT | SOURCE_IDENTIFIED_MODIFIED |
                       PARTIAL_EVIDENCE | NO_WATERMARK |
                       INVALID_MANIFEST | PROCESSING_FAILED | null
  evidence: EvidenceV1 | null
  metrics: JobMetricsV1
  safe_error_code: string | null
  correlation_id: UUID

EvidenceV1
  fingerprint_confidence: number 0..1
  valid_vote_count: non-negative integer
  analyzed_page_count: non-negative integer
  manifest_signature_valid: boolean | null
  exact_file_hash_match: boolean | null
  integrity_score: number 0..1 | null
  suspicious_regions: array of normalized rectangles
  limitations: non-empty array of stable copy identifiers

JobMetricsV1
  processing_ms: non-negative integer
  pages_processed: non-negative integer
  peak_rss_bytes: non-negative integer
  temp_peak_bytes: non-negative integer
  cleanup_failures: non-negative integer
```

## Milestones and Ownership

| Milestone | Target | Leader / code chính | Thành viên / code phụ + slide | Exit evidence |
| --- | --- | --- | --- | --- |
| M0 — Baseline | 28/08 | Worktree, monorepo, contracts, CI smoke | Synthetic fixtures, UI wireframe, slide outline | All runtimes have a failing-then-passing smoke test; schemas validate |
| M1 — Research baseline | 02/09 | Payload, fingerprint reference, candidate profiles | Attack simulator, corpus, benchmark reports | A candidate profile is promoted only if measured release gates pass |
| M2 — Rust local worker | 06/09 | Rust parity, PDF pipeline, signing, cleanup | Cross-language vectors and fault tests | Local issue and verify jobs pass vectors and cleanup paths |
| M3 — Control-plane vertical slice | 10/09 | Django, RBAC, outbox, broker/results, storage adapters | React workflows, API/UI tests | Both workflows run through local Compose using synthetic fixtures |
| M4 — Release candidate | 13/09 | Security hardening, observability, E2E, multi-arch | Full attack matrix, charts, manual QA | CI green; no unaccepted critical/high issue; offline demo passes |
| M5 — Public deployment | 15/09 | Azure audit, backup, deploy, DNS/TLS, rollback evidence | Public smoke test and demo capture | `https://splitbind.qivarn.id.vn` passes HTTPS and readiness checks |
| M6 — Presentation | 16/09 | Technical review and Q&A | Final slides, demo script, backup video | Two rehearsals pass; release and evidence bundle frozen |

## Critical Path and Parallel Work

```text
Shared contracts
    ├── Python reference → benchmark → released profile → Rust parity → worker
    ├── Django models/RBAC → uploads/jobs/outbox → broker/result consumer
    └── Compose/CI foundation ──────────────────────────────────────────┐
                                                                      ↓
Rust worker + Django control plane + React UI → local E2E → release gate
    → backup/rollback/offline drill → Azure deploy → DNS/TLS → presentation
```

- The member can build the attack harness and React UI in parallel after shared schemas exist.
- The leader owns contract changes, algorithms, Rust, integration boundaries, security gates, and production deployment.
- Every pull request has exactly one owner and one reviewer; the author cannot self-approve a release-gate change.

## Hard Gates

### Gate G0 — Contract freeze

- JSON Schemas validate all examples.
- Manifest canonicalization and queue field names are fixed.
- Synthetic fixture licenses and checksums are recorded.

### Gate G1 — Algorithm promotion

- No false attribution on the versioned acceptance corpus.
- Decode rate is at least 95% for JPEG quality 70 and resize 0.75x.
- Decode rate is at least 90% for crop 25% when enough tiles remain.
- Mean PSNR is at least 38 dB and mean SSIM is at least 0.95.
- A failing candidate remains in research results; the corpus is not edited to hide failure.

### Gate G2 — Local vertical slice

- Issuance produces an image-based PDF, a SHA-256 digest, a canonical manifest, and an Ed25519 signature.
- Verification produces one of the six specified statuses with evidence and limitation identifiers.
- Permission tests prove users cannot read out-of-scope records.
- Cleanup tests pass for success, permanent failure, retryable failure, timeout, cancellation, and restart sweeper.

### Gate G3 — Release candidate

- CI passes format, lint, type checking, unit, integration, contract, E2E, security, license, secret, SBOM, and multi-architecture build checks.
- Peak RSS is at most 1.5 GiB and temporary disk peak is at most 2 GiB at input limits.
- Production containers are non-root, read-only, and their combined memory limit is at most 3 GiB.
- Backup/restore, rollback, and offline-demo drills have observed postconditions.
- No critical/high vulnerability remains without a written, scoped risk decision.

### Gate G4 — Public cutover

- Azure budget and alert thresholds 25/50/75/90 are observed.
- Fresh Azure audit verifies VM, identity, disk, effective network rules, SSH restriction, and available disk.
- The release candidate is healthy before DNS mutation.
- The previous DNS value and previous image digests are captured for rollback.
- Caddy obtains a certificate valid for `splitbind.qivarn.id.vn`; HTTPS live/ready and same-origin API smoke tests pass.

## Master Execution Checklist

Platform task map: P1 freezes toolchains and smoke CI; P2 defines local/offline/production topology; P3 hardens images and resource limits; P4 adds metrics and capacity gates; P5 expands full CI, security, SBOM, and multi-architecture builds; P6 proves backup/restore; P7 proves digest release, rollback, and offline demo; P8 validates Neon, R2, and Key Vault policy; P9 audits the already-provisioned Azure resources and budget gate; P10 bootstraps the host and performs authorized deploy/DNS/TLS cutover.

- [ ] **Task 1:** Execute Tasks A1–A2 in the algorithm/worker plan to publish fixtures, schemas, and candidate profiles.
- [ ] **Task 2:** Execute Tasks P1–P2 in the platform/release plan to scaffold the monorepo and CI smoke gates.
- [ ] **Task 3:** Execute Tasks A3–A6 to prove the Python reference, attack harness, semi-fragile watermark, and shared vectors.
- [ ] **Task 4:** Execute Tasks B1–B4 in the control-plane/web plan while the algorithm benchmark runs.
- [ ] **Task 5:** Execute Tasks A7–A9 to port the released profile, PDF pipeline, and bounded local worker to Rust.
- [ ] **Task 6:** Execute Tasks B5–B9 to connect outbox, RabbitMQ, R2-compatible storage, result ingestion, OpenAPI, and React.
- [ ] **Task 7:** Execute Tasks P3–P5 to harden containers, add observability, and enforce full CI/multi-architecture gates.
- [ ] **Task 8:** Run system E2E, attack matrix, authorization, cleanup, and resource benchmarks; resolve all G3 blockers.
- [ ] **Task 9:** Execute Tasks P6–P7 and observe backup/restore, rollback, and offline-demo postconditions.
- [ ] **Task 10:** Execute Tasks P8–P10 to configure/audit managed dependencies, audit/start Azure, deploy by digest, and cut over DNS/TLS with rollback evidence.
- [ ] **Task 11:** Freeze evaluation outputs and create presentation artifacts from observed results only.
- [ ] **Task 12:** Run two complete rehearsals and tag the exact release used for the final demo.

## Presentation Deliverables

**Files:**

- Create: `docs/evaluation/mvp-results.md`
- Create: `docs/evaluation/benchmark-summary.csv`
- Create: `presentation/demo-script.md`
- Create: `presentation/qa-notes.md`
- Create: `presentation/SplitBind-Nhom9.pptx`

- [ ] Export benchmark tables directly from the versioned benchmark result, not by retyping values.
- [ ] Include one slide that contrasts robust watermark, semi-fragile watermark, hash, and digital signature.
- [ ] Include one slide that explicitly states that a matched issuance is not proof of who leaked the file.
- [ ] Demonstrate exact-file verification and one transformed-file attribution case.
- [ ] Demonstrate `PARTIAL_EVIDENCE` or `NO_WATERMARK` so uncertainty is visible rather than hidden.
- [ ] Record a local backup video using the frozen fixtures and release digest.
- [ ] Rehearse the offline Compose path with network access disabled.

## Definition of Complete

This plan is complete only when the product-level Definition of Done in the specification is observed: both workflows run end-to-end; algorithm claims are benchmarked; manifest signatures verify independently; RBAC and cleanup paths are tested; resource and container gates pass; backup/restore and rollback are rehearsed; Azure is reconstructible by documented procedure; the public hostname is healthy over TLS; and the offline demonstration remains usable without Azure or Internet access.
