# SplitBind Platform and Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the reproducible, resource-bounded platform that runs SplitBind locally, offline, in CI, and on the existing Azure VM, then release it at `https://splitbind.qivarn.id.vn` with tested backup, restore, rollback, and DNS/TLS cutover procedures.

**Architecture:** Local and offline environments use PostgreSQL, RabbitMQ, MinIO, and synthetic keys under Docker Compose; production runs only Caddy, Django API/outbox, RabbitMQ, and the Rust worker on the Azure VM while Neon, R2, and Key Vault remain external. Release images are selected by immutable digest, private key material is mounted only into the worker, and every cloud mutation is guarded by a cold Azure audit, an observed budget, release-candidate health, backup evidence, and a recoverable rollback state.

**Tech Stack:** Node.js 24 with npm workspaces, Python 3.11, Rust 1.97, Docker Compose, Caddy, PostgreSQL, RabbitMQ, MinIO, Prometheus, GitHub Actions, OCI multi-architecture images, Azure CLI

**Spec:** `docs/superpowers/specs/2026-08-13-splitbind-production-design.md`

## Global Constraints

- The production hostname is `splitbind.qivarn.id.vn`; do not modify the apex `qivarn.id.vn`, its name servers, MX records, email service, or existing hosting records.
- Never commit or hardcode the current Azure public IP, administrator IPv4, secrets, production object keys, presigned URLs, or private backup evidence.
- Keep the Azure for Students spending limit and do not upgrade to Pay-as-you-go.
- The annual USD 100 Azure budget with actual-cost alerts at 25%, 50%, 75%, and 90% must exist and be observed before the VM is started for deployment or DNS is changed.
- `vm-splitbind-prod` already exists and was observed deallocated on 27/08/2026. Audit it in place; do not provision a second VM, public IP, NIC, NSG, disk, or resource group.
- Keep the production VM deallocated whenever a public environment is unnecessary; its retained Standard public IP and disk can still consume credit.
- Only host TCP `80/443` may be public. TCP `22` is SSH-key-only and restricted to the administrator's runtime-discovered IPv4 `/32`; PostgreSQL, RabbitMQ, Docker, and metrics ports remain private.
- Production container limits are Caddy/static React `128 MiB`, Django API plus its event-bridge process `640 MiB` combined, RabbitMQ `512 MiB`, and Rust worker `1.5 GiB`; the combined limit is at most `3 GiB`. This plan allocates the spec's combined Django budget internally as API `512 MiB` plus event bridge `128 MiB`.
- The worker runs one job at a time, has a 600-second job timeout, and receives a 2 GiB `/tmp` quota. Production rejects configured safety limits above coded ceilings.
- Every production container runs non-root with a read-only root filesystem, explicit writable mounts, dropped Linux capabilities, `no-new-privileges`, and a health check.
- Django receives application/database/storage/broker secrets but never the private Ed25519, fingerprint, or integrity keys. Only the Rust worker mounts those three private key families.
- Local and offline environments use only synthetic test keys and synthetic fixtures. They never copy production secrets or real course documents.
- Liveness is independent of external services. Readiness covers PostgreSQL, RabbitMQ, storage configuration, and active public-key metadata without reading private key material.
- Full attack benchmarks run manually or on schedule, not on every commit. CI artifacts containing failure diagnostics or SBOMs have one-day retention.
- DNS cutover follows a healthy release candidate, an observed backup/restore drill, an observed rollback drill, a cold and running Azure audit, and capture of the previous DNS state and image digests.

---

## File Structure Lock-In

```text
package.json                         npm workspace entry point
package-lock.json                    reproducible JavaScript dependency graph
.nvmrc                              Node.js toolchain pin
.python-version                     Python toolchain pin
rust-toolchain.toml                 Rust, rustfmt, and Clippy pin
infra/
  caddy/Caddyfile                   same-origin TLS edge; never exposes metrics
  compose/
    compose.local.yaml              developer stack and optional profiles
    compose.offline.yaml            pull-free presentation stack
    compose.production.yaml         Azure services and hard limits
    config-test.env                 synthetic values for static validation
  docker/
    api.Dockerfile                  Django and outbox runtime image
    worker.Dockerfile               Rust worker runtime image
    web.Dockerfile                  React build copied into non-root Caddy
    ops.Dockerfile                  pinned PostgreSQL and age backup tools
  observability/
    prometheus.yaml                 local-only metric collection
    alerts.yaml                     release alert contract
  release/
    release.schema.json             immutable image/revision manifest
    offline-images.txt              exact image digests exported for demo
  scripts/
    verify-toolchain.ps1            local prerequisite check
    ci.ps1                          local CI-equivalent entry point
    backup-metadata.sh              encrypted PostgreSQL metadata export
    restore-drill.sh                isolated restore verification
    deploy.sh                       digest-based production deploy
    rollback.sh                     image and migration rollback
    offline-demo.ps1                pull-free local startup and smoke
    azure_preflight.py              cold/running Azure invariant audit
    dns-evidence.ps1                authoritative DNS observation only
tests/platform/                     stdlib-based platform contract tests
tests/security/                     rendered Compose and image policy tests
.github/workflows/
  ci.yaml                           code, contract, and security gates
  images.yaml                       amd64/arm64 build, scan, and SBOM
  benchmark.yaml                    manual/scheduled research benchmark
docs/runbooks/
  local-and-offline.md              developer and presentation operation
  backup-and-restore.md             backup ownership and restore evidence
  release-and-rollback.md           approval, deployment, and recovery
  azure-and-dns-cutover.md          budget, audit, start, DNS, TLS, stop
```

## Stable Platform Interfaces

```text
ReleaseManifestV1
  schema_version: 1
  git_commit: 40-character lowercase hexadecimal commit
  migration_id: non-empty string
  rollback_migration_id: non-empty string identifying the verified reverse target
  api_image: OCI reference ending @sha256:<64 lowercase hex>
  worker_image: OCI reference ending @sha256:<64 lowercase hex>
  web_image: OCI reference ending @sha256:<64 lowercase hex>
  created_at: RFC 3339 UTC timestamp

AzureAuditV1
  phase: cold | running
  budget_valid: boolean
  vm_power_state: VM deallocated | VM running
  vm_shape_valid: boolean
  identity_valid: boolean
  disk_valid: boolean
  public_ip_valid: boolean
  nsg_valid: boolean
  available_disk_bytes: non-negative integer | null
  blockers: array of stable blocker codes
```

### Task P1: Pin the root toolchain and npm workspace contract

**Owner:** Leader.

**Files:**

- Create: `package.json`
- Generate: `package-lock.json`
- Create: `.nvmrc`
- Create: `.python-version`
- Create: `rust-toolchain.toml`
- Create: `infra/scripts/verify-toolchain.ps1`
- Create: `.github/workflows/smoke.yaml`
- Test: `tests/platform/test_repository_contract.py`

**Interfaces:**

- Produces npm workspace selector `apps/*` and root scripts `format:check`, `lint`, `typecheck`, `test`, and `generate:api`.
- Produces `infra/scripts/verify-toolchain.ps1`, which checks development tools by default and adds GitHub/Azure CLI checks only with `-ReleaseTools`; neither mode requires the Docker daemon to be running.

- [ ] **Step 1: Write the failing repository-contract test**

```python
# tests/platform/test_repository_contract.py
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class RepositoryContractTest(unittest.TestCase):
    def test_root_toolchains_and_npm_workspace_are_pinned(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertTrue(package["private"])
        self.assertEqual(package["workspaces"], ["apps/*"])
        self.assertEqual((ROOT / ".nvmrc").read_text().strip(), "24.18.0")
        self.assertEqual((ROOT / ".python-version").read_text().strip(), "3.11.9")
        rust = (ROOT / "rust-toolchain.toml").read_text(encoding="utf-8")
        self.assertIn('channel = "1.97.1"', rust)
        self.assertIn('components = ["clippy", "rustfmt"]', rust)
        self.assertIn("test_repository_contract.py", (ROOT / ".github/workflows/smoke.yaml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and observe the missing root manifests**

Run: `python -m unittest discover -s tests/platform -p "test_repository_contract.py" -v`

Expected: FAIL with `FileNotFoundError` for `package.json`.

- [ ] **Step 3: Add the exact root manifests and prerequisite script**

```json
{
  "name": "splitbind",
  "private": true,
  "workspaces": ["apps/*"],
  "engines": { "node": ">=24.18.0 <25", "npm": ">=12 <13" },
  "scripts": {
    "format:check": "npm run format:check --workspaces --if-present",
    "lint": "npm run lint --workspaces --if-present",
    "typecheck": "npm run typecheck --workspaces --if-present",
    "test": "npm run test --workspaces --if-present",
    "generate:api": "npm run generate:api --workspace @splitbind/web"
  }
}
```

```toml
# rust-toolchain.toml
[toolchain]
channel = "1.97.1"
components = ["clippy", "rustfmt"]
profile = "minimal"
```

```powershell
# infra/scripts/verify-toolchain.ps1
param([switch]$ReleaseTools)
$ErrorActionPreference = "Stop"
$expected = [ordered]@{ node = "v24."; npm = "12."; python = "Python 3.11."; rustc = "rustc 1.97." }
foreach ($name in $expected.Keys) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { throw "MISSING_TOOL:$name" }
    $actual = (& $name --version | Select-Object -First 1).Trim()
    if (-not $actual.StartsWith($expected[$name])) { throw "TOOL_VERSION:$name:$actual" }
}
foreach ($name in @("docker")) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { throw "MISSING_TOOL:$name" }
}
if ($ReleaseTools) {
    foreach ($name in @("gh", "az")) {
        if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { throw "MISSING_RELEASE_TOOL:$name" }
    }
}
Write-Output "TOOLCHAIN_OK"
```

Write `24.18.0` to `.nvmrc`, write `3.11.9` to `.python-version`, and run `npm install --package-lock-only --ignore-scripts` to generate the root lock file.

```yaml
# .github/workflows/smoke.yaml
name: smoke
on: [pull_request, push]
permissions: { contents: read }
jobs:
  repository-contract:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - uses: actions/setup-node@v4
        with: { node-version-file: .nvmrc, cache: npm }
      - run: npm ci --ignore-scripts
      - run: python -m unittest discover -s tests/platform -p "test_repository_contract.py" -v
```

- [ ] **Step 4: Prove the static contract and observed local tools pass**

Run: `python -m unittest discover -s tests/platform -p "test_repository_contract.py" -v`

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File infra/scripts/verify-toolchain.ps1`

Expected: PASS and final output `TOOLCHAIN_OK`; the Docker daemon may remain stopped.

- [ ] **Step 5: Commit**

