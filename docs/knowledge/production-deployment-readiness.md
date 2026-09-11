# Production Deployment Readiness

Durable engineering lessons from deploying a containerised Django + React application behind a TLS-terminating reverse proxy, with external managed PostgreSQL and S3-compatible object storage.

Run-specific rollout evidence - image digests, workflow run IDs, server addresses, account identifiers - is deliberately **not** in this file. It contains live infrastructure identifiers and personal data, so it lives outside the publication set in `docs/internal/splitbind-rollout-evidence.md`. Keep that boundary: a fact that names a live host, IP, subscription, bucket, principal, or credential belongs there, not here.

## Deployment architecture invariants

- Production Compose runs only `caddy`, `api`, and `worker`. PostgreSQL and object storage are external managed services, not containers in the stack.
- Runtime images must use registry references pinned as `name@sha256:<digest>`. Mutable tags are not acceptable deployment inputs - a tag can be re-pointed between the verification run and the deployment, which silently breaks the chain of evidence.
- Separate the build plane from the run plane. A GitHub Actions workflow runs the release smoke gate, builds and publishes `linux/amd64` images, and records their immutable digests; the production VM only pulls and runs. A resource-constrained workstation is not a viable image build host, and the VM must not become one.
- Production settings require `DJANGO_SECRET_KEY`, `DATABASE_URL`, `SPLITBIND_ALLOWED_HOSTS`, the six bounded runtime-limit variables, and object-storage bucket credentials. The worker additionally receives an encrypted Ed25519 PKCS#8 key and a separate passphrase file through read-only secret mounts. Record variable *names* in documentation; never their values.
- Remove automatic migration from API startup. Package a dedicated one-shot migration entrypoint plus a fail-closed, idempotent bootstrap command for the first organization and administrator. Startup-time migration makes every container restart a schema event.
- A bootstrap deployment script that regenerates configuration, runs migrations and stops the whole stack is the wrong tool for a narrowly scoped update. For a web-only rollout, replace only the proxy/web image by immutable digest and keep a saved rollback configuration; preserve API and worker images, secrets, database, signing keys, DNS and existing Compose configuration.

## Safe deployment order

Audit cloud cost and network guards; complete local end-to-end tests; publish images by digest; materialize secrets outside Git; run one-shot migration and bootstrap; start Compose without mutating DNS; verify through SSH port forwarding; back up metadata; update only the application's own DNS record; verify HTTPS and both user workflows; roll back DNS and image digests on any failed postcondition.

Only the application subdomain may change. The apex domain and unrelated DNS records stay untouched - a deployment that can alter the apex can take down systems that have nothing to do with it.

## HTTPS, CSRF and cross-origin boundaries

- **Django CSRF Origin checking behind a proxy.** In Django 4.0+, browsers automatically send an `Origin` header on state-changing requests (POST/PUT/DELETE) over HTTPS. `CsrfViewMiddleware` strictly checks `request.META["HTTP_ORIGIN"]` against `CSRF_TRUSTED_ORIGINS`. If `CSRF_TRUSTED_ORIGINS` does not explicitly contain the public HTTPS origin, every browser request fails with HTTP 403 ("CSRF validation failed: Origin checking failed") even when the CSRF token in header and cookie are completely valid. Behind a TLS-terminating reverse proxy, `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` must also be set so Django recognises the request scheme.
- **Content Security Policy blocks direct-to-bucket uploads.** When the client uploads files directly to S3-compatible presigned URLs via `fetch(upload_url, { method: 'PUT', ... })`, the reverse proxy must include the storage endpoint in `connect-src` (for example `connect-src 'self' https://*.r2.cloudflarestorage.com;`). If typography or icons use inline base64 data URIs, `font-src 'self' data:;` and `img-src 'self' data: blob:;` must also be declared. Otherwise `default-src 'self'` blocks font rendering and silently aborts uploads in the browser engine before any network dispatch - there is no server-side trace to debug from.
- **The deployed policy has no `style-src`, so it inherits `default-src 'self'`.** Read from the live response header on 2026-09-11: `default-src 'self'; connect-src 'self' https://*.r2.cloudflarestorage.com; font-src 'self' data:; img-src 'self' data: blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'`. Two consequences for any frontend motion work. GSAP and ScrollTrigger keep working because they mutate the CSSOM (`el.style.transform = ...`), which CSP does not govern; the restriction applies to style *parsing*, not to script-driven property assignment. But a literal `style="..."` attribute written into HTML, a `<style>` element injected at runtime, and any library loaded from an external CDN are all blocked with no server-side trace. Bundle every dependency through the build, and keep initial animation states in JavaScript rather than in markup.

- **Bucket CORS is required for presigned uploads.** A direct browser-to-bucket upload is cross-origin, so browsers issue an `OPTIONS` preflight before the `PUT`. Cloudflare R2 returns `HTTP/1.1 403 Forbidden` to preflight unless a CORS policy is set on the bucket (AllowedOrigins: the public app origin; AllowedMethods: `PUT, GET, HEAD, POST`; AllowedHeaders: `*`; ExposeHeaders: `ETag, x-amz-meta-sha256`). Without it, uploads fail with `net::ERR_FAILED` / `Failed to fetch`.
- **Client-side session initialization race.** A login form that submits before the session bootstrap request has returned sends neither CSRF cookie nor header, and the server correctly rejects it with HTTP 403. Reproduce it by delaying `GET /api/v1/auth/session` by ~3000 ms in a real browser. The fix is client-side: await successful session initialization, guard submission while it is pending, and offer a retry. Never weaken server CSRF validation to make a client race disappear.

