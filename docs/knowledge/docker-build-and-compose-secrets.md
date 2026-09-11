# Docker Build and Compose Secret Invariants

Verified production-container rules:

- A Dockerfile `ARG` used by any `FROM` must be declared before the first `FROM`; an `ARG` declared inside an earlier stage is not available to a later `FROM`.
- Some Docker Compose engines ignore file-secret `uid`, `gid`, and `mode`. Do not claim ownership enforcement from those fields alone.
- For non-root containers, verify secret readability with the real service UID, keep the mount read-only, expose it only to the intended service, and enforce host-side access controls.
- Host secret file permissions across non-root container boundaries: In Docker Compose, bind-mounted secret files inherit the host filesystem's permissions and UID/GID. If host secret files are `chmod 0600` owned by host UID 1000, a non-root container user (e.g. UID 10001) will fail with permission denied (`EACCES`). To secure secrets without blocking non-root containers: set the host secrets directory to `chmod 0700` (accessible only by the host administrator and root daemon) and set the mounted key files to `chmod 0644` (readable by the non-root container UID once bind-mounted).
- Image `ENTRYPOINT` vs one-shot commands: In Docker CLI, `docker run <image> <args>` appends arguments to the image's defined `ENTRYPOINT` rather than replacing it. If the image has an entrypoint script that launches a daemon (such as Gunicorn), one-shot operations (e.g. migrations, database seeds, or key registrations) will start the server and block indefinitely. One-shot commands must explicitly override the entrypoint with `--entrypoint <executable>`.
- Linux file capabilities and `cap_drop: [ALL]`: If a container binary has file capabilities set (e.g. Caddy Alpine binary has `setcap cap_net_bind_service=ep /usr/bin/caddy`), dropping all capabilities via `cap_drop: [ALL]` causes the Linux kernel to fail `execve` with `EPERM` (`Operation not permitted`). The capability must be retained via `cap_add: [NET_BIND_SERVICE]`.

## Container metadata and backup retrieval


On a tested read-only Docker container with writable /tmp tmpfs, an application-generated JSON backup existed according to in-container ls, while docker compose cp reported file-not-found. Do not assume generation failed or rerun migrations. Stream the exact backup with docker compose exec -T service cat into a private host-side file under umask 077; validate JSON without printing it. Remove only the disposable container copy after host verification. Keep the host backup while rollback retention is needed. This is a verified fallback for that mount behavior, not a claim that all docker cp operations on tmpfs fail.