```bash
git add package.json package-lock.json .nvmrc .python-version rust-toolchain.toml infra/scripts/verify-toolchain.ps1 .github/workflows/smoke.yaml tests/platform/test_repository_contract.py
git commit -m "build: pin splitbind repository toolchains"
```

### Task P2: Define local, offline, and production Compose topologies with Caddy

**Owner:** Leader defines production boundaries; member verifies local/offline instructions.

**Files:**

- Create: `infra/compose/compose.local.yaml`
- Create: `infra/compose/compose.offline.yaml`
- Create: `infra/compose/compose.production.yaml`
- Create: `infra/compose/config-test.env`
- Create: `infra/compose/config-test-api.env`
- Create: `infra/compose/config-test-worker.env`
- Create: `infra/compose/config-test-secret.bin`
- Create: `infra/caddy/Caddyfile`
- Create: `docs/runbooks/local-and-offline.md`
- Test: `tests/platform/test_compose_topology.py`

**Interfaces:**

- Local profiles are `core`, `research`, `observability`, and `full`; `core` supplies Caddy, API, outbox, RabbitMQ, worker, PostgreSQL, and MinIO.
- Offline Compose consumes only locally loaded immutable images and synthetic keys, sets `pull_policy: never`, and uses no Neon, R2, Key Vault, or public DNS dependency.
- Production supplies exactly `caddy`, `api`, `outbox`, `rabbitmq`, and `worker`; it consumes external Neon/R2 endpoints. Secret source files live on the host under `/run/splitbind/secrets`, while Compose exposes only the three worker-private files inside that container under `/run/secrets`.

- [ ] **Step 1: Write failing static topology tests**

```python
# tests/platform/test_compose_topology.py
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class ComposeTopologyTest(unittest.TestCase):
    def test_profiles_and_external_boundaries_are_explicit(self):
        local = (ROOT / "infra/compose/compose.local.yaml").read_text(encoding="utf-8")
        offline = (ROOT / "infra/compose/compose.offline.yaml").read_text(encoding="utf-8")
        production = (ROOT / "infra/compose/compose.production.yaml").read_text(encoding="utf-8")
        for profile in ("core", "research", "observability", "full"):
            self.assertIn(profile, local)
        self.assertIn("pull_policy: never", offline)
        self.assertNotIn("keyvault.azure.net", offline.lower())
        self.assertNotIn("postgres:", production)
        self.assertNotIn("minio:", production)
        self.assertNotIn("15672:15672", production)

    def test_caddy_is_same_origin_and_does_not_proxy_metrics(self):
        caddy = (ROOT / "infra/caddy/Caddyfile").read_text(encoding="utf-8")
        self.assertIn("{$SPLITBIND_HOSTNAME}", caddy)
        self.assertIn("reverse_proxy api:8000", caddy)
        self.assertNotIn("/metrics", caddy)
```

- [ ] **Step 2: Run tests and observe missing topology files**

Run: `python -m unittest discover -s tests/platform -p "test_compose_topology.py" -v`

Expected: FAIL with `FileNotFoundError` for `compose.local.yaml`.

- [ ] **Step 3: Implement the exact service boundaries and same-origin route**

Use this local service/profile map in `compose.local.yaml`; P2 names local images so config rendering is independent, then P3 adds matching build definitions. Health endpoints come from B1/B6:

```yaml
name: splitbind-local
services:
  postgres:
    image: postgres:17-alpine
    profiles: [core, full]
    networks: [app]
  minio:
    image: minio/minio
    command: server /data
    profiles: [core, full]
    networks: [app]
  rabbitmq:
    image: rabbitmq:4-management-alpine
    profiles: [core, full]
    networks: [app]
  api:
    image: splitbind-api:local
    profiles: [core, full]
    networks: [app]
    depends_on: [postgres, minio, rabbitmq]
  outbox:
    image: splitbind-api:local
    command: ["python", "manage.py", "run_event_bridge"]
    profiles: [core, full]
    networks: [app]
    depends_on: [postgres, rabbitmq]
  worker:
    image: splitbind-worker:local
    profiles: [core, full]
    networks: [app]
    depends_on: [rabbitmq, minio]
  caddy:
    image: splitbind-web:local
    profiles: [core, full]
    ports: ["8080:8080"]
    environment: { SPLITBIND_HOSTNAME: "http://:8080", ACME_EMAIL: "local@example.invalid" }
    networks: [app]
    depends_on: [api]
  research:
    profiles: [research, full]
    image: splitbind-research:local
  prometheus:
    image: prom/prometheus
    profiles: [observability, full]
    networks: [app]
  e2e:
    image: splitbind-e2e:local
    profiles: [full]
    command: ["npm", "run", "e2e", "--workspace", "@splitbind/web"]
    environment: { BASE_URL: "http://caddy:8080" }
    networks: [app]
    depends_on: [caddy, outbox, worker]
networks:
  app: {}
```

Use the production image and secret contract below in `compose.production.yaml`; P3 adds the hardening keys and exact memory limits without changing this service set:

```yaml
name: splitbind-production
services:
  caddy:
    image: ${WEB_IMAGE:?WEB_IMAGE must be an immutable digest}
    ports: ["80:8080", "443:8443"]
    environment:
      SPLITBIND_HOSTNAME: ${SPLITBIND_HOSTNAME:?SPLITBIND_HOSTNAME is required}
      ACME_EMAIL: ${ACME_EMAIL:?ACME_EMAIL is required}
    networks: [app]
  api:
    image: ${API_IMAGE:?API_IMAGE must be an immutable digest}
    env_file: ["${API_ENV_FILE:-/run/splitbind/secrets/api.env}"]
    networks: [app]
  outbox:
    image: ${API_IMAGE:?API_IMAGE must be an immutable digest}
    command: ["python", "manage.py", "run_event_bridge"]
    env_file: ["${API_ENV_FILE:-/run/splitbind/secrets/api.env}"]
    networks: [app]
  rabbitmq:
    image: ${RABBITMQ_IMAGE:?RABBITMQ_IMAGE must be an immutable digest}
    networks: [app]
  worker:
    image: ${WORKER_IMAGE:?WORKER_IMAGE must be an immutable digest}
    env_file: ["${WORKER_ENV_FILE:-/run/splitbind/secrets/worker.env}"]
    secrets: [manifest_signing_key, fingerprint_key, integrity_key]
    networks: [app]
networks:
  app: {}
secrets:
  manifest_signing_key: { file: "${MANIFEST_SIGNING_KEY_FILE:-/run/splitbind/secrets/manifest-signing-key.pk8}" }
  fingerprint_key: { file: "${FINGERPRINT_KEY_FILE:-/run/splitbind/secrets/fingerprint-key.bin}" }
  integrity_key: { file: "${INTEGRITY_KEY_FILE:-/run/splitbind/secrets/integrity-key.bin}" }
```

`config-test.env` selects the three `splitbind-*:local` images, a pinned RabbitMQ test image, `SPLITBIND_HOSTNAME=http://localhost:8080`, a non-deliverable `example.invalid` ACME email, the two synthetic env files, and the same synthetic secret file for all three key-file variables. The test env files contain only clearly marked local credentials and endpoints; none is accepted when `ENVIRONMENT=production` because application startup validates key length/format and production hostnames.

Use a second local-only Compose file for offline mode with the same five application images plus PostgreSQL, MinIO, and RabbitMQ; every image comes from `infra/release/offline-images.txt`, every service sets `pull_policy: never`, and `offline-demo.ps1` generates disposable synthetic credentials/keys under ignored `artifacts/offline/keys/` before startup.

Use this complete edge contract in `infra/caddy/Caddyfile`:

```caddyfile
{
    admin off
    http_port 8080
    https_port 8443
    email {$ACME_EMAIL}
}

{$SPLITBIND_HOSTNAME} {
    encode zstd gzip
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "same-origin"
        Permissions-Policy "camera=(), microphone=(), geolocation=()"
        Content-Security-Policy "default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    }
    handle /api/* {
        reverse_proxy api:8000
    }
    handle /health/* {
        reverse_proxy api:8000
    }
    handle {
        root * /srv/web
        try_files {path} /index.html
        file_server
    }
}
```

- [ ] **Step 4: Render all topologies without starting containers**

Run: `python -m unittest discover -s tests/platform -p "test_compose_topology.py" -v`

Run: `docker compose --env-file infra/compose/config-test.env -f infra/compose/compose.local.yaml --profile full config --quiet`

Run: `docker compose --env-file infra/compose/config-test.env -f infra/compose/compose.offline.yaml config --quiet`

Run: `docker compose --env-file infra/compose/config-test.env -f infra/compose/compose.production.yaml config --quiet`

Expected: PASS without contacting the Docker daemon; the rendered production service set contains no PostgreSQL or MinIO and publishes only host ports 80/443.

- [ ] **Step 5: Commit**

```bash
git add infra/compose infra/caddy docs/runbooks/local-and-offline.md tests/platform/test_compose_topology.py
git commit -m "feat(platform): define splitbind compose topologies"
```

### Task P3: Build hardened non-root images and enforce resource policy

**Owner:** Leader.

**Files:**

- Create: `infra/docker/api.Dockerfile`
- Create: `infra/docker/worker.Dockerfile`
- Create: `infra/docker/web.Dockerfile`
- Create: `infra/docker/ops.Dockerfile`
- Create: `infra/docker/e2e.Dockerfile`
- Create: `research/python/Dockerfile`
- Modify: `infra/compose/compose.local.yaml`
- Modify: `infra/compose/compose.production.yaml`
- Test: `tests/security/test_production_compose.py`
- Test: `tests/security/test_container_runtime.py`

**Interfaces:**

- Produces runtime images `splitbind-api`, `splitbind-worker`, `splitbind-web`, and `splitbind-ops` with no compiler, package cache, test corpus, or source tree in runtime layers.
- Produces rendered production limits of Caddy `134217728`, API `536870912`, outbox `134217728`, RabbitMQ `536870912`, and worker `1610612736` bytes; total `2952790016` bytes.
- Worker is the only service whose rendered `secrets` list contains `manifest_signing_key`, `fingerprint_key`, or `integrity_key`.

- [ ] **Step 1: Write failing rendered-policy tests**

```python
# tests/security/test_production_compose.py
import json
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "infra/compose/compose.production.yaml"
ENV = ROOT / "infra/compose/config-test.env"


def rendered():
    result = subprocess.run(
        ["docker", "compose", "--env-file", str(ENV), "-f", str(COMPOSE), "config", "--format", "json"],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


class ProductionPolicyTest(unittest.TestCase):
    def test_non_root_read_only_limits_and_private_keys(self):
        services = rendered()["services"]
        expected = {"caddy": 134217728, "api": 536870912, "outbox": 134217728,
                    "rabbitmq": 536870912, "worker": 1610612736}
        self.assertEqual(set(services), set(expected))
        self.assertEqual(sum(expected.values()), 2952790016)
        for name, limit in expected.items():
            self.assertNotIn(str(services[name]["user"]).split(":")[0], {"0", "root"})
            self.assertTrue(services[name]["read_only"])
            self.assertEqual(services[name]["mem_limit"], limit)
            self.assertIn("ALL", services[name]["cap_drop"])
            self.assertIn("no-new-privileges:true", services[name]["security_opt"])
        self.assertNotIn("secrets", services["api"])
        self.assertEqual({item["source"] for item in services["worker"]["secrets"]},
                         {"manifest_signing_key", "fingerprint_key", "integrity_key"})
```

