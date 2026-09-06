# ADR-002: Temporary Python data plane for Integrity Release 0.1

Date: 2026-09-06

## Status

Accepted for Integrity Release 0.1 only. It does not supersede the Rust/RabbitMQ target for the full fingerprint product.

## Context

Fingerprint V1, V2 and V3 have no promoted profile. The verified V3 pre-gate completed 352/352 rows without execution errors or false attributions, but all four candidates failed the JPEG, resize and crop rate gates. Therefore the Rust fingerprint port remains correctly blocked.

The project nevertheless needs a usable academic production release by 2026-09-07. The repository already has a bounded Python issuance/verification worker, RBAC, upload/storage boundaries, job ownership, cleanup and an observed local end-to-end path. It does not yet have a Rust worker, RabbitMQ bridge, hardened runtime images or public release evidence.

## Decision

Integrity Release 0.1 will use a separate Python worker process with concurrency one and PostgreSQL job claims. It will issue a lossless image-only PDF containing a visible pseudonymous marker and create signed manifest evidence. Verification will attribute only an exact output-hash match with a valid manifest/signature. It will not execute an unreleased fingerprint decoder for production attribution.

The API and worker may share one container image, but only the worker receives the Ed25519 private signing-key mount. The API stores and verifies public-key metadata only. PostgreSQL and S3-compatible object storage remain external. Production Compose for this release contains Caddy, API and worker; RabbitMQ/outbox services are omitted from the running topology.

## Consequences

Positive consequences:

- A useful release can be tested and deployed without weakening Gate G1.
- Exact-file integrity, signed manifests, authorization and audit remain real capabilities.
- The existing bounded processing and cleanup code receives additional production tests instead of being rewritten under deadline pressure.

Costs and limitations:

- Transformed-file source attribution is unavailable.
- PostgreSQL polling is less scalable than RabbitMQ and supports only the single-worker academic deployment.
- Python native PDF/image libraries require strict container, timeout and resource isolation.
- The full release must later restore RabbitMQ/outbox delivery and replace the worker with Rust after a fingerprint profile passes G1 and cross-language parity.

## Guardrails

- `SPLITBIND_RELEASE_MODE=integrity_v1` is the only production processing mode for this release.
- Worker concurrency is exactly one, timeout is 600 seconds, retry is at most two, decoded input is at most 40 megapixels and temporary data is at most 2 GiB.
- No private signing key is mounted into Caddy or API.
- UI and reports must state that transformed fingerprint attribution is unavailable.
- This ADR cannot be used to label V1/V2/V3 as released or to skip the later full-product release gates.

## Replacement condition

ADR-002 is superseded when a versioned fingerprint profile passes the unchanged benchmark gates, Rust parity and bounded worker tests pass, RabbitMQ/outbox result flow is observed, and the full platform release gates succeed.
