# Local and offline operation

This runbook describes the P2 Compose boundaries. P2 provides static topology and parser validation only. P3 supplies matching container builds and hardening, B1/B6 supply application health behavior, and P7 supplies the release image inventory and offline-demo script. Do not treat a successful `docker compose config` render as runtime health evidence.

## Local profiles

Run commands from the repository root. The local topology publishes only Caddy on `http://localhost:8080`; PostgreSQL, MinIO, RabbitMQ, the API, outbox publisher, and worker remain on the private Compose network.

| Profile | Services | Intended use |
| --- | --- | --- |
| `core` | Caddy, API, outbox, RabbitMQ, worker, PostgreSQL, MinIO | Normal application development |
| `research` | Python research image | Algorithm experiments without the application stack |
| `observability` | Prometheus | Local metric inspection only |
| `full` | All local services plus the end-to-end runner | Complete local verification after dependent tasks land |

Validate a profile without creating containers or contacting the Docker daemon:

```powershell
python infra/scripts/check_compose_capabilities.py
docker compose --env-file infra/compose/config-test.env -f infra/compose/compose.local.yaml --profile core config --quiet
docker compose --env-file infra/compose/config-test.env -f infra/compose/compose.local.yaml --profile full config --quiet
```

The preflight probes `docker compose config --help` for the exact `--format`, `--no-env-resolution`, and `--no-path-resolution` capabilities used by platform tests. It does not contact the Docker daemon and reports an upgrade action when an option is unavailable; the project does not guess a historical minimum Compose version.

After P3 has built the placeholder images and the application-specific environment is configured, operators may start the core profile with:

```powershell
docker compose -f infra/compose/compose.local.yaml --profile core up -d
```

Stop the same project with `docker compose -f infra/compose/compose.local.yaml --profile core down`. Preserve named data deliberately if later tasks add volumes; never add `--volumes` unless deletion of that exact local state is intended.

## Offline demonstration boundary

The offline topology contains only Caddy, API, outbox, RabbitMQ, worker, PostgreSQL, and MinIO. Its application network is internal, every service uses `pull_policy: never`, and every image variable requires a digest reference. It does not use Neon, Cloudflare R2, Azure Key Vault, public DNS, or a public hostname.

Static validation uses deterministic fake digests and clearly marked non-production values:

```powershell
docker compose --env-file infra/compose/config-test.env -f infra/compose/compose.offline.yaml config --quiet
```

Those config-test files are parser fixtures, not runnable credentials. Application startup must reject them when `ENVIRONMENT=production`.

P7 owns the executable offline procedure. Its `infra/scripts/offline-demo.ps1` will load an approved image archive, bind the exact digests recorded in `infra/release/offline-images.txt`, and generate disposable synthetic credentials and key files below ignored `artifacts/offline/keys/` before startup. Do not copy production secrets, private course documents, or real recipient data into the offline bundle. After the demonstration, stop the Compose project and remove only the script-created disposable key directory after verifying its resolved path and ownership.

## Production separation

Production is a separate topology with exactly Caddy, API, outbox, RabbitMQ, and worker. Neon PostgreSQL and Cloudflare R2 remain external. Host secret sources are under `/run/splitbind/secrets`; only the worker receives the manifest-signing, fingerprint, and integrity private files at `/run/secrets`. API and outbox receive their environment file but never those worker-private key mounts. Production publishes only ports 80 and 443 through Caddy.

The rendered production environment exposes only non-secret routing hints: `SPLITBIND_DATABASE_HOST` identifies the external Neon hostname for API and outbox, while `OBJECT_STORAGE_ENDPOINT` identifies the HTTPS Cloudflare R2 endpoint for API and worker. Credential-bearing database and object-storage configuration remains in host-owned env files and never belongs in the Compose file. Future B1/B3 startup validation must fail closed unless each secret URL resolves to the same managed hostname/endpoint declared by its non-secret hint.

Validate the bounded P2 Caddy structure without downloading Caddy:

```powershell
python infra/scripts/validate_caddyfile.py
```

The validator accepts only this task's exact global block, site label, security headers, API/health reverse proxies, and static fallback, and emits structured JSON. It is deliberately not a general Caddy parser. P3 must additionally run the official `caddy validate` command inside the built web image; only that runtime-owned check proves compatibility with the packaged Caddy version.