- [ ] **Step 2: Run the policy test and observe missing hardening keys**

Run: `python -m unittest discover -s tests/security -p "test_production_compose.py" -v`

Expected: FAIL because the P2 Compose services do not yet set `user`, `read_only`, `mem_limit`, `cap_drop`, and `security_opt`.

- [ ] **Step 3: Add minimal multi-stage runtime images and exact Compose controls**

Each Dockerfile has a named build stage and a runtime stage. The API runtime copies only its virtual environment and `services/api`; the worker runtime copies only the release binary and required PDF shared libraries; the web runtime copies only `apps/web/dist`, Caddy, and `Caddyfile`; the ops runtime contains only `pg_dump`, `pg_restore`, `age`, and the backup scripts. Use numeric runtime users `10001:10001` for API/worker/web and the image's documented non-root RabbitMQ UID for RabbitMQ.

```dockerfile
# infra/docker/api.Dockerfile
FROM python:3.11.9-slim AS api-build
WORKDIR /build
COPY services/api/pyproject.toml services/api/
RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels ./services/api

FROM python:3.11.9-slim AS api
RUN groupadd --gid 10001 splitbind && useradd --uid 10001 --gid 10001 --no-create-home splitbind
COPY --from=api-build /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/* && rm -rf /wheels
WORKDIR /app
COPY services/api/ /app/
USER 10001:10001
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2"]
```

```dockerfile
# infra/docker/worker.Dockerfile
FROM rust:1.97.1-bookworm AS worker-build
WORKDIR /build
COPY services/worker/ ./services/worker/
RUN cargo build --locked --release --manifest-path services/worker/Cargo.toml -p splitbind-worker

FROM debian:13-slim AS worker
RUN groupadd --gid 10001 splitbind && useradd --uid 10001 --gid 10001 --no-create-home splitbind \
    && apt-get update && apt-get install -y --no-install-recommends ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=worker-build /build/services/worker/target/release/splitbind-worker /app/splitbind-worker
USER 10001:10001
ENTRYPOINT ["/app/splitbind-worker"]
```

```dockerfile
# infra/docker/web.Dockerfile
FROM node:24.18.0-alpine AS web-build
WORKDIR /build
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci
COPY apps/web/ apps/web/
RUN npm run build --workspace @splitbind/web

FROM caddy:2-alpine AS web
COPY --from=web-build /build/apps/web/dist /srv/web
COPY infra/caddy/Caddyfile /etc/caddy/Caddyfile
RUN chown -R 10001:10001 /srv/web /data /config
USER 10001:10001
```

```dockerfile
# infra/docker/ops.Dockerfile
FROM debian:13-slim AS ops
RUN groupadd --gid 10001 splitbind && useradd --uid 10001 --gid 10001 --no-create-home splitbind \
    && apt-get update && apt-get install -y --no-install-recommends age ca-certificates openssl postgresql-client \
    && rm -rf /var/lib/apt/lists/*
COPY infra/scripts/backup-metadata.sh infra/scripts/restore-drill.sh /app/
USER 10001:10001
ENTRYPOINT ["/bin/sh"]
```

```dockerfile
# research/python/Dockerfile
FROM python:3.11.9-slim AS research
WORKDIR /work
COPY research/python/pyproject.toml ./
COPY research/python/src ./src
RUN python -m pip install --no-cache-dir .
USER 10001:10001
ENTRYPOINT ["python", "-m", "splitbind_bench.runner"]
```

```dockerfile
# infra/docker/e2e.Dockerfile
FROM mcr.microsoft.com/playwright:v1.55.0-noble AS e2e
WORKDIR /work
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci
COPY apps/web/ apps/web/
COPY tests/e2e/ tests/e2e/
USER pwuser
```

In `compose.local.yaml`, retain each `image: splitbind-<name>:local` and add its matching `build.context: ../..` plus Dockerfile path for API, outbox, worker, web, research, and e2e. This makes `docker compose ... config` independent of P3 during P2, while `up --build` becomes available after this task.

Resolve and record the actual multi-architecture base-image digests during P5 image builds; the release manifest still references only the three built SplitBind images by immutable digest.

Apply this policy to every production service:

```yaml
services:
  caddy:
    user: "10001:10001"
    read_only: true
    mem_limit: 128m
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    tmpfs: ["/config:rw,nosuid,nodev,size=16m"]
    volumes: ["caddy_data:/data"]
    healthcheck: { test: ["CMD", "caddy", "version"], interval: 30s, timeout: 5s, retries: 3 }
  api:
    user: "10001:10001"
    read_only: true
    mem_limit: 512m
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    tmpfs: ["/tmp:rw,nosuid,nodev,size=64m"]
    healthcheck: { test: ["CMD", "python", "manage.py", "check", "--deploy"], interval: 30s, timeout: 10s, retries: 3 }
  outbox:
    user: "10001:10001"
    read_only: true
    mem_limit: 128m
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    tmpfs: ["/tmp:rw,nosuid,nodev,size=32m"]
    healthcheck: { test: ["CMD", "python", "manage.py", "check"], interval: 30s, timeout: 10s, retries: 3 }
  rabbitmq:
    user: "999:999"
    read_only: true
    mem_limit: 512m
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    tmpfs: ["/tmp:rw,nosuid,nodev,size=32m", "/var/run/rabbitmq:rw,nosuid,nodev,size=16m"]
    volumes: ["rabbitmq_data:/var/lib/rabbitmq"]
    healthcheck: { test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"], interval: 30s, timeout: 10s, retries: 5 }
  worker:
    user: "10001:10001"
    read_only: true
    mem_limit: 1536m
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    tmpfs: ["/tmp:rw,nosuid,nodev,size=2g"]
    healthcheck: { test: ["CMD", "/app/splitbind-worker", "health"], interval: 30s, timeout: 10s, retries: 3 }
volumes:
  caddy_data: {}
  rabbitmq_data: {}
```

`tests/security/test_container_runtime.py` starts the production images with synthetic configuration, inspects `.Config.User`, `.HostConfig.ReadonlyRootfs`, health, memory, capabilities, and writable paths, and fails when any value differs from the rendered contract.

- [ ] **Step 4: Prove static policy and built-image runtime behavior**

Run: `python -m unittest discover -s tests/security -p "test_production_compose.py" -v`

Run: `docker build --target api -f infra/docker/api.Dockerfile -t splitbind-api:local .`

Run: `docker build --target worker -f infra/docker/worker.Dockerfile -t splitbind-worker:local .`

Run: `docker build --target web -f infra/docker/web.Dockerfile -t splitbind-web:local .`

Run: `python -m unittest discover -s tests/security -p "test_container_runtime.py" -v`

Expected: PASS; all five services are non-root/read-only/healthy, only Caddy publishes 80/443, worker `/tmp` is capped at 2 GiB, and summed memory is 2.75 GiB.

- [ ] **Step 5: Commit**

```bash
git add infra/docker research/python/Dockerfile infra/compose/compose.local.yaml infra/compose/compose.production.yaml tests/security/test_production_compose.py tests/security/test_container_runtime.py
git commit -m "build: harden splitbind production containers"
```

### Task P4: Add bounded observability and release-capacity gates

**Owner:** Leader implements metric contracts; member builds presentation charts from exported data.

**Files:**

- Create: `contracts/observability/metrics-v1.json`
- Create: `services/api/splitbind/observability/metrics.py`
- Create: `services/api/splitbind/observability/middleware.py`
- Modify: `services/api/config/urls.py`
- Modify: `services/worker/crates/runtime/src/metrics.rs`
- Create: `infra/observability/prometheus.yaml`
- Create: `infra/observability/alerts.yaml`
- Modify: `infra/compose/compose.local.yaml`
- Test: `services/api/tests/observability/test_metrics.py`
- Test: `services/worker/crates/runtime/tests/metrics.rs`
- Test: `tests/platform/test_alert_contract.py`

**Interfaces:**

- API private endpoint `/metrics` emits Prometheus text but Caddy does not route it publicly.
- Stable names are `splitbind_http_requests_total`, `splitbind_http_request_duration_seconds`, `splitbind_queue_depth`, `splitbind_oldest_job_age_seconds`, `splitbind_jobs_total`, `splitbind_worker_page_seconds`, `splitbind_worker_peak_rss_bytes`, `splitbind_worker_temp_peak_bytes`, `splitbind_cleanup_failures_total`, `splitbind_sign_failures_total`, `splitbind_verify_failures_total`, `splitbind_r2_bytes_estimate`, and `splitbind_neon_storage_bytes_estimate`.
- Metric labels may include `method`, normalized `route`, `status_class`, `job_kind`, `outcome`, and `key_id`; they never include user, recipient, issuance, job, object key, filename, URL, or correlation identifiers.

- [ ] **Step 1: Write failing metric and alert-contract tests**

```python
# services/api/tests/observability/test_metrics.py
def test_metrics_are_private_and_have_bounded_labels(authenticated_client):
    authenticated_client.get("/health/live")
    response = authenticated_client.get("/metrics", HTTP_HOST="api")
    body = response.content.decode()
    assert response.status_code == 200
    assert "splitbind_http_requests_total" in body
    assert "correlation_id=" not in body
    assert "job_id=" not in body
```

```rust
// services/worker/crates/runtime/tests/metrics.rs
#[test]
fn cleanup_and_resource_metrics_use_stable_names() {
    let names = splitbind_runtime::metrics::metric_names();
    assert!(names.contains(&"splitbind_worker_peak_rss_bytes"));
    assert!(names.contains(&"splitbind_worker_temp_peak_bytes"));
    assert!(names.contains(&"splitbind_cleanup_failures_total"));
}
```

- [ ] **Step 2: Run tests and observe missing observability modules**

Run: `python -m pytest services/api/tests/observability/test_metrics.py -v`

Run: `cargo test --manifest-path services/worker/Cargo.toml -p splitbind-runtime --test metrics`

Expected: FAIL because the API metric registry and Rust stable-name registry do not exist.

- [ ] **Step 3: Implement the metric registry, private scrape, and exact alerts**

