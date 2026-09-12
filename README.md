# SplitBind

Document integrity tracing for the Information Security capstone project of Group 9.

SplitBind issues a per-recipient copy of a PDF, records signed evidence of what it issued, and later answers one question about a suspect file: does this document match an issuance this system performed, and has it been altered since. The live deployment runs at [splitbind.qivarn.id.vn](https://splitbind.qivarn.id.vn) with a Vietnamese interface.

## Status

Integrity Release 0.1 is deployed and serving. Its processing mode is `integrity_v1`, defined by [ADR-002](docs/decisions/002-integrity-release-python-worker.md).

| Capability | State |
|---|---|
| Issuance with a visible pseudonymous marker | Released |
| Exact-file integrity verification against a signed manifest | Released |
| Ed25519 signing over RFC 8785 canonical manifests | Released |
| Role-scoped access, append-only audit evidence, bounded retention | Released |
| Transformed-copy attribution by fingerprint decoding | Off by default, see [ADR-003](docs/decisions/003-enable-transformed-attribution.md) |
| Robust fingerprint profile passing Gate G1 | Not released |
| Rust worker, RabbitMQ delivery | Not implemented in this release |

## What the evidence means

The distinction below is the point of the project, not a disclaimer.

A verification answers from two sources. The exact SHA-256 of the file is compared against the hash recorded in a signed issuance manifest, and the manifest signature is checked against a registered Ed25519 public key. A match identifies the issuance and proves the bytes are unchanged. A mismatch proves the bytes differ from what was issued.

It does not prove who leaked, altered, or redistributed a document. A byte-identical match identifies a document, not a person's conduct. The interface and every result payload state this limit rather than implying attribution.

When transformed attribution is enabled, a fingerprint decoder may add a positive identification, and it may never contradict the hash result. Measured across five production trials, no transformed copy was attributed and every failure returned zero valid votes with no attribution, so the capability cannot accuse anyone; it simply does not answer. [ADR-003](docs/decisions/003-enable-transformed-attribution.md) records the measurement and the carrier root cause behind it.

## Architecture

The deployed topology is three containers behind one edge.

```
Caddy (TLS, HTTP/3, static web bundle)
  -> API      Django 5.2 REST control plane
  -> Worker   Python issuance and verification worker, concurrency 1
External: Neon PostgreSQL, Cloudflare R2
```

- **Web** React 19, TypeScript and Vite, generated from the OpenAPI contract so client and server cannot drift.
- **API** Django REST Framework on Python 3.11. Browser session and CSRF authentication, organization-scoped selectors, direct-to-storage uploads, append-only audit events.
- **Worker** A separate process claiming jobs from PostgreSQL. This release ships no message broker, and readiness reports `broker: not_applicable` rather than pretending one is healthy.
- **Signing** Only the worker receives the Ed25519 private key. The API stores and verifies public-key metadata only.
- **Images** Built by GitHub Actions and deployed by immutable digest (`name@sha256:...`). The production host only pulls; it never builds.

Runtime ceilings are declared once in [`services/api/config/limits.py`](services/api/config/limits.py) and asserted at startup: 50 pages, 100 MB per PDF, 40 megapixels per decoded image, 140 megapixels per rasterized document, a 600 second job timeout, and worker concurrency of one.

## Repository layout

| Path | Contents |
|---|---|
| `apps/web` | React interface and the generated TypeScript API client |
| `services/api` | Django control plane, worker, migrations, test suite |
| `research/python` | Reference implementation: payload and ECC, DWT-DCT-QIM fingerprinting, ORB synchronization, semi-fragile integrity watermark, RFC 8785 manifests |
| `contracts` | Frozen algorithm profiles, JSON schemas, and the validated OpenAPI contract |
| `infra` | Caddy edge, Compose topologies, deployment and audit scripts |
| `tests/platform` | Static contract checks over the Compose graph, the Caddy edge, and the operational scripts |
| `fixtures` | Deterministic synthetic corpora; no real document or personal data |
| `docs` | Decisions, evaluations, runbooks, and the knowledge base |

## Running it

Requires Python 3.11.9, Node 24.18.0 and Docker Desktop. A local presentation stack starts the API, one worker and Vite on the host, with MinIO bound to loopback:

```powershell
powershell -ExecutionPolicy Bypass -File infra/scripts/run_demo.ps1
powershell -ExecutionPolicy Bypass -File infra/scripts/run_demo.ps1 -Stop
```

[`docs/runbooks/local-and-offline.md`](docs/runbooks/local-and-offline.md) walks through an issuance followed by a verification.

## Verification

One entry point runs everything, and continuous integration runs the same commands:

```bash
python infra/scripts/run_smoke.py            # full suite
python infra/scripts/run_smoke.py --release  # everything except the research suite
```

It executes the API test suite, regenerates and validates the OpenAPI schema, regenerates the TypeScript client and fails on any drift, runs the web tests and type check, the platform contract tests, and the research contract tests.

## Deployment

Rollout is scripted and self-verifying:

```powershell
powershell -File infra/scripts/update_production_release.ps1 -ApiImage <digest> -WebImage <digest>
```

The script syncs the Compose file, applies migrations, reads the required limit table out of the image being deployed rather than restating it, validates the Caddyfile, restarts, then polls liveness and readiness and fails if either does not come back.

No script stores the deployment target. The host, administrator account, and storage endpoints come from environment variables documented by name in [`infra/scripts/README.md`](infra/scripts/README.md); a script that cannot resolve a required setting stops and names the variable.

## Research status

No fingerprint profile has been promoted. Gate G1 is unchanged and every result below is recorded as a factual no-release outcome.

| Run | Rows | Outcome |
|---|---|---|
| [V1 full matrix](docs/evaluation/fingerprint-profile-v1.md) | 32,736 | Completed with 1,488 execution errors; no candidate promoted |
| [V2 pre-gate](docs/evaluation/fingerprint-pregate-v2.md) | 1,408 | Zero execution errors, zero false attributions, empty qualified selection |
| [V3 pre-gate](docs/evaluation/fingerprint-pregate-v3.md) | 352 | Zero execution errors, zero false attributions, empty qualified selection |

Precision has held throughout: no run has ever produced a false attribution. Robustness has not. The production measurement in ADR-003 identified why the benchmark could not: a text page is close to the worst carrier this design can be given, being mostly white with sparse glyph edges and almost no mid-frequency texture where the QIM payload lives. A gradient carrier retained payload evidence through a 0.50 rescale while a text page produced nothing even unattacked, and every document this product issues is a text page. A robustness rate measured on gradient and vector corpora is therefore not a product capability.

## Documentation

- [ADR-001: Azure production architecture](docs/decisions/001-azure-production-architecture.md)
- [ADR-002: Python data plane for Integrity Release 0.1](docs/decisions/002-integrity-release-python-worker.md)
- [ADR-003: Transformed attribution as an off-by-default capability](docs/decisions/003-enable-transformed-attribution.md)
- [Local and offline runbook](docs/runbooks/local-and-offline.md)
- [Knowledge base](docs/knowledge/)

Course materials, correspondence, and deployment evidence are kept local and are not part of this repository.

## Security boundaries

- No personal data, real documents, secrets, or production keys are committed. Environment variables are documented by name, never by value.
- The private signing key exists only on the worker and is never mounted into the edge or the API.
- No PDF enters a message queue; only identifiers and minimal metadata cross a process boundary.
- Every success, failure, timeout, and cancellation path removes its temporary files.
- The system is never presented as proof of who leaked a document.

## License

Not licensed for open-source use. All rights reserved to the project group pending a license decision.