## Container packaging traps

- **Partial contract directory copies.** Copying only a subdirectory of a contracts tree (for example `contracts/algorithm`) omits sibling schema directories. If request-building code validates payloads against `contracts/jsonschema/<name>.schema.json` and the file is absent, Python raises `FileNotFoundError` and the endpoint returns HTTP 500 with no schema-related message. All runtime containers must copy the entire contracts directory (`COPY --chown=10001:10001 contracts /app/contracts`).
- Services run under read-only root filesystems, non-root users, dropped capabilities, and memory limits. Verify each of those properties directly after a cutover rather than inferring them from the Compose file.

See `docker-build-and-compose-secrets.md` for build-argument scope, non-root secret permissions, capability retention, and the tmpfs metadata-retrieval fallback.

## Data model and account management

- **Renaming a principal is safe when foreign keys target an immutable surrogate key.** Renaming a user in PostgreSQL preserves organization membership, audit logs and issuance history because every foreign key references the immutable UUID `user.id`, not the login name. Verify that the natural key is genuinely unreferenced before relying on this.
- **Programmatic user creation bypasses password validators.** `User.objects.create_user()` computes the password hash directly and never runs `AUTH_PASSWORD_VALIDATORS`, which the registration form would enforce. This is convenient for seeding QA accounts and dangerous on a production database: a trivially weak password can land on an account with an administrator role reachable through the public origin. If a programmatic account is created against production, record it as an item to rotate or disable, and never leave it as the standing QA credential.
- **Authentication principal is not the document recipient.** `User` is the operator who logs in; `Recipient` is the party a document is issued to and whose identity is encoded into the watermark. The issuance endpoint resolves `Recipient.objects.get(id=recipient_id, organization_id=actor.organization_id)`. Passing a `User.id` where a `Recipient.id` is expected raises `Recipient.DoesNotExist`, surfaced as `WorkflowNotFound("WORKFLOW_NOT_FOUND")` and the scoped-permission message in the UI. The two ID spaces look identical (both UUIDs) and will not fail loudly at the type level.
- **Signing key candidate uniqueness.** The worker queries active signing keys matching its private key and asserts exactly one candidate. Duplicate active records for the same organization and public key - easily produced by repeated bootstrap passes - fail with `MANIFEST_SIGNING_KEY_UNREGISTERED`, triggering rollback and marking the job `DEMO_RESULT_COMMIT_FAILED`. Obsolete keys must be explicitly transitioned to `REVOKED` so exactly one active key exists per keypair.

## Frontend validation

Submit buttons must be explicitly disabled (`disabled={isPending || Boolean(validationError)}`) *and* the form's `submit()` must short-circuit when `validationError` is present. The disabled attribute alone does not prevent programmatic or keyboard-initiated dispatch on an invalid file (oversized, wrong extension).

## Release tooling patterns

- **Dynamic SSH source-IP synchronisation.** A script that detects the current public IP and updates the cloud firewall's SSH allow rule removes the manual portal step whenever a residential or mobile ISP rotates the client address, while preserving a zero-public-access posture on port 22. Treat each detected address as personal data: it belongs in local evidence, not in committed documentation.
- **Standardised release harness.** Accept immutable API and web digests as parameters (or read them from a release environment file), synchronise the SSH rule, create a mode-700 rollback directory with a validated metadata dump, pull images, run a migration check in a disposable container, update the Compose environment file, restart services, and verify health endpoints - all without exposing or requiring raw database or storage secrets.
- Discover real filenames before reading them. Guessed paths cost a round trip each: a workflow assumed to be `.yml` that is actually `.yaml`; a management command assumed to sit under the model app; a config assumed to be at the worktree root instead of app-local; modules assumed to be `.ts` that are `.tsx`. Enumerate with `rg --files` first. None of these changed deployed state, but each was an avoidable failed tool call.

## Evidence discipline for deployments

- A merged pull request is source publication evidence only. It is not evidence of a deployment, and not evidence of a public DNS cutover. State which one you actually have.
- A rollout whose authenticated smoke timed out is an **unverified application postcondition**, not a successful rollout, even when root and health endpoints return 200. Restore the prior image while diagnosing.
- When the same failure reproduces on the previous image, the new release is not established as the cause. Do not attribute a regression to the change under test until it has been shown absent from the baseline.
- Diagnose authentication failures from response status codes, cookie presence, and safe error codes only. Never print secret header values, cookies, or passwords into smoke output or release artifacts.
- Do not describe a release as public production until local end-to-end tests, isolated backup and restore, rollback, and public HTTPS cutover have all passed and been observed.
- Exact-file hash matching proves that a downloaded artifact is byte-identical to the issued one. It is **not** robust fingerprint recovery, and a non-matching file must never be presented as proof that someone edited or leaked a document. Keep result copy free of attribution.