```python
# services/api/splitbind/observability/metrics.py
from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter("splitbind_http_requests", "HTTP responses", ["method", "route", "status_class"])
HTTP_DURATION = Histogram("splitbind_http_request_duration_seconds", "HTTP duration", ["method", "route"])
QUEUE_DEPTH = Gauge("splitbind_queue_depth", "Ready jobs", ["job_kind"])
OLDEST_JOB_AGE = Gauge("splitbind_oldest_job_age_seconds", "Oldest ready job age", ["job_kind"])
JOBS = Counter("splitbind_jobs", "Terminal job outcomes", ["job_kind", "outcome"])
R2_BYTES = Gauge("splitbind_r2_bytes_estimate", "Estimated object bytes")
NEON_BYTES = Gauge("splitbind_neon_storage_bytes_estimate", "Estimated database bytes")
```

Configure the local-only `observability` profile to scrape `api:8000/metrics` and the worker's private metric listener. Define alerts with these exact conditions: cleanup failures increase over 10 minutes; host disk exceeds 70% warning, 80% job-admission block, or 85% critical cleanup; oldest job age exceeds 300 seconds; signing key has less than 14 days validity; R2 or Neon usage exceeds 80% of the configured free-tier quota. Do not add Prometheus or Grafana to production Compose.

- [ ] **Step 4: Verify metrics, local profile, and alert thresholds**

Run: `python -m pytest services/api/tests/observability/test_metrics.py -v`

Run: `cargo test --manifest-path services/worker/Cargo.toml -p splitbind-runtime --test metrics`

Run: `python -m unittest discover -s tests/platform -p "test_alert_contract.py" -v`

Run: `docker compose --env-file infra/compose/config-test.env -f infra/compose/compose.local.yaml --profile observability config --quiet`

Expected: PASS; `/metrics` is reachable only on the private Compose network, alert tests observe 70/80/85 disk thresholds, and no high-cardinality/private identifiers are labels.

- [ ] **Step 5: Commit**

```bash
git add contracts/observability services/api/splitbind/observability services/api/config/urls.py services/api/tests/observability services/worker/crates/runtime/src/metrics.rs services/worker/crates/runtime/tests/metrics.rs infra/observability infra/compose/compose.local.yaml tests/platform/test_alert_contract.py
git commit -m "feat(observability): add bounded release metrics and alerts"
```

### Task P5: Enforce CI, security, SBOM, and multi-architecture gates

**Owner:** Leader owns release gates; member owns frontend and benchmark artifact checks.

**Files:**

- Create: `.github/workflows/ci.yaml`
- Create: `.github/workflows/images.yaml`
- Create: `.github/workflows/benchmark.yaml`
- Delete after full CI passes: `.github/workflows/smoke.yaml`
- Create: `docker-bake.hcl`
- Create: `deny.toml`
- Create: `.gitleaks.toml`
- Create: `infra/scripts/ci.ps1`
- Test: `tests/platform/test_ci_contract.py`

**Interfaces:**

- Pull-request jobs are exactly `api`, `web`, `rust`, `contracts`, `integration`, and `security`; all run with read-only repository permissions.
- Image validation builds `api`, `worker`, and `web` for `linux/amd64` and `linux/arm64`, scans the resulting OCI layouts, and exports CycloneDX SBOMs retained for one day.
- Full research benchmarks run only by `workflow_dispatch` or the weekly schedule and use the versioned synthetic corpus.

- [ ] **Step 1: Write the failing workflow-contract test**

```python
# tests/platform/test_ci_contract.py
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class CiContractTest(unittest.TestCase):
    def test_ci_and_image_gates_are_declared(self):
        ci = (ROOT / ".github/workflows/ci.yaml").read_text(encoding="utf-8")
        images = (ROOT / ".github/workflows/images.yaml").read_text(encoding="utf-8")
        benchmark = (ROOT / ".github/workflows/benchmark.yaml").read_text(encoding="utf-8")
        for job in ("api:", "web:", "rust:", "contracts:", "integration:", "security:"):
            self.assertIn(job, ci)
        for gate in ("pip-audit", "npm audit", "cargo deny", "gitleaks"):
            self.assertIn(gate, ci)
        self.assertIn("linux/amd64,linux/arm64", images)
        self.assertIn("retention-days: 1", images)
        self.assertIn("workflow_dispatch:", benchmark)
        self.assertNotIn("pull_request:", benchmark)
```

- [ ] **Step 2: Run the test and observe missing workflows**

Run: `python -m unittest discover -s tests/platform -p "test_ci_contract.py" -v`

Expected: FAIL with `FileNotFoundError` for `.github/workflows/ci.yaml`.

- [ ] **Step 3: Implement exact CI jobs and local equivalents**

Create `.github/workflows/ci.yaml` with `permissions: {contents: read}`, pull-request and main-branch triggers, and these commands:

```yaml
jobs:
  api:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11", cache: pip }
      - run: python -m pip install -e "services/api[dev]"
      - run: python -m ruff check services/api
      - run: python -m mypy services/api
      - run: python -m pytest services/api/tests -v
  web:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version-file: .nvmrc, cache: npm }
      - run: npm ci
      - run: npm run format:check --workspace @splitbind/web
      - run: npm run lint --workspace @splitbind/web
      - run: npm run typecheck --workspace @splitbind/web
      - run: npm test --workspace @splitbind/web
  rust:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - run: rustup show
      - run: cargo fmt --manifest-path services/worker/Cargo.toml --check
      - run: cargo clippy --manifest-path services/worker/Cargo.toml --workspace --all-targets -- -D warnings
      - run: cargo test --manifest-path services/worker/Cargo.toml --workspace
  contracts:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - uses: actions/setup-node@v4
        with: { node-version-file: .nvmrc, cache: npm }
      - run: python -m pip install -e "services/api[dev]"
      - run: npm ci
      - run: python services/api/manage.py spectacular --file contracts/openapi/schema.json --validate
      - run: npm run generate:api
      - run: git diff --exit-code contracts/openapi/schema.json apps/web/src/api/generated
  integration:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - run: docker compose --env-file infra/compose/config-test.env -f infra/compose/compose.local.yaml --profile core up --build --abort-on-container-exit --exit-code-from e2e e2e
      - if: always()
        run: docker compose --env-file infra/compose/config-test.env -f infra/compose/compose.local.yaml --profile core down --volumes --remove-orphans
  security:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: gitleaks/gitleaks-action@v2
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - uses: actions/setup-node@v4
        with: { node-version-file: .nvmrc, cache: npm }
      - run: python -m pip install pip-audit
      - run: pip-audit --strict
      - run: npm ci && npm audit --audit-level=high
      - run: cargo install cargo-deny --locked && cargo deny --manifest-path services/worker/Cargo.toml check advisories bans licenses sources
```

Create `images.yaml` with QEMU and Buildx setup, `docker/build-push-action` build steps for all three targets, `platforms: linux/amd64,linux/arm64`, `push: false`, image scans that fail on unfixed critical/high findings, and one CycloneDX JSON SBOM per image uploaded with `retention-days: 1`. Create `benchmark.yaml` with only `workflow_dispatch` and weekly `schedule` triggers and the exact versioned profile, corpus, matrix, and seed shown below.

```yaml
# .github/workflows/images.yaml (job body)
permissions: { contents: read }
jobs:
  build:
    runs-on: ubuntu-24.04
    strategy:
      fail-fast: false
      matrix: { target: [api, worker, web] }
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-qemu-action@v3
      - uses: docker/setup-buildx-action@v3
      - uses: aquasecurity/setup-trivy@v0.2.3
      - uses: anchore/sbom-action/download-syft@v0
      - uses: docker/build-push-action@v6
        with:
          context: .
          target: ${{ matrix.target }}
          platforms: linux/amd64,linux/arm64
          push: false
          outputs: type=oci,dest=/tmp/${{ matrix.target }}.tar
      - run: trivy image --input /tmp/${{ matrix.target }}.tar --ignore-unfixed --severity HIGH,CRITICAL --exit-code 1
      - run: syft oci-archive:/tmp/${{ matrix.target }}.tar -o cyclonedx-json=sbom-${{ matrix.target }}.json
      - uses: actions/upload-artifact@v4
        with:
          name: sbom-${{ matrix.target }}
          path: sbom-${{ matrix.target }}.json
          retention-days: 1
```

```yaml
# .github/workflows/benchmark.yaml
name: benchmark
on:
  workflow_dispatch:
  schedule:
    - cron: "0 3 * * 0"
permissions: { contents: read }
jobs:
  benchmark:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11", cache: pip }
      - run: python -m pip install -e "research/python[dev]"
      - run: python research/python/scripts/run_benchmark.py --profile contracts/algorithm/fingerprint-profile.v1.json --corpus fixtures/corpus/corpus-manifest.v1.json --matrix contracts/algorithm/attack-matrix.v1.json --seed 20260827 --output artifacts/benchmark
      - uses: actions/upload-artifact@v4
        with: { name: benchmark, path: artifacts/benchmark, retention-days: 1 }
```

`infra/scripts/ci.ps1` runs the same format, lint, type, unit, contract, Compose config, and platform/security test commands in fail-fast order. It does not run the full attack benchmark unless called with `-IncludeBenchmark`.

```powershell
param([switch]$IncludeBenchmark)
$ErrorActionPreference = "Stop"
python -m ruff check services/api research/python
python -m mypy services/api
python -m pytest services/api/tests research/python/tests
npm run format:check
npm run lint
npm run typecheck
npm test
cargo fmt --manifest-path services/worker/Cargo.toml --check
cargo clippy --manifest-path services/worker/Cargo.toml --workspace --all-targets -- -D warnings
cargo test --manifest-path services/worker/Cargo.toml --workspace
python services/api/manage.py spectacular --file contracts/openapi/schema.json --validate
npm run generate:api
git diff --exit-code contracts/openapi/schema.json apps/web/src/api/generated
python -m unittest discover -s tests/platform -p "test_*.py" -v
python -m unittest discover -s tests/security -p "test_*.py" -v
if ($IncludeBenchmark) {
    python research/python/scripts/run_benchmark.py --profile contracts/algorithm/fingerprint-profile.v1.json --corpus fixtures/corpus/corpus-manifest.v1.json --matrix contracts/algorithm/attack-matrix.v1.json --seed 20260827 --output artifacts/benchmark-local
}
```

- [ ] **Step 4: Verify local gates and workflow policy**

Run: `python -m unittest discover -s tests/platform -p "test_ci_contract.py" -v`

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File infra/scripts/ci.ps1`

Run: `docker buildx bake --file docker-bake.hcl --print`

Expected: PASS; generated contracts have no drift, security commands return zero, and Bake reports all three targets with both required platforms.

- [ ] **Step 5: Commit**

```bash
git add -A .github/workflows docker-bake.hcl deny.toml .gitleaks.toml infra/scripts/ci.ps1 tests/platform/test_ci_contract.py
git commit -m "ci: enforce splitbind release and multiarch gates"
```

### Task P6: Implement encrypted metadata backup and isolated restore drills

**Owner:** Leader; member records the drill checklist and timestamps without copying backup contents.

**Files:**

- Create: `infra/scripts/backup-metadata.sh`
- Create: `infra/scripts/restore-drill.sh`
- Create: `services/api/splitbind/retention/management/commands/verify_restore.py`
- Create: `docs/runbooks/backup-and-restore.md`
- Test: `tests/platform/test_backup_scripts.py`
- Test: `tests/integration/test_backup_restore.py`

**Interfaces:**

- `backup-metadata.sh <absolute-output.age>` requires `DATABASE_URL` and `BACKUP_AGE_RECIPIENT`, emits `<output>.sha256`, and deletes its exact plaintext temporary file on every exit.
- `restore-drill.sh <absolute-backup.age> <absolute-age-identity>` requires `RESTORE_DATABASE_URL` whose database name ends `_restore_drill`; it never accepts the production database URL.
- A passing drill writes only status, schema version, row-count ranges, backup digest, start/end UTC, and tool versions to `artifacts/recovery/restore-evidence.json`.

- [ ] **Step 1: Write failing safety-contract tests**

```python
# tests/platform/test_backup_scripts.py
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class BackupScriptTest(unittest.TestCase):
    def test_backup_is_encrypted_and_restore_is_nonproduction_only(self):
        backup = (ROOT / "infra/scripts/backup-metadata.sh").read_text(encoding="utf-8")
        restore = (ROOT / "infra/scripts/restore-drill.sh").read_text(encoding="utf-8")
        self.assertIn("pg_dump --format=custom --no-owner", backup)
        self.assertIn("age -r", backup)
        self.assertIn("trap 'rm -f -- \"$plain\"' EXIT", backup)
        self.assertIn("_restore_drill", restore)
        self.assertIn("pg_restore --exit-on-error --no-owner", restore)
        self.assertNotIn("R2_BACKUP", backup + restore)
```

- [ ] **Step 2: Run the test and observe missing scripts**

Run: `python -m unittest discover -s tests/platform -p "test_backup_scripts.py" -v`

Expected: FAIL with `FileNotFoundError` for `backup-metadata.sh`.

- [ ] **Step 3: Implement fail-closed backup and restore scripts**

```sh
#!/bin/sh
# infra/scripts/backup-metadata.sh
set -eu
[ "$#" -eq 1 ] || { echo "usage: backup-metadata.sh ABSOLUTE_OUTPUT.age" >&2; exit 64; }
case "$1" in /*.age) output="$1" ;; *) echo "output must be an absolute .age path" >&2; exit 64 ;; esac
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_AGE_RECIPIENT:?BACKUP_AGE_RECIPIENT is required}"
[ -d "$(dirname -- "$output")" ] || { echo "output parent does not exist" >&2; exit 66; }
umask 077
plain="$(mktemp "${TMPDIR:-/tmp}/splitbind-pg.XXXXXX")"
encrypted="${output}.partial"
trap 'rm -f -- "$plain"' EXIT
trap 'rm -f -- "$encrypted"' HUP INT TERM
pg_dump --format=custom --no-owner --dbname="$DATABASE_URL" --file="$plain"
age -r "$BACKUP_AGE_RECIPIENT" -o "$encrypted" "$plain"
mv -- "$encrypted" "$output"
sha256sum "$output" > "${output}.sha256"
```

```sh
#!/bin/sh
# infra/scripts/restore-drill.sh
set -eu
[ "$#" -eq 2 ] || { echo "usage: restore-drill.sh ABSOLUTE_BACKUP.age ABSOLUTE_IDENTITY" >&2; exit 64; }
: "${RESTORE_DATABASE_URL:?RESTORE_DATABASE_URL is required}"
: "${RESTORE_EVIDENCE_PATH:?RESTORE_EVIDENCE_PATH is required}"
case "$RESTORE_EVIDENCE_PATH" in /*.json) ;; *) echo "evidence path must be absolute JSON" >&2; exit 64 ;; esac
db_name="$(printf '%s' "$RESTORE_DATABASE_URL" | sed -E 's#^.*/([^/?]+).*$#\1#')"
case "$db_name" in *_restore_drill) ;; *) echo "restore target must end _restore_drill" >&2; exit 65 ;; esac
plain="$(mktemp "${TMPDIR:-/tmp}/splitbind-restore.XXXXXX")"
trap 'rm -f -- "$plain"' EXIT
age -d -i "$2" -o "$plain" "$1"
pg_restore --list "$plain" >/dev/null
pg_restore --exit-on-error --no-owner --dbname="$RESTORE_DATABASE_URL" "$plain"
python services/api/manage.py verify_restore --database-url "$RESTORE_DATABASE_URL" --evidence "$RESTORE_EVIDENCE_PATH"
```

```python
# core of services/api/splitbind/retention/management/commands/verify_restore.py
def verify_restore(database_url: str) -> dict[str, object]:
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM django_migrations")
            migration_count = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM documents_manifest")
            manifest_count = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM audit_auditevent")
            audit_count = cursor.fetchone()[0]
            cursor.execute("""
                SELECT count(*) FROM documents_manifest m
                LEFT JOIN documents_signingkey k ON k.key_id = m.key_id
                WHERE k.key_id IS NULL
            """)
            orphaned_key_count = cursor.fetchone()[0]
    if migration_count < 1 or orphaned_key_count != 0:
        raise CommandError("RESTORE_INTEGRITY")
    return {
        "schema_version": 1,
        "status": "verified",
        "migration_count": migration_count,
        "manifest_count": manifest_count,
        "audit_count": audit_count,
    }
```

The command adds backup SHA-256, UTC start/end, and tool versions before atomically writing the private evidence file. It never records row contents or claims expired R2 objects can be recovered. The runbook requires an encrypted private-key backup stored off-host and tests its restore with a disposable test signing key; production private material is never printed or included in drill evidence.

- [ ] **Step 4: Run a complete local backup/restore drill**

Run: `python -m unittest discover -s tests/platform -p "test_backup_scripts.py" -v`

Run: `python -m pytest tests/integration/test_backup_restore.py -v`

Expected: PASS; the restored scratch database passes `verify_restore`, encrypted backup digest matches, no plaintext dump remains, and the production database is unchanged.

- [ ] **Step 5: Commit**

```bash
git add infra/scripts/backup-metadata.sh infra/scripts/restore-drill.sh services/api/splitbind/retention/management/commands/verify_restore.py docs/runbooks/backup-and-restore.md tests/platform/test_backup_scripts.py tests/integration/test_backup_restore.py
git commit -m "feat(recovery): add encrypted metadata restore drill"
```

### Task P7: Implement digest releases, automatic rollback, and a pull-free offline demo

**Owner:** Leader owns deploy/rollback; member owns offline-demo rehearsal and backup video.

**Files:**

- Create: `infra/release/release.schema.json`
- Create: `infra/release/offline-images.txt`
- Create: `infra/scripts/validate-release.py`
- Create: `infra/scripts/deploy.sh`
- Create: `infra/scripts/rollback.sh`
- Create: `infra/scripts/offline-demo.ps1`
- Create: `docs/runbooks/release-and-rollback.md`
- Test: `tests/platform/test_release_manifest.py`
- Test: `tests/integration/test_release_rollback.py`
- Test: `tests/e2e/test_offline_demo.py`

**Interfaces:**

- `validate-release.py RELEASE.json [--env-output ABSOLUTE_PATH]` rejects tags, mutable references, non-40-character commits, unknown fields, and missing rollback migration IDs; the optional output contains only image digest variables and migration identifiers.
- `deploy.sh RELEASE.json EVIDENCE_DIR` requires `e2e.ok`, `security.ok`, `multiarch.ok`, `backup-restore.ok`, and `rollback-drill.ok`; it saves the prior release before applying migrations and invokes `rollback.sh` on failed readiness.
- `offline-demo.ps1 -Archive <absolute tar> -Release <absolute json>` loads exact digests, starts `compose.offline.yaml` with `pull_policy: never` and an internal network, and waits for local issuance/verification smoke success.

- [ ] **Step 1: Write failing release and offline-policy tests**

```python
# tests/platform/test_release_manifest.py
from pathlib import Path
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def test_release_requires_three_immutable_digests(tmp_path):
    release = {
        "schema_version": 1,
        "git_commit": "a" * 40,
        "migration_id": "documents.0004_manifest",
        "rollback_migration_id": "documents.0003_document",
        "api_image": "ghcr.io/qivarnq3g/splitbind-api@sha256:" + "1" * 64,
        "worker_image": "ghcr.io/qivarnq3g/splitbind-worker@sha256:" + "2" * 64,
        "web_image": "ghcr.io/qivarnq3g/splitbind-web@sha256:" + "3" * 64,
        "created_at": "2026-09-13T12:00:00Z",
    }
    path = tmp_path / "release.json"
    path.write_text(json.dumps(release), encoding="utf-8")
    result = subprocess.run(["python", str(ROOT / "infra/scripts/validate-release.py"), str(path)])
    assert result.returncode == 0


def test_offline_compose_cannot_pull_or_reach_external_network():
    text = (ROOT / "infra/compose/compose.offline.yaml").read_text(encoding="utf-8")
    assert "pull_policy: never" in text
    assert "internal: true" in text
```

- [ ] **Step 2: Run tests and observe missing release tooling**

Run: `python -m pytest tests/platform/test_release_manifest.py -v`

Expected: FAIL because `validate-release.py` and the immutable offline manifest are absent.

- [ ] **Step 3: Implement the schema validator and fail-safe deploy state machine**

`release.schema.json` sets `additionalProperties: false`, requires all eight fields in the test above, and uses `^.+@sha256:[0-9a-f]{64}$` for each image. `validate-release.py` validates against that schema and exits `65` on any mutable reference.

```python
# core of infra/scripts/validate-release.py
IMAGE_PATTERN = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
EXPECTED_FIELDS = {
    "schema_version", "git_commit", "migration_id", "rollback_migration_id",
    "api_image", "worker_image", "web_image", "created_at",
}


def validate_release(value: dict) -> None:
    if set(value) != EXPECTED_FIELDS or value.get("schema_version") != 1:
        raise ValueError("RELEASE_SCHEMA")
    if re.fullmatch(r"[0-9a-f]{40}", value["git_commit"]) is None:
        raise ValueError("RELEASE_COMMIT")
    for field in ("api_image", "worker_image", "web_image"):
        if IMAGE_PATTERN.fullmatch(value[field]) is None:
            raise ValueError("MUTABLE_IMAGE")
```

```sh
#!/bin/sh
# infra/scripts/deploy.sh
set -eu
[ "$#" -eq 2 ] || { echo "usage: deploy.sh RELEASE.json EVIDENCE_DIR" >&2; exit 64; }
release="$1"; evidence="$2"
python infra/scripts/validate-release.py "$release"
for gate in e2e.ok security.ok multiarch.ok backup-restore.ok rollback-drill.ok; do
    [ -f "$evidence/$gate" ] || { echo "MISSING_GATE:$gate" >&2; exit 65; }
done
state_dir="/var/lib/splitbind/releases"
install -d -m 0700 "$state_dir"
[ ! -f "$state_dir/current.json" ] || cp "$state_dir/current.json" "$state_dir/previous.json"
install -m 0600 "$release" "$state_dir/candidate.json"
python infra/scripts/validate-release.py "$release" --env-output /run/splitbind/release.env
docker compose --env-file /run/splitbind/release.env -f infra/compose/compose.production.yaml pull
docker compose --env-file /run/splitbind/release.env -f infra/compose/compose.production.yaml run --rm api python manage.py migrate --noinput
docker compose --env-file /run/splitbind/release.env -f infra/compose/compose.production.yaml up -d --remove-orphans
if ! curl --fail --silent --show-error --retry 12 --retry-delay 5 http://127.0.0.1:8080/health/ready >/dev/null; then
    infra/scripts/rollback.sh "$state_dir/previous.json"
    exit 70
fi
mv "$state_dir/candidate.json" "$state_dir/current.json"
```

```sh
#!/bin/sh
# infra/scripts/rollback.sh
set -eu
[ "$#" -eq 1 ] || { echo "usage: rollback.sh PREVIOUS_RELEASE.json" >&2; exit 64; }
previous="$1"
python infra/scripts/validate-release.py "$previous" --env-output /run/splitbind/release.env
rollback_target="$(python -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["rollback_migration_id"])' "$previous")"
rollback_app="${rollback_target%%.*}"
rollback_name="${rollback_target#*.}"
docker compose --env-file /run/splitbind/release.env -f infra/compose/compose.production.yaml run --rm api python manage.py migrate --noinput "$rollback_app" "$rollback_name"
docker compose --env-file /run/splitbind/release.env -f infra/compose/compose.production.yaml up -d --remove-orphans
curl --fail --silent --show-error --retry 12 --retry-delay 5 http://127.0.0.1:8080/health/ready >/dev/null
```

The runbook marks a release ineligible when any migration lacks a tested reverse target. Rollback never deletes the failed release, backup, logs, or database evidence needed for diagnosis.

```powershell
# core of infra/scripts/offline-demo.ps1
param(
    [Parameter(Mandatory)][string]$Archive,
    [Parameter(Mandatory)][string]$Release
)
$ErrorActionPreference = "Stop"
$archivePath = (Resolve-Path -LiteralPath $Archive).Path
$releasePath = (Resolve-Path -LiteralPath $Release).Path
python infra/scripts/validate-release.py $releasePath
docker load --input $archivePath | Out-Null
$artifactRoot = Join-Path (Get-Location).Path "artifacts"
$keyRoot = Join-Path $artifactRoot "offline/keys"
New-Item -ItemType Directory -Force -Path $keyRoot | Out-Null
docker run --rm --volume "${keyRoot}:/keys" splitbind-ops:local sh -c 'umask 077; openssl genpkey -algorithm Ed25519 -out /keys/manifest.pk8; openssl rand -out /keys/fingerprint.bin 32; openssl rand -out /keys/integrity.bin 32'
docker compose --env-file infra/compose/offline.env -f infra/compose/compose.offline.yaml up -d --wait
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:8080/health/ready" | Out-Null
    python -m pytest tests/e2e/test_offline_demo.py -v
} catch {
    docker compose --env-file infra/compose/offline.env -f infra/compose/compose.offline.yaml logs --no-color
    throw
}
```

- [ ] **Step 4: Observe release rollback and offline-demo postconditions**

Run: `python -m pytest tests/platform/test_release_manifest.py tests/integration/test_release_rollback.py -v`

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File infra/scripts/offline-demo.ps1 -Archive artifacts/offline/splitbind-images.tar -Release artifacts/release/release.json`

Run: `python -m pytest tests/e2e/test_offline_demo.py -v`

Expected: PASS; an injected readiness failure restores the previous digests and migration state, while the offline stack completes one issuance and one verification with external egress blocked.

- [ ] **Step 5: Commit**

```bash
git add infra/release infra/scripts/validate-release.py infra/scripts/deploy.sh infra/scripts/rollback.sh infra/scripts/offline-demo.ps1 docs/runbooks/release-and-rollback.md tests/platform/test_release_manifest.py tests/integration/test_release_rollback.py tests/e2e/test_offline_demo.py
git commit -m "feat(release): add digest rollback and offline demo"
```

### Task P8: Configure and verify Neon, R2, and Key Vault production boundaries

**Owner:** Leader only; the member reviews sanitized policy evidence. External service creation or mutation requires explicit operator authorization at execution time.

**Files:**

- Create: `infra/production/managed-services-policy.json`
- Create: `infra/production/neon-roles.sql`
- Create: `infra/production/key-vault-contract.json`
- Create: `infra/scripts/managed_services_preflight.py`
- Create: `fixtures/platform/managed-services-valid.json`
- Create: `docs/runbooks/managed-services.md`
- Test: `tests/platform/test_managed_services_policy.py`

**Interfaces:**

- The normalized storage policy fixes bucket scope, R2 lifecycle for orphan prefix `uploads/orphan/` at `24` hours, application cleanup for issuance inputs at `7` days and outputs at `30` days, verification-input cleanup `24` hours after its result, server-side encryption, and CORS origin `https://splitbind.qivarn.id.vn`.
- Neon roles are `splitbind_owner` for migrations only, `splitbind_app` for Django/outbox DML, `splitbind_worker` for cancellation/manifest reads, and `splitbind_backup` for metadata dumps. Runtime containers never receive owner or backup credentials.
- A dedicated SplitBind Key Vault contains separate API environment, worker environment, Ed25519 signing, fingerprint, and integrity secrets. The VM system identity receives `Key Vault Secrets User` only at that vault scope; Django still receives no private algorithm/signing secret.
- `managed_services_preflight.py --observation JSON --output JSON` compares sanitized provider observations to repository policy and emits only stable blockers, service endpoints without credentials, quota/usage values, and key IDs/expiry metadata.

- [ ] **Step 1: Write failing policy and least-privilege tests**

```python
# tests/platform/test_managed_services_policy.py
import json
from pathlib import Path

from infra.scripts.managed_services_preflight import validate_observation

ROOT = Path(__file__).resolve().parents[2]


def test_policy_freezes_retention_origin_and_role_split():
    policy = json.loads((ROOT / "infra/production/managed-services-policy.json").read_text(encoding="utf-8"))
    assert policy["r2"]["orphan"] == {"prefix": "uploads/orphan/", "expire_hours": 24}
    assert policy["r2"]["cors_origins"] == ["https://splitbind.qivarn.id.vn"]
    assert policy["neon"]["runtime_roles"] == ["splitbind_app", "splitbind_worker"]
    assert policy["neon"]["migration_role"] == "splitbind_owner"
    assert policy["neon"]["backup_role"] == "splitbind_backup"


def test_valid_sanitized_observation_has_no_blockers():
    observation = json.loads((ROOT / "fixtures/platform/managed-services-valid.json").read_text(encoding="utf-8"))
    assert validate_observation(observation) == []
```

- [ ] **Step 2: Run tests and observe missing production policy**

Run: `python -m pytest tests/platform/test_managed_services_policy.py -v`

Expected: FAIL with `ModuleNotFoundError` or `FileNotFoundError` for the policy/preflight files.

- [ ] **Step 3: Implement normalized policy, SQL roles, and fail-closed validation**

```json
{
  "schema_version": 1,
  "r2": {
    "bucket_purpose": "splitbind-production-objects",
    "server_side_encryption": true,
    "cors_origins": ["https://splitbind.qivarn.id.vn"],
    "cors_methods": ["GET", "HEAD", "PUT"],
    "orphan": {"prefix": "uploads/orphan/", "expire_hours": 24},
    "issuance_input": {"prefix": "inputs/issuance/", "application_retention_hours": 168},
    "issuance_output": {"prefix": "outputs/issuance/", "application_retention_hours": 720},
    "verification_input": {"prefix": "inputs/verification/", "application_retention_after_result_hours": 24}
  },
  "neon": {
    "tls_required": true,
    "migration_role": "splitbind_owner",
    "runtime_roles": ["splitbind_app", "splitbind_worker"],
    "backup_role": "splitbind_backup"
  },
  "key_vault": {
    "dedicated_vault": true,
    "soft_delete": true,
    "purge_protection": true,
    "vm_role": "Key Vault Secrets User",
    "private_secret_consumers": ["worker"]
  }
}
```

```sql
-- infra/production/neon-roles.sql, executed by the Neon project owner after
-- passwords are supplied through provider controls rather than this file.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO splitbind_app, splitbind_worker, splitbind_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE splitbind_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO splitbind_app;
ALTER DEFAULT PRIVILEGES FOR ROLE splitbind_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO splitbind_app;
ALTER DEFAULT PRIVILEGES FOR ROLE splitbind_owner IN SCHEMA public
    GRANT SELECT ON TABLES TO splitbind_worker, splitbind_backup;
```

```python
# invariant core in infra/scripts/managed_services_preflight.py
def validate_observation(value: dict) -> list[str]:
    blockers: list[str] = []
    r2 = value.get("r2", {})
    if r2.get("cors_origins") != ["https://splitbind.qivarn.id.vn"]:
        blockers.append("R2_CORS")
    if r2.get("orphan_expire_hours") != 24 or r2.get("orphan_prefix") != "uploads/orphan/":
        blockers.append("R2_LIFECYCLE")
    if not r2.get("server_side_encryption"):
        blockers.append("R2_ENCRYPTION")
    neon = value.get("neon", {})
    if not neon.get("tls_in_use"):
        blockers.append("NEON_TLS")
    if sorted(neon.get("roles", [])) != ["splitbind_app", "splitbind_backup", "splitbind_owner", "splitbind_worker"]:
        blockers.append("NEON_ROLES")
    vault = value.get("key_vault", {})
    if not vault.get("dedicated") or not vault.get("soft_delete") or not vault.get("purge_protection"):
        blockers.append("KEY_VAULT_POLICY")
    if vault.get("vm_role") != "Key Vault Secrets User" or vault.get("role_scope") != "vault":
        blockers.append("KEY_VAULT_RBAC")
    return blockers
```

The runbook creates provider resources only after authorization, generates separate credentials outside Git, applies the normalized retention/CORS policy, runs Django migrations with `splitbind_owner`, applies runtime grants, and records secret metadata without values. R2 API credentials are separate and bucket-scoped for API and worker. The verification upload/download probes use one task-owned synthetic object and delete that exact key after checksum verification; failure to delete remains a reported cleanup blocker.

- [ ] **Step 4: Verify sanitized fixtures, then provider observations**

Run: `python -m pytest tests/platform/test_managed_services_policy.py -v`

Run after authorized provider configuration: `python infra/scripts/managed_services_preflight.py --observation artifacts/deployment/managed-services-observed.private.json --output artifacts/deployment/managed-services-sanitized.json`

Expected: fixture tests PASS. Real preflight exits zero only when TLS, roles/grants, R2 lifecycle/CORS/encryption, scoped credentials, Key Vault protection/RBAC, key metadata, quota headroom, and the synthetic object cleanup postcondition are observed.

- [ ] **Step 5: Commit policy and runbook; keep provider evidence private**

```bash
git add infra/production infra/scripts/managed_services_preflight.py fixtures/platform/managed-services-valid.json docs/runbooks/managed-services.md tests/platform/test_managed_services_policy.py
git commit -m "feat(ops): define managed production service gates"
```

### Task P9: Audit the existing Azure host and enforce budget-before-start

**Owner:** Leader only. External Azure mutation requires explicit operator authorization at execution time.

**Files:**

- Create: `infra/scripts/azure_preflight.py`
- Create: `fixtures/platform/azure-valid-cold.json`
- Create: `fixtures/platform/azure-valid-running.json`
- Create: `docs/runbooks/azure-and-dns-cutover.md`
- Test: `tests/platform/test_azure_preflight.py`

**Interfaces:**

- `python infra/scripts/azure_preflight.py cold --output <absolute-json>` requires an enabled USD 100 annual budget with Actual thresholds 25/50/75/90, expected resource identity, a deallocated VM, static Standard IPv4, Trusted Launch, Secure Boot, vTPM, system identity, 32 GiB Standard SSD, and configured NSG rules.
- `python infra/scripts/azure_preflight.py running --output <absolute-json>` additionally requires the running power state, effective NSG rules, SSH `/32`, and at least 8 GiB available OS-disk space.
- Stable blockers include `BUDGET_MISSING`, `BUDGET_THRESHOLDS`, `VM_DUPLICATE`, `VM_SHAPE`, `VM_NOT_DEALLOCATED`, `IDENTITY`, `TRUSTED_LAUNCH`, `DISK`, `PUBLIC_IP`, `NSG_PUBLIC_PORT`, `SSH_SCOPE`, and `DISK_HEADROOM`.

- [ ] **Step 1: Write failing invariant tests with sanitized fixtures**

```python
# tests/platform/test_azure_preflight.py
from copy import deepcopy
import json
from pathlib import Path

from infra.scripts.azure_preflight import validate_state

ROOT = Path(__file__).resolve().parents[2]


def valid_cold():
    return json.loads((ROOT / "fixtures/platform/azure-valid-cold.json").read_text(encoding="utf-8"))


def test_valid_cold_state_has_no_blocker():
    assert validate_state(valid_cold(), phase="cold") == []


def test_missing_budget_and_public_rabbitmq_fail_closed():
    state = deepcopy(valid_cold())
    state["budget"] = None
    state["nsg_rules"].append({"port": "5672", "source": "Internet", "access": "Allow"})
    assert validate_state(state, phase="cold") == ["BUDGET_MISSING", "NSG_PUBLIC_PORT"]
```

- [ ] **Step 2: Run tests and observe the missing audit module**

Run: `python -m pytest tests/platform/test_azure_preflight.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'infra.scripts.azure_preflight'`.

- [ ] **Step 3: Implement exact invariant validation and budget creation gate**

```python
# invariant core in infra/scripts/azure_preflight.py
EXPECTED = {
    "resource_group": "rg-splitbind-prod",
    "location": "koreacentral",
    "vm_name": "vm-splitbind-prod",
    "sku": "Standard_B2ls_v2",
}


def validate_state(state: dict, phase: str) -> list[str]:
    blockers: list[str] = []
    budget = state.get("budget")
    if budget is None:
        blockers.append("BUDGET_MISSING")
    elif budget.get("amount") != 100 or sorted(budget.get("actual_thresholds", [])) != [25, 50, 75, 90]:
        blockers.append("BUDGET_THRESHOLDS")
    if state.get("vm_count") != 1:
        blockers.append("VM_DUPLICATE")
    if any(state.get(key) != value for key, value in EXPECTED.items()):
        blockers.append("VM_SHAPE")
    if state.get("identity_type") != "SystemAssigned":
        blockers.append("IDENTITY")
    if not all((state.get("trusted_launch"), state.get("secure_boot"), state.get("vtpm"))):
        blockers.append("TRUSTED_LAUNCH")
    if state.get("disk_size_gib") != 32 or state.get("disk_sku") != "StandardSSD_LRS":
        blockers.append("DISK")
    if state.get("public_ip_sku") != "Standard" or state.get("public_ip_allocation") != "Static":
        blockers.append("PUBLIC_IP")
    if phase == "cold" and state.get("power_state") != "VM deallocated":
        blockers.append("VM_NOT_DEALLOCATED")
    if phase == "running" and state.get("power_state") != "VM running":
        blockers.append("VM_SHAPE")
    if phase == "running" and int(state.get("available_disk_bytes", 0)) < 8 * 1024**3:
        blockers.append("DISK_HEADROOM")
    rule_field = "effective_nsg_rules" if phase == "running" else "nsg_rules"
    rules = state.get(rule_field, [])
    allowed_public = {("80", "Internet"), ("443", "Internet")}
    public = {(str(rule["port"]), rule["source"]) for rule in rules
              if rule.get("access") == "Allow" and rule.get("source") == "Internet"}
    if public != allowed_public:
        blockers.append("NSG_PUBLIC_PORT")
    ssh = [rule for rule in rules if str(rule.get("port")) == "22" and rule.get("access") == "Allow"]
    if len(ssh) != 1 or not ssh[0].get("source", "").endswith("/32"):
        blockers.append("SSH_SCOPE")
    return blockers
```

The collector invokes `az account show`, the Consumption budgets REST endpoint, `az vm list/show/get-instance-view`, `az network public-ip show`, `az network nic show/list-effective-nsg`, and `az disk show`, always using the fixed resource names above. It redacts subscription ID, tenant ID, public IP, administrator source IP, and email from the JSON evidence. In running phase it obtains available bytes with SSH `df -B1 --output=avail /` and stores only the integer.

If the cold audit reports `BUDGET_MISSING`, stop. After explicit operator authorization, create `splitbind-credit-budget` for `2026-08-01T00:00:00Z` through `2027-08-01T00:00:00Z`, amount USD 100, time grain `Annually`, with enabled Actual notifications `Actual_GreaterThan_25`, `50`, `75`, and `90` sent to the process-local `BUDGET_CONTACT_EMAIL`. Re-run the REST read and cold audit; do not start the VM if any blocker remains.

```powershell
$ErrorActionPreference = "Stop"
$subscriptionId = az account show --query id --output tsv
$contact = $env:BUDGET_CONTACT_EMAIL
if ([string]::IsNullOrWhiteSpace($contact)) { throw "BUDGET_CONTACT_EMAIL is required" }
$notifications = [ordered]@{}
foreach ($threshold in @(25, 50, 75, 90)) {
    $notifications["Actual_GreaterThan_$threshold"] = @{
        enabled = $true; operator = "GreaterThan"; threshold = $threshold
        thresholdType = "Actual"; contactEmails = @($contact)
    }
}
$body = @{ properties = @{
    amount = 100; category = "Cost"; timeGrain = "Annually"
    timePeriod = @{ startDate = "2026-08-01T00:00:00Z"; endDate = "2027-08-01T00:00:00Z" }
    notifications = $notifications
} } | ConvertTo-Json -Depth 8
$uri = "/subscriptions/$subscriptionId/providers/Microsoft.Consumption/budgets/splitbind-credit-budget?api-version=2023-11-01"
az rest --method put --uri $uri --body $body --output none
az rest --method get --uri $uri --output json | Out-Null
```

- [ ] **Step 4: Verify fixture tests, then observe the real cold gate**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File infra/scripts/verify-toolchain.ps1 -ReleaseTools`

Run: `python -m pytest tests/platform/test_azure_preflight.py -v`

Run: `python infra/scripts/azure_preflight.py cold --output artifacts/deployment/azure-cold.json`

Expected: fixture tests PASS. The real command exits zero only after the budget and all deallocated-host invariants are observed; before budget creation it must exit nonzero with `BUDGET_MISSING` and must not start or modify the VM.

- [ ] **Step 5: Commit**

```bash
git add infra/scripts/azure_preflight.py fixtures/platform/azure-valid-cold.json fixtures/platform/azure-valid-running.json docs/runbooks/azure-and-dns-cutover.md tests/platform/test_azure_preflight.py
git commit -m "feat(ops): add azure budget and host preflight"
```

### Task P10: Deploy Azure, cut over only the SplitBind subdomain, and prove TLS rollback

**Owner:** Leader performs Azure/DNS mutations; member independently runs public smoke checks. External start, DNS, and stop operations require explicit operator authorization at execution time.

**Files:**

- Create: `infra/scripts/materialize-secrets.sh`
- Create: `infra/scripts/bootstrap-host.sh`
- Create: `infra/systemd/splitbind.service`
- Create: `infra/systemd/splitbind-secrets.service`
- Create: `infra/systemd/splitbind-tmpfiles.conf`
- Create: `infra/scripts/dns-evidence.ps1`
- Modify: `infra/scripts/deploy.sh`
- Modify: `infra/scripts/rollback.sh`
- Modify: `docs/runbooks/azure-and-dns-cutover.md`
- Test: `tests/platform/test_cutover_runbook.py`
- Test: `tests/e2e/test_public_smoke.py`

**Interfaces:**

- `materialize-secrets.sh` obtains a Key Vault bearer token from Azure Instance Metadata Service through the VM's system-assigned managed identity, writes API and worker sources under host tmpfs `/run/splitbind/secrets`, and sets mode `0400`. API environment values enter only the `api` and `outbox` containers; the three worker-private key values never enter those Django containers, the repository, release manifest, or environment evidence. Docker maps only the three worker-private sources to `/run/secrets/{manifest_signing_key,fingerprint_key,integrity_key}` inside the worker.
- `dns-evidence.ps1 -Phase before|after|rollback -Output <absolute-json>` records authoritative NS/A answers, TTL, UTC time, and hostname while redacting unrelated zone records and target IP from publishable evidence.
- OnePortal cutover creates only an `A` record with host label `splitbind`, target equal to the runtime-observed static Azure IPv4, and TTL `300` seconds.

- [ ] **Step 1: Write failing cutover safety tests**

```python
# tests/platform/test_cutover_runbook.py
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_runbook_limits_dns_and_secret_scope():
    runbook = (ROOT / "docs/runbooks/azure-and-dns-cutover.md").read_text(encoding="utf-8")
    secrets = (ROOT / "infra/scripts/materialize-secrets.sh").read_text(encoding="utf-8")
    assert "splitbind.qivarn.id.vn" in runbook
    assert "Host label: `splitbind`" in runbook
    assert "TTL: `300`" in runbook
    assert "Do not modify: apex, NS, MX, email, existing hosting" in runbook
    assert "Metadata:true" in secrets
    assert "vault.azure.net" in secrets
    assert "chmod 0400" in secrets
    assert "manifest-signing-key" not in runbook
```

- [ ] **Step 2: Run tests and observe missing cutover files**

Run: `python -m pytest tests/platform/test_cutover_runbook.py -v`

Expected: FAIL because the secret materializer and finalized runbook do not exist.

- [ ] **Step 3: Implement secret isolation and the exact cutover/rollback sequence**

```sh
#!/bin/sh
# infra/scripts/materialize-secrets.sh
set -eu
: "${SPLITBIND_KEY_VAULT:?SPLITBIND_KEY_VAULT is required}"
install -d -m 0700 /run/splitbind/secrets
token="$(curl --fail --silent --show-error --noproxy "*" -H Metadata:true 'http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fvault.azure.net' | jq -er .access_token)"
fetch() {
    secret_name="$1"; output="$2"
    partial="${output}.partial"
    umask 077
    curl --fail --silent --show-error -H "Authorization: Bearer $token" "https://${SPLITBIND_KEY_VAULT}.vault.azure.net/secrets/${secret_name}?api-version=7.4" | jq -er .value > "$partial"
    chmod 0400 "$partial"
    mv "$partial" "$output"
}
fetch splitbind-api-env /run/splitbind/secrets/api.env
fetch splitbind-worker-env /run/splitbind/secrets/worker.env
fetch splitbind-manifest-signing-key /run/splitbind/secrets/manifest-signing-key.pk8
fetch splitbind-fingerprint-key /run/splitbind/secrets/fingerprint-key.bin
fetch splitbind-integrity-key /run/splitbind/secrets/integrity-key.bin
chown 10001:10001 /run/splitbind/secrets/manifest-signing-key.pk8 /run/splitbind/secrets/fingerprint-key.bin /run/splitbind/secrets/integrity-key.bin
chmod 0400 /run/splitbind/secrets/manifest-signing-key.pk8 /run/splitbind/secrets/fingerprint-key.bin /run/splitbind/secrets/integrity-key.bin
unset token
```

```sh
#!/bin/sh
# core of infra/scripts/bootstrap-host.sh
set -eu
[ "$(id -u)" -eq 0 ] || { echo "bootstrap requires root" >&2; exit 77; }
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates curl docker.io docker-compose jq unattended-upgrades
docker compose version >/dev/null
install -d -o root -g root -m 0755 /opt/splitbind /var/lib/splitbind/releases
install -m 0644 infra/systemd/splitbind-tmpfiles.conf /etc/tmpfiles.d/splitbind.conf
systemd-tmpfiles --create /etc/tmpfiles.d/splitbind.conf
if ! swapon --show=NAME --noheadings | grep -qx /swapfile; then
    fallocate -l 1G /swapfile
    chmod 0600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    grep -q '^/swapfile ' /etc/fstab || printf '%s\n' '/swapfile none swap sw 0 0' >> /etc/fstab
fi
sysctl -w vm.swappiness=10
install -m 0644 infra/systemd/splitbind-secrets.service infra/systemd/splitbind.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable splitbind.service
```

`splitbind-tmpfiles.conf` creates `/run/splitbind` as root mode `0700` on every boot. `splitbind-secrets.service` runs `materialize-secrets.sh` before `splitbind.service`; the latter starts production Compose from `/opt/splitbind`, uses `Restart=on-failure`, and runs no network-facing process outside containers. Azure NSG remains the host-ingress boundary, while Compose publishes only Caddy on ports 80 and 443. The bootstrap script does not start the application; deployment remains a separate authorized step after running audit.

```ini
# infra/systemd/splitbind-tmpfiles.conf
d /run/splitbind 0700 root root -
d /run/splitbind/secrets 0700 root root -
```

```ini
# infra/systemd/splitbind-secrets.service
[Unit]
Description=Materialize SplitBind secrets through managed identity
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=/etc/splitbind/host.env
ExecStart=/opt/splitbind/infra/scripts/materialize-secrets.sh
RemainAfterExit=yes
```

```ini
# infra/systemd/splitbind.service
[Unit]
Description=SplitBind production Compose stack
Requires=docker.service splitbind-secrets.service
After=docker.service splitbind-secrets.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/splitbind
ExecStartPre=/usr/bin/python3 infra/scripts/validate-release.py /var/lib/splitbind/releases/current.json --env-output /run/splitbind/release.env
ExecStart=/usr/bin/docker compose --env-file /run/splitbind/release.env -f infra/compose/compose.production.yaml up -d --remove-orphans
ExecStop=/usr/bin/docker compose --env-file /run/splitbind/release.env -f infra/compose/compose.production.yaml down
TimeoutStartSec=900

[Install]
WantedBy=multi-user.target
```

The runbook sequence is fixed:

1. Verify G3 evidence, encrypted backup/restore evidence, rollback evidence, release JSON, and image digests.
2. Run the cold Azure audit. Stop on any blocker.
3. Capture pre-cutover DNS evidence and confirm no existing `splitbind` record would be overwritten without a recorded rollback value.
4. With explicit authorization, start only `vm-splitbind-prod`; run the running audit before deployment.
5. Materialize secrets into `/run`, deploy the release by digest, and verify local liveness/readiness plus both workflows through SSH port forwarding. Do not mutate DNS yet.
6. Capture the previous image release and DNS state. In OnePortal create only: type `A`, host label `splitbind`, value equal to the runtime-observed static Azure IPv4, TTL `300`.
7. Query every authoritative name server discovered from `Resolve-DnsName qivarn.id.vn -Type NS` until all answer the expected A record or the 15-minute cutover window expires.
8. Verify Caddy obtained a certificate whose SAN contains `splitbind.qivarn.id.vn`; run public live, ready, static asset, session/CSRF, issuance, and verification smoke checks.
9. If authoritative DNS, TLS, readiness, or workflow smoke fails, restore the previous DNS state, run `rollback.sh` to the prior image digest, collect rollback DNS evidence, and verify recovery.
10. After the approved public test window, either keep the service running for the explicitly approved period or deallocate the VM and verify `VM deallocated`. Never promise that deallocation removes public-IP or disk cost.

- [ ] **Step 4: Prove local policy, then execute authorized public gates**

Run: `python -m pytest tests/platform/test_cutover_runbook.py -v`

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File infra/scripts/dns-evidence.ps1 -Phase before -Output artifacts/deployment/dns-before.json`

Run after authorized start: `python infra/scripts/azure_preflight.py running --output artifacts/deployment/azure-running.json`

Run after authorized DNS update: `curl --fail --silent --show-error https://splitbind.qivarn.id.vn/health/live`

Run after authorized DNS update: `curl --fail --silent --show-error https://splitbind.qivarn.id.vn/health/ready`

Run: `python -m pytest tests/e2e/test_public_smoke.py -v --base-url https://splitbind.qivarn.id.vn`

Expected: PASS with a valid hostname certificate, same-origin API, and both public workflows. Any failure invokes the recorded DNS/image rollback path and preserves diagnostics.

- [ ] **Step 5: Commit repository artifacts and retain private evidence outside Git**

```bash
git add infra/scripts/materialize-secrets.sh infra/scripts/bootstrap-host.sh infra/scripts/dns-evidence.ps1 infra/scripts/deploy.sh infra/scripts/rollback.sh infra/systemd docs/runbooks/azure-and-dns-cutover.md tests/platform/test_cutover_runbook.py tests/e2e/test_public_smoke.py
git commit -m "feat(release): gate azure dns and tls cutover"
```

Do not add `artifacts/deployment`, `/run/splitbind`, Azure output containing identifiers/IPs, backup archives, contact email, SSH material, or live release state.

## Track Verification Matrix

- `python -m unittest discover -s tests/platform -p "test_*.py" -v`
- `python -m unittest discover -s tests/security -p "test_production_compose.py" -v`
- `python -m pytest tests/integration/test_backup_restore.py tests/integration/test_release_rollback.py -v`
- `python -m pytest tests/e2e/test_offline_demo.py -v`
- `python -m pytest services/api/tests/observability -v`
- `cargo test --manifest-path services/worker/Cargo.toml -p splitbind-runtime --test metrics`
- `docker compose --env-file infra/compose/config-test.env -f infra/compose/compose.local.yaml --profile full config --quiet`
- `docker compose --env-file infra/compose/config-test.env -f infra/compose/compose.offline.yaml config --quiet`
- `docker compose --env-file infra/compose/config-test.env -f infra/compose/compose.production.yaml config --quiet`
- `powershell -NoProfile -ExecutionPolicy Bypass -File infra/scripts/ci.ps1`
- `docker buildx bake --file docker-bake.hcl --print`
- `python infra/scripts/azure_preflight.py cold --output artifacts/deployment/azure-cold.json`
- After explicit deployment authorization: running Azure audit and public smoke commands from P9.
- `git diff --check`

## Track Exit Evidence

- Root toolchain pins match the verified Windows toolchain and npm workspaces use `apps/*`.
- Local `core`, optional `research`/`observability`/`full`, and pull-free offline Compose configurations render and run.
- Production Compose has only the five approved services, publishes only 80/443 through Caddy, keeps private keys worker-only, and totals 2.75 GiB of container memory limits.
- Runtime inspection proves non-root users, read-only roots, explicit writable mounts, health checks, capability drop, and worker `/tmp` quota.
- Required metrics and alert thresholds exist without public metric exposure or high-cardinality/private labels.
- CI observes formatting, lint, types, unit/integration/contract/E2E, dependency/license/secret scans, critical/high image scans, one-day SBOMs, and amd64/arm64 builds.
- Encrypted metadata backup restores into an isolated database; no plaintext dump or production mutation remains.
- Injected release failure rolls back image digests and reversible migrations; offline issuance and verification work without external egress.
- Cold and running Azure audits pass with the budget present, no duplicate resource, correct VM/security/identity/disk/network state, and adequate disk headroom.
- Only `splitbind.qivarn.id.vn` is cut over; authoritative DNS, Caddy TLS, readiness, same-origin behavior, both workflows, DNS rollback, and final VM power state have observed evidence.
